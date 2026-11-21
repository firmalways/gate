"""End-to-end tests: client → Gate proxy → echo upstream (a fake AI) → Gate → client."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from firmalways_gate.audit import AuditLog
from firmalways_gate.echo_upstream import PREFIX, EchoUpstreamServer
from firmalways_gate.policy import Policy
from firmalways_gate.server import create_server

ID = "1101700203611"
PHONE = "081-234-5678"
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
PROMPT = f"ช่วยร่างจดหมายถึงนายสมชาย ใจดี บัตร {ID} โทร {PHONE}"
CLIENT_KEY = "test-client-key"


def start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class ProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.echo = start(EchoUpstreamServer(("127.0.0.1", 0), chunk_size=3))
        cls.tmp = tempfile.TemporaryDirectory()
        cls.audit_path = Path(cls.tmp.name) / "audit.jsonl"
        policy = Policy.from_dict(
            {"upstreams": [{"name": "echo", "base_url": cls.echo.base_url, "models": ["echo"], "timeout": 10}]}
        )
        dead = Policy.from_dict(
            {"upstreams": [{"name": "dead", "base_url": "http://127.0.0.1:9/v1", "models": ["dead"], "timeout": 2}]}
        )
        cls.policy = Policy(**{**policy.__dict__, "upstreams": policy.upstreams + dead.upstreams})
        cls.gate = start(
            create_server(cls.policy, "127.0.0.1", 0, audit=AuditLog(str(cls.audit_path), b"k"), client_api_key=CLIENT_KEY)
        )

    @classmethod
    def tearDownClass(cls):
        for server in (cls.gate, cls.echo):
            server.shutdown()
            server.server_close()
        cls.tmp.cleanup()

    def request(self, path, body=None, *, key=CLIENT_KEY, method=None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(self.gate.url + path, data=data, method=method or ("POST" if data else "GET"))
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read().decode()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, dict(exc.headers), exc.read().decode()

    def chat(self, content, **extra):
        return self.request("/v1/chat/completions", {"model": "echo", "messages": [{"role": "user", "content": content}], **extra})

    def last_upstream_text(self):
        return self.echo.received[-1]["messages"][-1]["content"]

    def test_health_needs_no_key(self):
        status, _, body = self.request("/healthz", key=None)
        self.assertEqual((status, json.loads(body)["status"]), (200, "ok"))

    def test_models(self):
        status, _, body = self.request("/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual({m["id"] for m in json.loads(body)["data"]}, {"echo", "dead"})

    def test_auth_required(self):
        self.assertEqual(self.chat("hi", )[0], 200)
        status, _, _ = self.request("/v1/chat/completions", {"model": "echo", "messages": []}, key="wrong")
        self.assertEqual(status, 401)

    def test_non_streaming_round_trip(self):
        status, headers, body = self.chat(PROMPT)
        self.assertEqual(status, 200)
        seen_by_ai = self.last_upstream_text()
        for value in ("สมชาย", ID, PHONE):
            self.assertNotIn(value, seen_by_ai)
        self.assertIn("«THAI_NATIONAL_ID_1»", seen_by_ai)
        answer = json.loads(body)["choices"][0]["message"]["content"]
        self.assertEqual(answer, PREFIX + PROMPT)
        self.assertEqual(headers["X-FirmAlways-Entities"], "PERSON=1,PHONE=1,THAI_NATIONAL_ID=1")

    def test_streaming_round_trip(self):
        status, headers, body = self.chat(PROMPT, stream=True)
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers["Content-Type"])
        events = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1], "[DONE]")
        text = "".join(
            choice["delta"].get("content", "") for e in events[:-1] for choice in json.loads(e)["choices"]
        )
        self.assertEqual(text, PREFIX + PROMPT)
        self.assertNotIn(ID, self.last_upstream_text())

    def test_secret_is_blocked_and_never_forwarded(self):
        before = len(self.echo.received)
        status, _, body = self.chat(f"ช่วยดูโค้ดนี้ key={AWS_KEY}")
        self.assertEqual(status, 422)
        error = json.loads(body)["error"]
        self.assertEqual((error["code"], error["entity_types"]), ("blocked_entity", ["SECRET"]))
        self.assertNotIn(AWS_KEY, body)
        self.assertEqual(len(self.echo.received), before)

    def test_model_not_allowed(self):
        status, _, body = self.request("/v1/chat/completions", {"model": "gpt-x", "messages": []})
        self.assertEqual((status, json.loads(body)["error"]["code"]), (403, "model_not_allowed"))

    def test_image_content_blocked(self):
        status, _, body = self.chat([{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}])
        self.assertEqual((status, json.loads(body)["error"]["code"]), (422, "content_not_allowed"))

    def test_bad_requests(self):
        self.assertEqual(self.request("/v1/chat/completions", {"model": "echo"})[0], 400)
        self.assertEqual(self.request("/v1/chat/completions", {"model": "echo", "messages": ["x"]})[0], 400)
        self.assertEqual(self.request("/nope", {"a": 1})[0], 404)

    def test_upstream_unreachable(self):
        status, _, body = self.request("/v1/chat/completions", {"model": "dead", "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual((status, json.loads(body)["error"]["code"]), (502, "upstream_unreachable"))

    def test_preview(self):
        status, _, body = self.request("/v1/firmalways/preview", {"text": PROMPT})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["masked_text"], "ช่วยร่างจดหมายถึงนาย«PERSON_1» บัตร «THAI_NATIONAL_ID_1» โทร «PHONE_1»")
        self.assertTrue(result["would_forward"])

    def test_audit_has_no_content(self):
        self.chat(PROMPT, user="emp-001")
        log = self.audit_path.read_text(encoding="utf-8")
        for value in ("สมชาย", ID, PHONE, "emp-001", "ช่วยร่าง"):
            self.assertNotIn(value, log)
        actions = {json.loads(line)["action"] for line in log.splitlines()}
        self.assertIn("forwarded", actions)


if __name__ == "__main__":
    unittest.main()
