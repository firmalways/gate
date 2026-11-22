# FirmAlways Gate browser extension (Chrome / Edge, Manifest V3)

ซ่อนข้อมูลส่วนบุคคลก่อนวางข้อความลงใน ChatGPT, Claude หรือ Gemini บนเว็บ โดยใช้ FirmAlways Gate ที่รันในเครื่องหรือในองค์กรของคุณเอง

## What it does

- **Paste:** pasted text goes to your Gate (`/v1/firmalways/preview`). Personal data becomes `«TYPE_N»` before it reaches the chat box. Secrets and PDPA s.26 sensitive data are **not pasted at all** and a red notice explains why.
- **Display:** placeholders shown on the page (in your message and the AI's answer) are replaced with the real values **on your screen only**. The chat box is never touched, so what you send stays masked.
- **Fail closed:** if Gate is not reachable, nothing is pasted (configurable).
- The same value keeps the same placeholder for the whole tab. The mapping lives in the tab's memory only.

## Install (developer mode)

1. Run Gate: `FIRMALWAYS_GATE_API_KEY=<key> firmalways-gate serve`
2. Chrome → `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select this `extension/` folder.
3. Open the extension's **Options**, set the Gate URL (default `http://127.0.0.1:8787`) and the key.

For a company rollout, publish it privately through the Chrome Web Store or force-install it with Chrome Enterprise policy, pointing at your internal Gate URL.

## Limits

- Only **pasted** text is inspected. Text typed by hand is not checked in this version.
- File uploads through the site's own upload button are not inspected (use Gate's API path for files).
- Chat sites change their pages often; insertion uses the standard `insertText` command, which their editors support today.
- Tested in headless Chromium against a local test page (see `test/e2e_playwright.py`), not against the live chat sites, which need a signed-in account.

## Tests

```bash
node --test extension/test/*.test.js
uv run --python 3.12 --with playwright python -m playwright install chromium
uv run --python 3.12 --with playwright python extension/test/e2e_playwright.py
```
