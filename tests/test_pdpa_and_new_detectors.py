import time
import unittest

from firmalways_gate.analyzer import analyze
from firmalways_gate.detectors import ip_address, license_plate, line_id, passport, sensitive, thai_id
from firmalways_gate.engine import Gate
from firmalways_gate.policy import Policy
from firmalways_gate.pseudonymize import Pseudonymizer


def found(text, **kw):
    return [(e.type, text[e.start:e.end]) for e in analyze(text, **kw)]


def spans(detector, text):
    return [text[e.start:e.end] for e in detector.detect(text)]


class SensitiveDataTest(unittest.TestCase):
    def test_reported_only_with_an_identifier(self):
        self.assertEqual(found("อาการเบาหวานมีอะไรบ้าง"), [])
        self.assertEqual(found("นายสมชาย ใจดี เป็นเบาหวาน"), [("PERSON", "สมชาย ใจดี"), ("SENSITIVE_HEALTH", "เบาหวาน")])

    def test_can_report_without_identifier(self):
        self.assertEqual(found("อาการเบาหวาน", sensitive_requires_identifier=False), [("SENSITIVE_HEALTH", "เบาหวาน")])

    def test_categories(self):
        cases = {
            "SENSITIVE_RELIGION": "นับถือศาสนาอิสลาม",
            "SENSITIVE_CRIMINAL": "มีประวัติอาชญากรรม",
            "SENSITIVE_DISABILITY": "เป็นผู้พิการ",
            "SENSITIVE_BIOMETRIC": "ข้อมูลลายนิ้วมือ",
            "SENSITIVE_GENETIC": "ผลตรวจยีน",
            "SENSITIVE_POLITICAL": "เป็นสมาชิกพรรค",
            "SENSITIVE_UNION": "สมาชิกสหภาพแรงงาน",
            "SENSITIVE_SEXUAL": "รสนิยมทางเพศ",
            "SENSITIVE_RACE": "เชื้อชาติ",
        }
        for kind, phrase in cases.items():
            types = [e.type for e in sensitive.detect(phrase)]
            self.assertIn(kind, types, phrase)

    def test_english_keywords_use_word_boundaries(self):
        self.assertEqual([e.type for e in sensitive.detect("Mr. Lee was diagnosed with cancer")],
                         ["SENSITIVE_HEALTH", "SENSITIVE_HEALTH"])
        self.assertEqual(sensitive.detect("hearing aids and a racecar"), [])

    def test_audit_result_is_not_health(self):
        self.assertEqual(sensitive.detect("ผลตรวจสอบบัญชีของนายสมชาย"), [])

    def test_default_policy_blocks_sensitive_personal_data(self):
        _, protection = Gate().protect_text("นางสาวสมศรี ผลตรวจเลือดพบเชื้อเอชไอวี", Pseudonymizer())
        self.assertEqual(protection.blocked_types, {"SENSITIVE_HEALTH"})

    def test_policy_can_mask_sensitive_terms(self):
        gate = Gate(Policy.from_dict({"entities": {"SENSITIVE_HEALTH": "mask"}}))
        text, protection = gate.protect_text("นายสมชาย ป่วยเป็นมะเร็ง", Pseudonymizer())
        self.assertFalse(protection.blocked)
        self.assertEqual(text, "นาย«PERSON_1» «SENSITIVE_HEALTH_1»«SENSITIVE_HEALTH_2»")


class NewDetectorsTest(unittest.TestCase):
    def test_passport(self):
        self.assertEqual(spans(passport, "หนังสือเดินทางเลขที่ AA1234567 หมดอายุ"), ["AA1234567"])
        self.assertEqual(spans(passport, "Passport No.: x1234567"), ["x1234567"])
        self.assertEqual(spans(passport, "รหัส AA1234567"), [])

    def test_license_plate(self):
        self.assertEqual(spans(license_plate, "รถทะเบียน กข 1234 กรุงเทพมหานคร"), ["กข 1234"])
        self.assertEqual(spans(license_plate, "ทะเบียนรถ 1กข-1234"), ["1กข-1234"])
        self.assertEqual(spans(license_plate, "เลขทะเบียนนิติบุคคล 0105556000123"), [])

    def test_line_id(self):
        self.assertEqual(spans(line_id, "แอดไลน์ @firmshop ได้เลย"), ["@firmshop"])
        self.assertEqual(spans(line_id, "LINE ID: somchai.99"), ["somchai.99"])
        self.assertEqual(spans(line_id, "ไอดีไลน์ wipa_2024"), ["wipa_2024"])
        self.assertEqual(spans(line_id, "line 25 of the file"), [])
        self.assertEqual(spans(line_id, "ไลน์กลุ่มบริษัท"), [])

    def test_ip_address(self):
        self.assertEqual(spans(ip_address, "ล็อกอินจาก 203.0.113.45 เมื่อวาน"), ["203.0.113.45"])
        self.assertEqual(spans(ip_address, "2001:0db8:85a3:0000:0000:8a2e:0370:7334"), ["2001:0db8:85a3:0000:0000:8a2e:0370:7334"])
        self.assertEqual(spans(ip_address, "เวอร์ชัน 1.2.3 และ 999.1.1.1 และ 1.2.3.4.5"), [])

    def test_tax_id_for_companies(self):
        text = "บริษัท ตัวอย่าง จำกัด เลขประจำตัวผู้เสียภาษี 0105556000123"
        valid = thai_id.is_valid_thai_id("0105556000123")
        entities = thai_id.detect(text, require_checksum=False)
        self.assertEqual([e.type for e in entities], ["TAX_ID"])
        self.assertEqual(entities[0].score, 1.0 if valid else 0.5)
        # A personal ID next to the same keyword stays a national ID.
        self.assertEqual([e.type for e in thai_id.detect("เลขผู้เสียภาษี 1101700203611")], ["THAI_NATIONAL_ID"])

    def test_identifiers_trigger_sensitive_detection(self):
        self.assertIn(("SENSITIVE_HEALTH", "เบาหวาน"), found("ไลน์ @somchai99 เป็นเบาหวาน"))


class RobustnessTest(unittest.TestCase):
    def test_adversarial_inputs_are_fast(self):
        inputs = [
            "a" * 100_000,
            "1" * 100_000,
            "ก" * 100_000,
            "a@" * 50_000,
            "1-" * 50_000,
            "คุณ" * 30_000,
            "บัญชี " + "1 " * 50_000,
            "-----BEGIN PRIVATE KEY-----" + "x" * 100_000,
            "เลขที่ 1 " * 20_000,
        ]
        for text in inputs:
            start = time.perf_counter()
            analyze(text)
            self.assertLess(time.perf_counter() - start, 3.0, text[:20])


if __name__ == "__main__":
    unittest.main()
