import importlib.util
import unittest

from firmalways_gate.analyzer import analyze
from firmalways_gate.detectors.thai_ner import ThaiNER
from firmalways_gate.engine import Gate
from firmalways_gate.policy import Policy, PolicyError


class FakeTagger:
    def __init__(self, tags):
        self.tags = tags

    def tag(self, text, pos=False):
        return self.tags


class ThaiNERUnitTest(unittest.TestCase):
    def test_spans_and_trimming(self):
        text = "ลูกค้าคุณมีนา ขอเลื่อนนัด ส่งให้สมชายตรวจ"
        tags = [("ลูกค้า", "B-PERSON"), ("คุณ", "I-PERSON"), ("มีนา", "I-PERSON"), (" ", "O"), ("ขอ", "O"),
                ("เลื่อนนัด", "O"), (" ", "O"), ("ส่ง", "O"), ("ให้", "O"), ("สม", "B-PERSON"), ("ชาย", "I-PERSON"),
                ("ตรวจ", "O")]
        found = ThaiNER(tagger=FakeTagger(tags))(text)
        self.assertEqual([text[e.start:e.end] for e in found], ["มีนา", "สมชาย"])

    def test_merges_with_rule_based_names(self):
        text = "นายสมชาย ใจดี"
        tags = [("นาย", "B-PERSON"), ("สม", "I-PERSON"), ("ชาย", "I-PERSON"), (" ", "I-PERSON"), ("ใจดี", "I-PERSON")]
        found = analyze(text, extra_detectors=[ThaiNER(tagger=FakeTagger(tags))])
        self.assertEqual([(e.type, text[e.start:e.end]) for e in found], [("PERSON", "สมชาย ใจดี")])

    def test_unknown_words_are_skipped(self):
        self.assertEqual(ThaiNER(tagger=FakeTagger([("xyz", "B-PERSON")]))("abc"), [])

    @unittest.skipIf(importlib.util.find_spec("pythainlp"), "pythainlp installed")
    def test_policy_without_pythainlp(self):
        with self.assertRaises(PolicyError) as ctx:
            Gate(Policy(thai_ner=True))
        self.assertIn("thai-ner", str(ctx.exception))


@unittest.skipUnless(importlib.util.find_spec("pythainlp"), "pythainlp not installed")
class ThaiNERRealTest(unittest.TestCase):
    def test_untitled_name(self):
        gate = Gate(Policy(thai_ner=True))
        text = "ส่งรายงานให้สมชายตรวจก่อนนะ"
        self.assertIn(("PERSON", "สมชาย"), [(e.type, text[e.start:e.end]) for e in gate.analyze(text)])


if __name__ == "__main__":
    unittest.main()
