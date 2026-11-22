"""AI answers are scanned too: new personal data that was not in the request is redacted."""

import json
import threading
import unittest
import urllib.request
from collections import Counter

from firmalways_gate.echo_upstream import EchoUpstreamServer
from firmalways_gate.engine import Gate, ResponseScanner, restore_completion
from firmalways_gate.policy import Policy
from firmalways_gate.pseudonymize import Pseudonymizer
from firmalways_gate.server import create_server

ID = "1101700203611"
LEAKED_ID = "3520100123457"
LEAKED_KEY = "sk-" + "proj-" + "Z9y8X7w6V5u4T3s2R1q0P9o8"


class EngineResponseScanTest(unittest.TestCase):
    def setUp(self):
        self.gate = Gate()
        self.p = Pseudonymizer()
        self.gate.protect_text(f"บัตร {ID} อีเมล a@example.com", self.p)

    def test_new_values_redacted_known_values_kept(self):
        counts = Counter()
        out = self.gate.scan_response(f"บัตร {ID} และบัตรอื่น {LEAKED_ID} key {LEAKED_KEY}", self.p, counts)
        self.assertEqual(out, f"บัตร {ID} และบัตรอื่น «REDACTED_THAI_NATIONAL_ID» key «REDACTED_SECRET»")
        self.assertEqual(counts, Counter({"THAI_NATIONAL_ID": 1, "SECRET": 1}))

    def test_types_allowed_by_default_are_kept(self):
        self.assertEqual(self.gate.scan_response("ติดต่อ b@example.com", self.p), "ติดต่อ b@example.com")

    def test_policy_controls(self):
        off = Gate(Policy.from_dict({"response": {"scan": False}}))
        self.assertEqual(off.scan_response(f"{LEAKED_ID}", Pseudonymizer()), LEAKED_ID)
        strict = Gate(Policy.from_dict({"response": {"default_action": "mask"}}))
        self.assertEqual(strict.scan_response("ติดต่อ b@example.com", Pseudonymizer()), "ติดต่อ «REDACTED_EMAIL»")

    def test_allowed_request_values_are_known(self):
        gate = Gate(Policy.from_dict({"entities": {"THAI_NATIONAL_ID": "allow"}}))
        p = Pseudonymizer()
        gate.protect_text(f"บัตร {LEAKED_ID}", p)
        self.assertEqual(gate.scan_response(f"บัตร {LEAKED_ID}", p), f"บัตร {LEAKED_ID}")

    def test_restore_completion_with_gate(self):
        data = {"choices": [{"message": {"content": f"«THAI_NATIONAL_ID_1» / {LEAKED_ID}"}}]}
        restore_completion(data, self.p, self.gate)
        self.assertEqual(data["choices"][0]["message"]["content"], f"{ID} / «REDACTED_THAI_NATIONAL_ID»")

    def test_stream_scanner_every_split(self):
        answer = f"ข้อมูลที่พบ: บัตร {LEAKED_ID} และ {ID} " + "ต่อ" * 120
        expected = self.gate.scan_response(answer, self.p)
        for i in range(0, len(answer) + 1, 7):
            scanner = ResponseScanner(self.gate, self.p, Counter())
            out = scanner.feed(answer[:i]) + scanner.feed(answer[i:]) + scanner.flush()
            self.assertEqual(out, expected, i)
        scanner = ResponseScanner(self.gate, self.p, Counter())
        self.assertEqual("".join(scanner.feed(c) for c in answer) + scanner.flush(), expected)


class ProxyResponseScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        leak = f"เรียบร้อย ส่วนบัตรของอีกคนคือ {LEAKED_ID} และ key {LEAKED_KEY}"
        cls.echo = EchoUpstreamServer(("127.0.0.1", 0), chunk_size=4, responder=lambda body: leak)
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()
        policy = Policy.from_dict({"upstreams": [{"name": "echo", "base_url": cls.echo.base_url, "models": ["echo"]}]})
        cls.gate = create_server(policy, "127.0.0.1", 0)
        threading.Thread(target=cls.gate.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.gate, cls.echo):
            server.shutdown()
            server.server_close()

    def post(self, stream):
        body = {"model": "echo", "stream": stream, "messages": [{"role": "user", "content": "สรุปให้หน่อย"}]}
        req = urllib.request.Request(self.gate.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return dict(resp.headers), resp.read().decode()

    def test_non_stream(self):
        headers, body = self.post(False)
        content = json.loads(body)["choices"][0]["message"]["content"]
        self.assertNotIn(LEAKED_ID, content)
        self.assertNotIn(LEAKED_KEY, content)
        self.assertIn("«REDACTED_SECRET»", content)
        self.assertEqual(headers["X-FirmAlways-Response-Redacted"], "SECRET=1,THAI_NATIONAL_ID=1")

    def test_stream(self):
        _, body = self.post(True)
        events = [line[6:] for line in body.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
        text = "".join(c["delta"].get("content", "") for e in events for c in json.loads(e)["choices"])
        self.assertEqual(text, "เรียบร้อย ส่วนบัตรของอีกคนคือ «REDACTED_THAI_NATIONAL_ID» และ key «REDACTED_SECRET»")


if __name__ == "__main__":
    unittest.main()
