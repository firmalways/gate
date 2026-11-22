# FirmAlways Gate

[![CI](https://github.com/firmalways/gate/actions/workflows/ci.yml/badge.svg)](https://github.com/firmalways/gate/actions/workflows/ci.yml)

**Open-source AI privacy gateway for Thai personal data (PDPA).**
ด่านกรองข้อมูลส่วนบุคคลภาษาไทย ก่อนส่งข้อความไปหา AI — ตรวจจับ ซ่อน ส่งต่อ แล้วคืนค่าในคำตอบ โค้ดเปิดให้ตรวจสอบได้ทุกบรรทัด

```
คุณพิมพ์:   ร่างอีเมลถึงนางสาวสมศรี รักไทย บัตร 1-1017-00203-61-1 โทร 081-234-5678
AI ได้รับ:  ร่างอีเมลถึงนางสาว«PERSON_1» บัตร «THAI_NATIONAL_ID_1» โทร «PHONE_1»
คุณได้รับ:  คำตอบของ AI ที่ใส่ชื่อ เลขบัตร และเบอร์จริงกลับคืนให้แล้ว
```

> **Status: alpha (v0.2.0).** Gate helps reduce the risk of sending personal data to AI providers and supports PDPA work. It does **not** make an organization "PDPA compliant", and no detector finds 100% of personal data. Read [Known limits](#known-limits) before using it with real data.

## Why

- Employees paste customer data into ChatGPT, Claude or Gemini. Consumer plans may use it for training; every provider must read plaintext to answer.
- Global PII tools handle Thai poorly: Thai has no spaces between words, national IDs have a checksum, addresses have their own structure.
- A privacy tool should be verifiable. Gate is small, has **zero runtime dependencies** (Python standard library only) and runs inside your own machine or cloud.

## What it does

| | |
|---|---|
| Detects | Thai national ID (13 digits + checksum, Thai digits, any grouping), juristic tax ID, Thai phones (mobile, landline, +66), email, Thai bank accounts, payment cards (Luhn), passports, Thai licence plates, LINE IDs, IP addresses, secrets (API keys, tokens, private keys, passwords), person names with Thai/English titles (optional Thai NER for untitled names), Thai addresses |
| PDPA s.26 | Health, religion, criminal record, disability, biometric, genetic, political, union, sexual and race data — reported when it appears next to a person identifier, **blocked by default** |
| Masks | Replaces values with `«TYPE_N»` placeholders; the same value keeps the same placeholder within a request |
| Restores | Puts real values back into the AI's answer locally, including streamed answers and tool-call arguments |
| Scans answers | Redacts new IDs, cards, bank accounts, passports and secrets that the AI produces but you did not send (`«REDACTED_TYPE»`) |
| Files | Reads text from attached txt/csv/md/json, DOCX and PDF (optional `pypdf`), masks it and forwards it as text; refuses images and files it cannot read |
| Enforces | Per-type policy (`allow` / `mask` / `block`), a model allowlist, per-client keys (`[[clients]]`), fail-closed on errors |
| Proxies | OpenAI-compatible `/v1/chat/completions` (streaming and non-streaming): change only `base_url` |
| Audits | JSON Lines with counts per data type, model, client, action and latency — never prompt or answer content |
| Browser | A Chrome/Edge extension masks pasted text on ChatGPT, Claude and Gemini through your Gate ([extension/](extension/)) |

Detection adds about 2 ms for a 4,000-character prompt (p95, Apple Silicon).

## Install

Requires Python 3.11+ (or Docker).

```bash
curl -fsSL https://firmalways.meapplication.co.th/install.sh | sh
```

The script installs the latest release with uv, pipx or pip, including PDF support. Read it first: [install.sh](install.sh).
The same script is attached to every GitHub release:

```bash
curl -fsSL https://github.com/firmalways/gate/releases/latest/download/install.sh | sh
```

Docker (linux/amd64 and arm64):

```bash
docker run --rm -p 8787:8787 -e FIRMALWAYS_GATE_API_KEY=change-me \
  -v "$PWD/policy.toml:/etc/firmalways/policy.toml:ro" ghcr.io/firmalways/gate
```

From source, with optional extras `[pdf]` (pypdf) and `[thai-ner]` (PyThaiNLP):

```bash
pip install "firmalways-gate[pdf,thai-ner] @ git+https://github.com/firmalways/gate.git"
```

## Try it in one minute (no API key, nothing leaves your machine)

See what an AI would receive:

```bash
firmalways-gate scan "ลูกค้าคุณสมชาย ใจดี เลขบัตร 1101700203611 โทร 081-234-5678"
```

Run the full flow with a fake AI that echoes what it receives:

```bash
firmalways-gate echo-upstream --port 8788
```

```bash
FIRMALWAYS_GATE_API_KEY=demo-key firmalways-gate serve --policy examples/policy.demo.toml
```

```bash
curl -s http://127.0.0.1:8787/v1/chat/completions \
  -H "Authorization: Bearer demo-key" -H "Content-Type: application/json" \
  -d '{"model":"echo","messages":[{"role":"user","content":"โอนเข้าบัญชี 123-4-56789-0 ให้นายเอกชัย บุญมา"}]}'
```

The echo terminal prints `AI received: โอนเข้าบัญชี «BANK_ACCOUNT_1» ให้นาย«PERSON_1»`, while your answer contains the real values.

## Use with a real AI provider

1. Copy [`policy.example.toml`](policy.example.toml) to `policy.toml` and list the models you allow.
2. Put the provider key in Gate's environment, not in your apps:

```bash
OPENAI_API_KEY=sk-... FIRMALWAYS_GATE_API_KEY=$(openssl rand -hex 24) firmalways-gate serve --policy policy.toml
```

3. Point any OpenAI-compatible client at Gate:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1", api_key="<FIRMALWAYS_GATE_API_KEY>")
client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": "..."}])
```

The same works for Open WebUI, LibreChat, LiteLLM and other tools that accept an OpenAI base URL. Upstreams can be OpenAI, Azure OpenAI (your own subscription, `auth_header = "api-key"`), any OpenAI-compatible endpoint, or a local model (Ollama, vLLM, LM Studio) so nothing leaves the machine.

## Use as a library

```python
from firmalways_gate import Gate, Pseudonymizer

gate = Gate()                      # default policy: mask personal data, block secrets
p = Pseudonymizer()                # one per request, memory only
masked, protection = gate.protect_text("นายสมชาย ใจดี โทร 0812345678", p)
if protection.blocked:
    raise RuntimeError(protection.blocked_types)
answer = call_your_llm(masked)     # "เรียนคุณ«PERSON_1» ..."
print(p.restore(answer))           # "เรียนคุณสมชาย ใจดี ..."
```

## HTTP API

| Method and path | Purpose |
|---|---|
| `GET /healthz` | Liveness (no auth) |
| `GET /v1/models` | Models allowed by policy |
| `POST /v1/chat/completions` | Mask → forward → restore. Response header `X-FirmAlways-Entities` lists counts per type |
| `POST /v1/firmalways/preview` | `{"text": "..."}` → what the AI would receive, without calling it |

Errors use the OpenAI error shape with `type: "firmalways_gate"` and codes `blocked_entity` (422), `content_not_allowed` (422), `model_not_allowed` (403), `unauthorized` (401), `upstream_unreachable` (502), `detection_failed` (500, request not forwarded).

## Security model

- **Fail closed.** If inspection fails, the request is refused, never forwarded unmasked.
- **No content at rest.** Placeholder mappings live in memory for one request. Chat clients resend history each turn, so placeholders stay consistent without storage.
- **Audit without content.** User IDs are HMAC-SHA256 hashed when `FIRMALWAYS_AUDIT_HMAC_KEY` is set.
- **Client authentication.** Set `FIRMALWAYS_GATE_API_KEY`; Gate warns when it listens beyond localhost without one.
- **Provider keys stay in Gate.** Clients authenticate to Gate, Gate authenticates to the provider.

## Benchmark

```bash
firmalways-gate benchmark --dataset curated
```

On a curated set of 50 hand-written Thai prompts, Gate finds 94% of labelled values with no false positives (98% with the Thai NER extra); Microsoft Presidio in its default English setup finds 54%. Details, caveats and how to reproduce: [docs/benchmark.md](docs/benchmark.md). The curated set is written by the maintainers and not yet externally annotated.

## Known limits

- Context can still leak: masking a name does not hide a confidential fact in the same sentence.
- Without the Thai NER extra, names are found only after a title (นาย, นางสาว, คุณ, ด.ช., Mr. ...); names starting with common words in the stop lists are missed.
- PDPA s.26 detection uses keyword lists: it is a heuristic, not a classifier. Review the lists for your organisation.
- Bank accounts without the `XXX-X-XXXXX-X` format are found only near a keyword (บัญชี, ธนาคาร, bank names).
- Images are not inspected (no OCR) and are refused by default; so are uploaded `file_id` references. Scanned PDFs without a text layer yield no text.
- Streaming answers are delayed by up to 200 characters while Gate scans them.
- Only traffic sent through Gate is protected.
- The server uses Python's standard-library HTTP server: suitable for a team or department behind TLS termination, not yet for high-traffic public exposure.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Design: [docs/architecture.md](docs/architecture.md)

## FirmAlways Pro

Gate stays free and open source. For organisations, **FirmAlways Pro** adds per-department policies, a PDPA report for your DPO and installation in your own cloud with an offline licence: [firmalways.meapplication.co.th/pro](https://firmalways.meapplication.co.th/pro/). `firmalways-gate serve` prints one line about Pro at startup; hide it with `FIRMALWAYS_NO_PRO_HINT=1`. Gate never contacts our servers.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability privately.

## License

Apache-2.0. "FirmAlways" is the project's brand name; forks should use a different name.
