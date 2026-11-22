"""Details fraudsters use to impersonate someone: full address, birth date, nationality."""

import unittest

from firmalways_gate.analyzer import analyze
from firmalways_gate.detectors import birth_date, nationality, thai_address
from firmalways_gate.engine import Gate
from firmalways_gate.pseudonymize import Pseudonymizer


def spans(detector, text):
    return [text[e.start:e.end] for e in detector.detect(text)]


class AddressWithBuildingTest(unittest.TestCase):
    def test_condo_and_bare_house_number(self):
        value = "ธันยาคารคอนโดมิเนียม 50/38 ซอยลาดพร้าว 38 ถนนลาดพร้าว แขวงสามเสนนอก เขตห้วยขวาง กรุงเทพมหานคร 10310"
        self.assertEqual(spans(thai_address, f"ส่งของไปที่\n{value}\nขอบคุณค่ะ"), [value])

    def test_lead_in_words_are_not_part_of_the_building(self):
        self.assertEqual(
            spans(thai_address, "ส่งไปที่อาคารสาทรทาวเวอร์ ถนนสาทรใต้ แขวงยานนาวา"),
            ["อาคารสาทรทาวเวอร์ ถนนสาทรใต้ แขวงยานนาวา"],
        )

    def test_not_addresses(self):
        for text in ("ประชุมวันที่ 22/11/2026 ห้อง 501", "ราคา 50/38 บาท", "อาคารเรียนใหม่สร้างเสร็จแล้ว", "สัดส่วน 3/4 ของยอดขาย"):
            self.assertEqual(spans(thai_address, text), [], text)


class BirthDateTest(unittest.TestCase):
    def test_formats(self):
        cases = {
            "วันเกิด 12 มีนาคม 2530": "12 มีนาคม 2530",
            "เกิดวันที่ 1 ม.ค. 2535": "1 ม.ค. 2535",
            "วัน/เดือน/ปีเกิด: 05/11/2530": "05/11/2530",
            "ว/ด/ป เกิด ๑๒/๐๓/๒๕๓๐": "๑๒/๐๓/๒๕๓๐",
            "Date of birth: 1990-04-01": "1990-04-01",
            "DOB 4 July 1988": "4 July 1988",
            "born on March 3, 1992": "March 3, 1992",
        }
        for text, expected in cases.items():
            self.assertEqual(spans(birth_date, text), [expected], text)

    def test_dates_without_birth_keyword_are_ignored(self):
        self.assertEqual(spans(birth_date, "ประชุมวันที่ 12 มีนาคม 2569"), [])

    def test_birth_date_identifies_a_person_for_section_26(self):
        found = [(e.type, e.text) for e in analyze("วันเกิด 12/03/2530 เป็นเบาหวาน")]
        self.assertIn(("SENSITIVE_HEALTH", "เบาหวาน"), found)


class NationalityTest(unittest.TestCase):
    def test_only_with_an_identifier(self):
        self.assertEqual([e.type for e in analyze("คนสัญชาติไทยต้องเสียภาษีไหม")], [])
        text = "นายสมชาย ใจดี สัญชาติไทย"
        self.assertIn(("NATIONALITY", "สัญชาติไทย"), [(e.type, text[e.start:e.end]) for e in analyze(text)])

    def test_english(self):
        self.assertEqual(spans(nationality, "nationality: Thai"), ["Thai"])


class DefaultPolicyTest(unittest.TestCase):
    def test_id_card_details_are_masked(self):
        text = "นายสมชาย ใจดี วันเกิด 12 มีนาคม 2530 สัญชาติไทย"
        masked, protection = Gate().protect_text(text, Pseudonymizer())
        self.assertEqual(masked, "นาย«PERSON_1» วันเกิด «DATE_OF_BIRTH_1» «NATIONALITY_1»")
        self.assertFalse(protection.blocked)


if __name__ == "__main__":
    unittest.main()
