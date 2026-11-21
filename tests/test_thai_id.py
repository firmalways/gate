import unittest

from firmalways_gate.detectors import thai_id

# Synthetic numbers with valid check digits (not real people).
VALID_A = "1101700203611"
VALID_B = "3520100123457"
INVALID = "1101700203612"  # last digit wrong


class IsValidThaiIdTest(unittest.TestCase):
    def test_valid_numbers(self):
        for value in (VALID_A, VALID_B, "8000000000014", "3123409876549"):
            self.assertTrue(thai_id.is_valid_thai_id(value), value)

    def test_wrong_check_digit(self):
        self.assertFalse(thai_id.is_valid_thai_id(INVALID))

    def test_only_one_check_digit_is_valid(self):
        valid = [d for d in "0123456789" if thai_id.is_valid_thai_id(VALID_A[:12] + d)]
        self.assertEqual(valid, ["1"])

    def test_wrong_length(self):
        self.assertFalse(thai_id.is_valid_thai_id(VALID_A[:12]))
        self.assertFalse(thai_id.is_valid_thai_id(VALID_A + "0"))

    def test_all_zeros_is_invalid(self):
        self.assertFalse(thai_id.is_valid_thai_id("0000000000000"))

    def test_separators_and_thai_digits(self):
        self.assertTrue(thai_id.is_valid_thai_id("1-1017-00203-61-1"))
        self.assertTrue(thai_id.is_valid_thai_id("๑๑๐๑๗๐๐๒๐๓๖๑๑"))


class DetectTest(unittest.TestCase):
    def assert_single(self, text, expected_raw):
        found = thai_id.detect(text)
        self.assertEqual(len(found), 1, found)
        entity = found[0]
        self.assertEqual(entity.type, thai_id.ENTITY_TYPE)
        self.assertEqual(text[entity.start:entity.end], expected_raw)
        self.assertEqual(entity.text, expected_raw)
        self.assertEqual(entity.score, 1.0)

    def test_plain(self):
        self.assert_single(f"ID {VALID_A}", VALID_A)

    def test_hyphen_grouping(self):
        self.assert_single("เลขบัตร 1-1017-00203-61-1 ค่ะ", "1-1017-00203-61-1")

    def test_space_grouping(self):
        self.assert_single("เลขบัตร 1 1017 00203 61 1", "1 1017 00203 61 1")

    def test_thai_digits(self):
        self.assert_single("บัตร ๑๑๐๑๗๐๐๒๐๓๖๑๑", "๑๑๐๑๗๐๐๒๐๓๖๑๑")

    def test_inside_unspaced_thai_text(self):
        self.assert_single(f"ผู้ป่วยเลขบัตร{VALID_A}โทร0812345678", VALID_A)

    def test_multiple_in_order(self):
        found = thai_id.detect(f"{VALID_A} และ {VALID_B}")
        self.assertEqual([e.text for e in found], [VALID_A, VALID_B])

    def test_invalid_checksum_skipped_by_default(self):
        self.assertEqual(thai_id.detect(f"ID {INVALID}"), [])

    def test_invalid_checksum_reported_when_lenient(self):
        found = thai_id.detect(f"ID {INVALID}", require_checksum=False)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].score, 0.5)

    def test_longer_digit_runs_are_not_ids(self):
        self.assertEqual(thai_id.detect(f"9{VALID_A}"), [])
        self.assertEqual(thai_id.detect(f"{VALID_A}9"), [])
        self.assertEqual(thai_id.detect(f"๙{VALID_A}"), [])

    def test_phone_number_is_not_an_id(self):
        self.assertEqual(thai_id.detect("โทร 081-234-5678", require_checksum=False), [])

    def test_repr_hides_raw_value(self):
        entity = thai_id.detect(VALID_A)[0]
        self.assertNotIn(VALID_A, repr(entity))


if __name__ == "__main__":
    unittest.main()
