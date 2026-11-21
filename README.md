# FirmAlways Gate

**Open-source AI privacy gateway for Thai personal data (PDPA).**
ด่านกรองข้อมูลส่วนบุคคลภาษาไทย ก่อนส่งข้อความไปหา AI — ตรวจจับ ซ่อน ส่งต่อ แล้วคืนค่าในคำตอบ โค้ดเปิดให้ตรวจสอบได้ทุกบรรทัด

```
คุณพิมพ์:   ร่างอีเมลถึงนางสาวสมศรี รักไทย บัตร 1-1017-00203-61-1 โทร 081-234-5678
AI ได้รับ:  ร่างอีเมลถึงนางสาว«PERSON_1» บัตร «THAI_NATIONAL_ID_1» โทร «PHONE_1»
คุณได้รับ:  คำตอบของ AI ที่ใส่ชื่อ เลขบัตร และเบอร์จริงกลับคืนให้แล้ว
```

> **Status: alpha (v0.1.0).** Gate helps reduce the risk of sending personal data to AI providers and supports PDPA work. It does **not** make an organization "PDPA compliant", and no detector finds 100% of personal data. Read [Known limits](#known-limits) before using it with real data.

## Why

- Employees paste customer data into ChatGPT, Claude or Gemini. Consumer plans may use it for training; every provider must read plaintext to answer.
- Global PII tools handle Thai poorly: Thai has no spaces between words, national IDs have a checksum, addresses have their own structure.
- A privacy tool should be verifiable. Gate is small, has **zero runtime dependencies** (Python standard library only) and runs inside your own machine or cloud.

## What it does

| | |
|---|---|
| Detects | Thai national ID (13 digits + checksum, Thai digits, any grouping), Thai phones (mobile, landline, +66), email, Thai bank accounts, payment cards (Luhn), secrets (API keys, tokens, private keys, passwords), person names with Thai/English titles, Thai addresses |
| Masks | Replaces values with `«TYPE_N»` placeholders; the same value keeps the same placeholder within a request |
| Restores | Puts real values back into the AI's answer locally, including streamed answers and tool-call arguments |
| Enforces | Per-type policy (`allow` / `mask` / `block`), a model allowlist, refusal of images/files it cannot inspect, fail-closed on errors |
| Proxies | OpenAI-compatible `/v1/chat/completions` (streaming and non-streaming): change only `base_url` |
| Audits | JSON Lines with counts per data type, model, action and latency — never prompt or answer content |

Detection adds about 2 ms for a 4,000-character prompt (p95, Apple Silicon).

## Install

Requires Python 3.11+.

```bash
pip install git+https://github.com/piyawatSritavong/FirmAlways-Gate.git
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
firmalways-gate benchmark
```

Runs a synthetic Thai dataset (generated values, no real people) including hard negatives such as คุณภาพ, นายจ้าง, ขอบคุณ, order numbers and prices. Current result: 100% precision and recall on 313 samples. **This is optimistic**: the same authors wrote the detectors and the templates. It is a regression guard. A human-labelled dataset and a comparison with Microsoft Presidio are next.

## Known limits

- Context can still leak: masking a name does not hide a confidential fact in the same sentence.
- Names are found only after a title (นาย, นางสาว, คุณ, ด.ช., Mr. ...). Untitled names, and names starting with common words in the stop lists, are missed. Thai NER is planned.
- Bank accounts without the `XXX-X-XXXXX-X` format are found only near a keyword (บัญชี, ธนาคาร, bank names).
- Images, PDFs and other files are not inspected; by default requests containing them are refused.
- Only traffic sent through Gate is protected.
- The server uses Python's standard-library HTTP server: suitable for a team or department behind TLS termination, not yet for high-traffic public exposure.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Design: [docs/architecture.md](docs/architecture.md)

## License

Apache-2.0. "FirmAlways" is the project's brand name; forks should use a different name.
