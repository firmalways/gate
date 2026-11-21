import json
import tempfile
import unittest
from pathlib import Path

from firmalways_gate.audit import AuditLog
from firmalways_gate.engine import ContentNotAllowed, Gate, restore_completion
from firmalways_gate.policy import Policy, PolicyError, load_policy
from firmalways_gate.pseudonymize import Pseudonymizer

ROOT = Path(__file__).resolve().parents[1]
ID = "1101700203611"
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"


class PolicyTest(unittest.TestCase):
    def test_defaults(self):
        policy = Policy()
        self.assertEqual(policy.action_for("SECRET"), "block")
        self.assertEqual(policy.action_for("PHONE"), "mask")
        self.assertEqual(policy.action_for("SOMETHING_NEW"), "mask")
        self.assertIsNone(policy.route("gpt-4.1"))

    def test_example_files_load(self):
        for name in ("policy.example.toml", "examples/policy.demo.toml"):
            policy = load_policy(ROOT / name)
            self.assertTrue(policy.upstreams, name)

    def test_routing_and_wildcard(self):
        policy = Policy.from_dict(
            {
                "upstreams": [
                    {"name": "a", "base_url": "https://a.example/v1", "models": ["m1"]},
                    {"name": "b", "base_url": "http://b.example/v1", "models": ["*"]},
                ]
            }
        )
        self.assertEqual(policy.route("m1").name, "a")
        self.assertEqual(policy.route("anything").name, "b")
        self.assertEqual(policy.route("m1").chat_url, "https://a.example/v1/chat/completions")

    def test_entity_overrides(self):
        policy = Policy.from_dict({"default_action": "block", "entities": {"phone": "allow"}})
        self.assertEqual(policy.action_for("PHONE"), "allow")
        self.assertEqual(policy.action_for("UNKNOWN"), "block")

    def test_invalid_policies(self):
        bad = [
            {"default_action": "ignore"},
            {"entities": {"PHONE": "hide"}},
            {"detection": {"min_score": 2}},
            {"detection": {"lenient_thai_id": "yes"}},
            {"upstreams": [{"name": "a", "base_url": "ftp://x", "models": ["m"]}]},
            {"upstreams": [{"name": "a", "base_url": "https://x", "models": []}]},
            {"upstreams": [{"name": "a", "base_url": "https://x", "models": ["m"]}] * 2},
            {"server": {"max_body_bytes": 0}},
        ]
        for data in bad:
            with self.assertRaises(PolicyError, msg=data):
                Policy.from_dict(data)

    def test_unreadable_and_invalid_toml(self):
        with self.assertRaises(PolicyError):
            load_policy("/nonexistent/policy.toml")
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write("default_action = ")
        with self.assertRaises(PolicyError):
            load_policy(fh.name)


class GateTest(unittest.TestCase):
    def test_protect_messages_masks_all_text_and_copies(self):
        messages = [
            {"role": "system", "content": "ลูกค้าคือนายสมชาย ใจดี"},
            {"role": "user", "content": [{"type": "text", "text": f"บัตร {ID}"}]},
            {"role": "assistant", "tool_calls": [{"function": {"name": "f", "arguments": '{"phone": "0812345678"}'}}]},
        ]
        p = Pseudonymizer()
        out, protection = Gate().protect_messages(messages, p)
        self.assertEqual(out[0]["content"], "ลูกค้าคือนาย«PERSON_1»")
        self.assertEqual(out[1]["content"][0]["text"], "บัตร «THAI_NATIONAL_ID_1»")
        self.assertEqual(out[2]["tool_calls"][0]["function"]["arguments"], '{"phone": "«PHONE_1»"}')
        self.assertEqual(messages[1]["content"][0]["text"], f"บัตร {ID}")  # input untouched
        self.assertEqual(protection.masked, 3)
        self.assertFalse(protection.blocked)

    def test_blocked_types(self):
        _, protection = Gate().protect_messages([{"role": "user", "content": f"key {AWS_KEY}"}], Pseudonymizer())
        self.assertEqual(protection.blocked_types, {"SECRET"})

    def test_allow_action_keeps_value(self):
        gate = Gate(Policy.from_dict({"entities": {"EMAIL": "allow"}}))
        text, protection = gate.protect_text("a@example.com", Pseudonymizer())
        self.assertEqual(text, "a@example.com")
        self.assertEqual(protection.counts["EMAIL"], 1)

    def test_non_text_content(self):
        messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:x"}}]}]
        with self.assertRaises(ContentNotAllowed):
            Gate().protect_messages(messages, Pseudonymizer())
        Gate(Policy.from_dict({"content": {"allow_non_text": True}})).protect_messages(messages, Pseudonymizer())

    def test_malformed_messages(self):
        for messages in (["text"], [{"content": 5}], [{"content": ["x"]}]):
            with self.assertRaises(TypeError):
                Gate().protect_messages(messages, Pseudonymizer())

    def test_preview(self):
        result = Gate().preview(f"บัตร {ID} key {AWS_KEY}")
        self.assertFalse(result["would_forward"])
        self.assertEqual(result["blocked_types"], ["SECRET"])
        self.assertNotIn(ID, json.dumps(result))
        self.assertEqual(result["entities"][0]["placeholder"], "«THAI_NATIONAL_ID_1»")

    def test_restore_completion(self):
        p = Pseudonymizer()
        Gate().protect_text(f"บัตร {ID}", p)
        data = {
            "choices": [
                {"message": {"content": "บัตร «THAI_NATIONAL_ID_1»", "tool_calls": [{"function": {"arguments": "THAI_NATIONAL_ID_1"}}]}}
            ]
        }
        restore_completion(data, p)
        self.assertEqual(data["choices"][0]["message"]["content"], f"บัตร {ID}")
        self.assertEqual(data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"], ID)


class AuditTest(unittest.TestCase):
    def test_writes_jsonl_without_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            log = AuditLog(str(path), b"key")
            log.write(request_id="r1", user=log.user_ref("emp-001"), action="forwarded", status=200, entities={"PHONE": 1})
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["entities"], {"PHONE": 1})
            self.assertNotIn("emp-001", path.read_text(encoding="utf-8"))
            self.assertEqual(len(record["user"]), 32)
            self.assertIn("ts", record)

    def test_rejects_content_fields(self):
        with self.assertRaises(ValueError):
            AuditLog("-").write(prompt="secret text")

    def test_user_ref_needs_key(self):
        self.assertIsNone(AuditLog("-").user_ref("emp-001"))
        self.assertIsNone(AuditLog("-", b"k").user_ref(None))

    def test_disabled(self):
        AuditLog(None).write(action="forwarded")  # no error, no output


if __name__ == "__main__":
    unittest.main()
