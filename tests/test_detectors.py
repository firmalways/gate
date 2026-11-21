import unittest

from firmalways_gate.analyzer import analyze, resolve_overlaps
from firmalways_gate.detectors import bank_account, credit_card, email, phone, secret, thai_address, thai_name
from firmalways_gate.entities import Entity

# Secret-shaped test values are assembled at runtime so the source file never
# contains a string that secret scanners would flag.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
OPENAI_KEY = "sk-" + "proj-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
GITHUB_TOKEN = "ghp" + "_" + "A" * 36


def spans(detector, text):
    return [text[e.start:e.end] for e in detector.detect(text)]


class PhoneTest(unittest.TestCase):
    def test_mobile_formats(self):
        for value in ("0812345678", "081-234-5678", "081 234 5678", "081.234.5678", "+66 81 234 5678", "+66812345678"):
            self.assertEqual(spans(phone, f"โทร {value} ค่ะ"), [value], value)

    def test_landline(self):
        self.assertEqual(spans(phone, "สำนักงาน 02-123-4567"), ["02-123-4567"])
        self.assertEqual(spans(phone, "(+66)2-123-4567"), ["(+66)2-123-4567"])

    def test_unspaced_thai(self):
        self.assertEqual(spans(phone, "โทร0812345678ด่วน"), ["0812345678"])

    def test_not_phones(self):
        for text in ("สายด่วน 1112", "1101700203611", "ยอด 0812345678901", "เลข 01-234-5678"):
            self.assertEqual(spans(phone, text), [], text)


class EmailTest(unittest.TestCase):
    def test_basic_and_thai_boundaries(self):
        self.assertEqual(spans(email, "อีเมลsomchai.j+hr@example.co.thค่ะ"), ["somchai.j+hr@example.co.th"])
        self.assertEqual(spans(email, "ส่งมาที่ a@b.io."), ["a@b.io"])

    def test_not_email(self):
        self.assertEqual(spans(email, "user@localhost และ @mention"), [])


class BankAccountTest(unittest.TestCase):
    def test_formatted(self):
        self.assertEqual(spans(bank_account, "โอน 123-4-56789-0 นะ"), ["123-4-56789-0"])

    def test_keyword_context(self):
        self.assertEqual(spans(bank_account, "เลขบัญชี 1234567890 ครับ"), ["1234567890"])
        self.assertEqual(spans(bank_account, "KBank acct no. 123 456 7890"), ["123 456 7890"])

    def test_without_context_plain_numbers_are_ignored(self):
        self.assertEqual(spans(bank_account, "ใบสั่งซื้อ 4501234567"), [])


class CreditCardTest(unittest.TestCase):
    def test_luhn_valid(self):
        for value in ("4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111", "3782 822463 10005"):
            self.assertEqual(spans(credit_card, f"บัตร {value} หมดอายุ"), [value], value)

    def test_luhn_invalid_and_mixed_separators(self):
        self.assertEqual(spans(credit_card, "4111 1111 1111 1112"), [])
        self.assertEqual(spans(credit_card, "4111 1111-1111 1111"), [])

    def test_luhn_function(self):
        self.assertTrue(credit_card.luhn_valid("4111111111111111"))
        self.assertFalse(credit_card.luhn_valid("411111111111"))


class SecretTest(unittest.TestCase):
    def test_provider_keys(self):
        for value in (AWS_KEY, OPENAI_KEY, GITHUB_TOKEN):
            self.assertEqual(spans(secret, f"key={value} end"), [value], value[:6])

    def test_password_value_only(self):
        self.assertEqual(spans(secret, "รหัสผ่าน: hunter22"), ["hunter22"])
        self.assertEqual(spans(secret, "password = 'abc12345'"), ["abc12345"])

    def test_private_key_block(self):
        block = "-----BEGIN " + "PRIVATE KEY-----\nMIIE\n-----END " + "PRIVATE KEY-----"
        self.assertEqual(spans(secret, f"x {block} y"), [block])

    def test_not_secrets(self):
        self.assertEqual(spans(secret, "passport: AB12 and sk-short"), [])


class ThaiNameTest(unittest.TestCase):
    def test_titles(self):
        cases = {
            "นายสมชาย ใจดี เป็นลูกค้า": "สมชาย ใจดี",
            "นางสาวสมศรี เลขบัตร": "สมศรี",
            "ด.ช.ธนกฤต รักไทย": "ธนกฤต รักไทย",
            "ลูกค้าคุณวิภาวรรณ ศรีสุข": "วิภาวรรณ ศรีสุข",
            "คุณ ณัฐพล โทร": "ณัฐพล",
            "Mrs. Anna Lee called": "Anna Lee",
        }
        for text, expected in cases.items():
            self.assertEqual(spans(thai_name, text), [expected], text)

    def test_common_words_are_not_names(self):
        for text in (
            "ขอบคุณครับ",
            "ทนายความ",
            "นายจ้างต้องจ่าย",
            "คุณภาพดี",
            "นางแบบสวย",
            "คุณช่วยสรุปหน่อย",
            "นายกรัฐมนตรี",
            "นางพยาบาล",
            "คุณสมบัติผู้สมัคร",
        ):
            self.assertEqual(spans(thai_name, text), [], text)

    def test_names_that_start_like_stop_words_for_other_titles(self):
        self.assertEqual(spans(thai_name, "นายเอกชัย บุญมา"), ["เอกชัย บุญมา"])
        self.assertEqual(spans(thai_name, "นางสาวดวงใจ ทองคำ"), ["ดวงใจ ทองคำ"])


class ThaiAddressTest(unittest.TestCase):
    def test_full_address(self):
        value = "บ้านเลขที่ 12/3 หมู่ 4 ตำบลบางพลีใหญ่ อำเภอบางพลี จังหวัดสมุทรปราการ 10540"
        self.assertEqual(spans(thai_address, f"ส่งที่ {value} โทร 02-123-4567"), [value])

    def test_bangkok(self):
        value = "เลขที่ 99/1 ซอยสุขุมวิท 21 แขวงคลองเตยเหนือ เขตวัฒนา กรุงเทพฯ 10110"
        self.assertEqual(spans(thai_address, value), [value])

    def test_single_component_is_ignored(self):
        for text in ("เขตพื้นที่การศึกษา", "ราคา 35900 บาท", "ใบสั่งซื้อเลขที่ 4501234567"):
            self.assertEqual(spans(thai_address, text), [], text)


class AnalyzerTest(unittest.TestCase):
    def test_mixed_text(self):
        text = "ลูกค้าคุณสมชาย ใจดี เลขบัตร 1-1017-00203-61-1 โทร 081-234-5678 อีเมล a@example.com"
        found = [(e.type, text[e.start:e.end]) for e in analyze(text)]
        self.assertEqual(
            found,
            [
                ("PERSON", "สมชาย ใจดี"),
                ("THAI_NATIONAL_ID", "1-1017-00203-61-1"),
                ("PHONE", "081-234-5678"),
                ("EMAIL", "a@example.com"),
            ],
        )

    def test_lenient_thai_id_and_min_score(self):
        text = "เลข 1101700203612"
        self.assertEqual([e.type for e in analyze(text)], ["THAI_NATIONAL_ID"])
        self.assertEqual(analyze(text, lenient_thai_id=False), [])
        self.assertEqual(analyze(text, min_score=0.6), [])

    def test_entity_type_filter(self):
        text = "โทร 0812345678 a@example.com"
        self.assertEqual([e.type for e in analyze(text, entity_types=["EMAIL"])], ["EMAIL"])

    def test_resolve_overlaps_prefers_longer_then_score(self):
        a = Entity("A", 0, 10, "x" * 10, 0.5)
        b = Entity("B", 2, 5, "xxx", 1.0)
        c = Entity("C", 0, 10, "x" * 10, 0.9)
        d = Entity("D", 12, 14, "xx", 0.5)
        self.assertEqual([e.type for e in resolve_overlaps([a, b, c, d])], ["C", "D"])

    def test_no_personal_data(self):
        self.assertEqual(analyze("สรุปยอดขายเดือนนี้ให้หน่อย ราคา 4,990 บาท"), [])


if __name__ == "__main__":
    unittest.main()
