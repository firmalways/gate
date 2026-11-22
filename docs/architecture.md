# FirmAlways Gate v0.1 — System Design

Status: implemented in v0.1.0 (22 November 2026). Scope: the open-source core. Paid SMB and Company products build on top of it and are out of scope here.

Implementation notes that differ from the first draft:
- Policy files are **TOML** (standard-library `tomllib`) instead of YAML, so the core keeps zero runtime dependencies. Python 3.11+.
- The proxy uses the standard-library `ThreadingHTTPServer` and `urllib` instead of FastAPI/httpx, for the same reason: everything a customer must audit is in this repository.
- Thai names use title-based rules (นาย, นางสาว, คุณ, ...) with stop lists; Thai NER remains a planned optional extra.
- The Presidio comparison is not implemented yet.

## v0.2.0 additions (22 November 2026)

- **PDPA s.26 sensitive data** (`detectors/sensitive.py`): keyword lists per category; reported only when the same text holds a person identifier; blocked by default. A title-based name that swallows a sensitive term is trimmed so the term is still reported.
- **Response scanning** (`engine.scan_response`, `ResponseScanner`): values in the answer that were not in the request (masked or allowed) are redacted per `[response]` policy; streaming holds back 200 characters plus any entity crossing the cut.
- **Files** (`files.py`): `file` content parts with inline `file_data` are extracted (text, DOCX by regex over `word/document.xml` with a size cap, PDF via optional pypdf), masked, and replaced by a text part. Anything unreadable is refused.
- **More detectors**: passport, licence plate, LINE ID, IP address, juristic tax ID.
- **Thai NER extra** (`detectors/thai_ner.py`): PyThaiNLP `thainer`, passed to `analyze(extra_detectors=...)` per Gate instance.
- **Clients** (`[[clients]]`): one key per app or team, fail closed when a key variable is unset, client name in the audit log, and a `gate_for_client` hook so a separate product can choose a policy per client.
- **Browser extension** (`extension/`): paste interception through `/v1/firmalways/preview`, tab-wide placeholder numbering, on-screen restoration outside editable fields, code-point to UTF-16 offset conversion.
- **Benchmarks**: curated v0 set and a Presidio comparison (`docs/benchmark.md`).

## 1. Requirements

### Functional
1. Detect Thai personal data in prompt text: national ID (13 digits, checksum), phone, email, bank account, Thai person names, addresses, and secrets (API keys, passwords).
2. Replace each detected value with a placeholder before the prompt leaves the customer boundary, and restore the real value in the model's answer locally.
3. Apply a policy per entity type: `allow`, `mask` or `block`. Allow only approved upstream providers and models.
4. Expose an OpenAI-compatible endpoint (`POST /v1/chat/completions`, streaming and non-streaming) so existing apps only change `base_url`.
5. Write an audit record per request **without prompt or answer content**.
6. Ship a public synthetic Thai benchmark that reports precision and recall per entity type, compared with Microsoft Presidio.

### Non-functional
| Property | Target for v0.1 |
|---|---|
| Added latency (rule detectors, 4,000-character prompt) | p95 < 50 ms |
| State | Stateless; nothing about content persisted by default |
| Failure mode | **Fail closed**: if detection or policy fails, the request is blocked, never forwarded unmasked |
| Deployment | Single container or `pip install`; runs in the customer's own machine or cloud |
| Dependencies | Core library has zero runtime dependencies; Thai NER and the proxy are optional extras |

### Constraints
- One developer, about 4–6 weeks for v0.1.
- Python 3.11+, because the Thai NLP ecosystem (PyThaiNLP) and Presidio are Python.
- Apache-2.0 license.

## 2. High-level design

```
 Client app / Open WebUI / LiteLLM / browser extension (v0.2)
        │  OpenAI-format request (real values)
        ▼
┌──────────────────────────── FirmAlways Gate (customer boundary) ───────────────────────────┐
│                                                                                            │
│  ① Detector registry ──► ② Policy engine ──► ③ Pseudonymizer ──► ④ Upstream router ───────┼──► Approved provider
│   rules: THAI_NATIONAL_ID,  per type:           value → «THAI_NATIONAL_ID_1»   model allowlist │   (Azure OpenAI, Bedrock,
│   phone, email, bank, secret allow/mask/block   mapping kept in memory         fail closed     │    OpenAI API, local model)
│   NER: Thai names (extra)   block → 4xx         for this request only                          │
│                                                                                            │
│  ⑥ Audit writer ◄──────────────────────────── ⑤ Restorer ◄─────────────────────────────────┼─── Answer with placeholders
│   JSONL: time, request id, hashed user,        placeholders → real values                    │
│   model, counts per entity type, action        (streaming-safe buffer)                       │
└────────────────────────────────────────────────────────────────────────────────────────────┘
        │  Answer with real values
        ▼
      Client
```

### Package layout
```
src/firmalways_gate/
  entities.py          Entity dataclass (raw text hidden from repr)
  detectors/           One module per entity type; each exposes ENTITY_TYPE and detect(text) -> list[Entity]
  analyzer.py          Run all detectors, filter by score, resolve overlaps
  policy.py            Load TOML policy: action per entity type, model allowlist, upstreams
  pseudonymize.py      Pseudonymizer (mask / restore) and StreamRestorer (chunk-safe restore)
  engine.py            Gate: apply policy to text and chat messages; preview; restore completions
  audit.py             Content-free JSON Lines writer with HMAC user references
  server.py            OpenAI-compatible proxy (standard library)
  echo_upstream.py     Fake AI that echoes what it receives, for demos and tests
  benchmark.py         Synthetic Thai dataset and scorer
  cli.py               scan | serve | echo-upstream | benchmark
```

## 3. Deep dive

### 3.1 Detection
- **Rules first.** Structured identifiers (national ID, phone, bank account, email, secrets) use regex plus validation (checksum, prefix tables). Precise, fast and explainable.
- **Thai digits.** Every numeric detector accepts Arabic (0–9) and Thai (๐–๙) digits.
- **No word boundaries.** Thai is written without spaces, so detectors use digit look-arounds instead of `\b`. Example: `บัตร1101700203611โทร` must match.
- **Names and addresses** need NER (PyThaiNLP) as an optional extra; they will have lower precision and are reported separately in the benchmark.
- **Overlaps.** When spans overlap, keep the longest span, then the highest score.
- **Strict vs. lenient.** `require_checksum=False` also reports 13-digit numbers that fail the checksum (score 0.5), because a mistyped ID is still personal data. The default policy should mask them too.

### 3.2 Pseudonymization and restoration
- Placeholder format: `«TYPE_N»` (for example `«THAI_NATIONAL_ID_1»`). The guillemets are rare in prompts and models usually copy them intact.
- Numbering is per request and in order of appearance. The same value gets the same placeholder within a request. Chat clients resend the whole history each turn, so mapping stays consistent **without storing anything between requests**.
- The mapping lives only in memory for the request and is discarded after the response.
- **Streaming:** a placeholder may be split across chunks. The restorer holds back the tail of the buffer that could be the start of a placeholder (at most the longest placeholder length) and flushes it once the placeholder is complete or ruled out.
- **Model mangling:** models sometimes drop or alter placeholders. Restoration tolerates spacing changes. Unrestored placeholders are left visible, never guessed.

### 3.3 Policy
```toml
# policy.toml — full example in policy.example.toml
default_action = "mask"        # unknown types are masked

[entities]
THAI_NATIONAL_ID = "mask"
SECRET = "block"

[[upstreams]]
name = "azure"
base_url = "https://<customer-resource>.openai.azure.com/openai/v1"
api_key_env = "AZURE_OPENAI_API_KEY"
auth_header = "api-key"
models = ["<deployment>"]
```
- A blocked entity returns HTTP 422 with entity types only, never the values.
- Requests to models not on the allowlist return HTTP 403.
- Non-text content parts (images, files) return HTTP 422 unless `content.allow_non_text = true`.
- An invalid policy file stops Gate from starting (exit code 2).

### 3.4 Audit record
```json
{"ts":"2026-11-22T10:00:00+07:00","request_id":"…","user":"hmac-sha256(user_id)","upstream":"azure-openai-th",
 "model":"gpt-4.1","entities":{"THAI_NATIONAL_ID":1,"PHONE":2},"action":"forwarded","latency_ms":38}
```
No prompt text, answer text, placeholder mapping or raw values, ever. User IDs are HMAC-hashed with a key the customer holds.

### 3.5 Error handling
| Failure | Behavior |
|---|---|
| Detector raises | Block request (fail closed), audit `action: error` |
| Upstream HTTP error | Pass the upstream status and body through; retry is the client's decision |
| Upstream unreachable or timeout | HTTP 502 `upstream_unreachable` |
| Policy file invalid at startup | Refuse to start |
| Restoration incomplete | Return answer with remaining placeholders visible |

## 4. Scale and reliability
- CPU-bound regex work; one process handles many requests. Scale horizontally behind any load balancer because there is no shared state.
- Thai NER is the expensive part; keep it optional and measure its latency separately.
- Monitoring: request count, block rate, entity counts per type, added latency p50/p95, upstream error rate. Never log content to monitoring.

## 5. Trade-offs

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Language | Python | Go/Rust | Thai NLP ecosystem and Presidio compatibility; measured ~2 ms p95 for 4,000 characters |
| HTTP stack | Standard library | FastAPI/httpx | Zero dependencies to audit; revisit for high traffic (no HTTP/1.1 keep-alive, no async) |
| Detection | Rules + optional NER | LLM-based detection | Deterministic, fast, explainable, no data sent to another model |
| Integration | Standalone core + adapters (LiteLLM guardrail, Open WebUI filter, Presidio recognizers) | Fork Presidio | Zero-dependency core; adapters ride existing ecosystems |
| Mapping storage | Per-request memory | Persistent vault | Nothing to leak at rest; works because clients resend history |
| Failure mode | Fail closed | Fail open | A privacy tool must never forward unmasked data silently |

## 6. Known limits (state them publicly)
- Context still leaks: masking names does not hide a confidential business fact in the sentence.
- Detection is never 100%; publish measured precision and recall.
- Files, images and screenshots are out of scope for v0.1.
- Gate only protects traffic that goes through it; personal devices can bypass it.
- Gate supports PDPA work; it does not make a company "PDPA compliant".

## 7. Revisit as the system grows
- Persistent, customer-key-encrypted vault for long-lived agents and documents.
- File and image extraction (PDF, DOCX, OCR).
- Browser extension for shadow-AI control (v0.2).
- Dashboard, PDPA reports and SSO (paid Company product).
- Confidential-computing deployment with remote attestation for the most sensitive customers.
