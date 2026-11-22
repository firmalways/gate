import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from firmalways_gate.audit import AuditLog
from firmalways_gate.echo_upstream import EchoUpstreamServer
from firmalways_gate.engine import Gate
from firmalways_gate.policy import Policy, PolicyError
from firmalways_gate.server import create_server

ENV = {"GATE_KEY_HR": "hr-secret", "GATE_KEY_SALES": "sales-secret"}


class ClientKeysTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = mock.patch.dict(os.environ, ENV)
        cls.env.start()
        cls.echo = EchoUpstreamServer(("127.0.0.1", 0))
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()
        cls.policy = Policy.from_dict({
            "upstreams": [{"name": "echo", "base_url": cls.echo.base_url, "models": ["echo"]}],
            "clients": [{"name": "hr", "api_key_env": "GATE_KEY_HR"}, {"name": "sales", "api_key_env": "GATE_KEY_SALES"}],
        })
        # Per-client policy through the extension point: sales may send email addresses as-is.
        sales = Gate(Policy(**{**cls.policy.__dict__, "entity_actions": {**cls.policy.entity_actions, "EMAIL": "allow"}}))
        base = Gate(cls.policy)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.audit_path = Path(cls.tmp.name) / "audit.jsonl"
        cls.gate = create_server(cls.policy, "127.0.0.1", 0, audit=AuditLog(str(cls.audit_path)),
                                 gate_for_client=lambda c: sales if c == "sales" else base)
        threading.Thread(target=cls.gate.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.gate, cls.echo):
            server.shutdown()
            server.server_close()
        cls.env.stop()
        cls.tmp.cleanup()

    def chat(self, key, text="ส่งไปที่ a@example.com"):
        body = {"model": "echo", "messages": [{"role": "user", "content": text}]}
        req = urllib.request.Request(self.gate.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code

    def test_each_client_key_works_and_unknown_key_is_refused(self):
        self.assertEqual(self.chat("hr-secret"), 200)
        self.assertEqual(self.chat("sales-secret"), 200)
        self.assertEqual(self.chat("other"), 401)
        self.assertEqual(self.chat(""), 401)

    def test_per_client_policy_and_audit(self):
        self.chat("hr-secret")
        self.assertIn("«EMAIL_1»", self.echo.received[-1]["messages"][0]["content"])
        self.chat("sales-secret")
        self.assertIn("a@example.com", self.echo.received[-1]["messages"][0]["content"])
        clients = [json.loads(line).get("client") for line in self.audit_path.read_text().splitlines()]
        self.assertIn("hr", clients)
        self.assertIn("sales", clients)

    def test_invalid_clients(self):
        for data in ({"clients": [{"name": "a"}]}, {"clients": [{"name": "a", "api_key_env": "X"}] * 2}, {"clients": {}}):
            with self.assertRaises(PolicyError):
                Policy.from_dict(data)


if __name__ == "__main__":
    unittest.main()
