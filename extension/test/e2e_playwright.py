"""End-to-end test of the browser extension in real Chromium (optional, not run in CI).

Loads the unpacked extension, runs a live Gate, opens a local test page that
stands in for a chat site, and checks paste masking, blocking, display
restoration and fail-closed behaviour.

    uv run --python 3.12 --with playwright python -m playwright install chromium
    uv run --python 3.12 --with playwright python extension/test/e2e_playwright.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from playwright.sync_api import sync_playwright  # noqa: E402

from firmalways_gate.policy import Policy  # noqa: E402
from firmalways_gate.server import create_server  # noqa: E402

PAGE = """<!doctype html><meta charset="utf-8"><title>fake chat</title>
<textarea id="box" style="width:600px;height:80px"></textarea>
<div id="chat"></div>"""
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"


def serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    work = Path(tempfile.mkdtemp())
    ext = work / "extension"
    shutil.copytree(ROOT / "extension", ext, ignore=shutil.ignore_patterns("test"))
    manifest = json.loads((ext / "manifest.json").read_text())
    manifest["content_scripts"][0]["matches"].append("http://127.0.0.1/*")  # the local test page
    (ext / "manifest.json").write_text(json.dumps(manifest))
    (work / "site").mkdir()
    (work / "site" / "index.html").write_text(PAGE, encoding="utf-8")

    gate = serve(create_server(Policy(), "127.0.0.1", 0, client_api_key="e2e-key"))
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = partial(Quiet, directory=str(work / "site"))
    site = serve(ThreadingHTTPServer(("127.0.0.1", 0), handler))
    site_url = f"http://127.0.0.1:{site.server_address[1]}/index.html"

    checks: list[tuple[str, bool]] = []
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(work / "profile"),
            channel="chromium",
            headless=True,
            args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}"],
        )
        worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
        worker.evaluate(
            "s => chrome.storage.local.set(s)", {"gateUrl": gate.url, "apiKey": "e2e-key", "failOpen": False}
        )
        page = context.new_page()
        page.goto(site_url)

        def toasts():
            return page.evaluate("() => [...document.querySelectorAll('[data-firmalways-toast]')].map(t => t.textContent).join(' | ')")

        def paste(text):
            page.evaluate(
                """t => { const box = document.getElementById('box'); box.focus();
                   const dt = new DataTransfer(); dt.setData('text/plain', t);
                   box.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }""",
                text,
            )
            page.wait_for_timeout(700)
            return page.input_value("#box")

        value = paste("ลูกค้านายสมชาย ใจดี บัตร 1101700203611 โทร 081-234-5678")
        checks.append(("paste is masked", value == "ลูกค้านาย«PERSON_1» บัตร «THAI_NATIONAL_ID_1» โทร «PHONE_1»"))

        page.evaluate("() => { const d = document.createElement('p'); d.id = 'reply'; "
                      "d.textContent = 'เรียนคุณ«PERSON_1» เบอร์ «PHONE_1»'; document.getElementById('chat').appendChild(d); }")
        page.wait_for_timeout(300)
        checks.append(("answer is restored on screen", page.text_content("#reply") == "เรียนคุณสมชาย ใจดี เบอร์ 081-234-5678"))
        checks.append(("chat box stays masked", "1101700203611" not in page.input_value("#box")))

        page.fill("#box", "")
        value = paste(f"ช่วยดู key {AWS_KEY}")
        toast = toasts()
        checks.append(("secret paste is blocked", value == "" and "SECRET" in toast))

        gate.shutdown()
        gate.server_close()
        page.wait_for_timeout(5200)  # let the previous toast disappear
        value = paste("โทร 0812345678")
        toast = toasts()
        checks.append(("fails closed when Gate is down", value == "" and "ไม่ทำงาน" in toast))
        context.close()

    site.shutdown()
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
