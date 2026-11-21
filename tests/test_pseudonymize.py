import unittest

from firmalways_gate.analyzer import analyze
from firmalways_gate.entities import Entity
from firmalways_gate.pseudonymize import MAX_HOLD, Pseudonymizer

ID = "1101700203611"


class MaskRestoreTest(unittest.TestCase):
    def test_round_trip(self):
        text = f"นายสมชาย ใจดี บัตร {ID} โทร 081-234-5678"
        p = Pseudonymizer()
        masked = p.mask(text, analyze(text))
        self.assertEqual(masked, "นาย«PERSON_1» บัตร «THAI_NATIONAL_ID_1» โทร «PHONE_1»")
        for value in ("สมชาย", ID, "081-234-5678"):
            self.assertNotIn(value, masked)
        self.assertEqual(p.restore(masked), text)

    def test_same_value_same_placeholder_across_formats(self):
        p = Pseudonymizer()
        first = p.mask(f"บัตร {ID}", analyze(f"บัตร {ID}"))
        second_text = "บัตร 1-1017-00203-61-1"
        second = p.mask(second_text, analyze(second_text))
        self.assertEqual(first, "บัตร «THAI_NATIONAL_ID_1»")
        self.assertEqual(second, "บัตร «THAI_NATIONAL_ID_1»")

    def test_phone_prefix_normalization(self):
        p = Pseudonymizer()
        a = p.placeholder_for(Entity("PHONE", 0, 10, "0812345678"))
        b = p.placeholder_for(Entity("PHONE", 0, 15, "+66 81 234 5678"))
        c = p.placeholder_for(Entity("PHONE", 0, 10, "0899999999"))
        self.assertEqual((a, b, c), ("«PHONE_1»", "«PHONE_1»", "«PHONE_2»"))

    def test_restore_tolerates_spacing_and_bare_tokens(self):
        p = Pseudonymizer()
        p.placeholder_for(Entity("PHONE", 0, 10, "0812345678"))
        self.assertEqual(p.restore("โทร « PHONE_1 » หรือ PHONE_1 ได้"), "โทร 0812345678 หรือ 0812345678 ได้")

    def test_restore_leaves_unknown_and_lookalike_tokens(self):
        p = Pseudonymizer()
        p.placeholder_for(Entity("PHONE", 0, 10, "0812345678"))
        self.assertEqual(p.restore("«EMAIL_9» PHONE_10 XPHONE_1"), "«EMAIL_9» PHONE_10 XPHONE_1")

    def test_restore_without_mapping_is_identity(self):
        self.assertEqual(Pseudonymizer().restore("«PHONE_1»"), "«PHONE_1»")

    def test_overlapping_entities_rejected(self):
        with self.assertRaises(ValueError):
            Pseudonymizer().mask("abcdef", [Entity("A", 0, 4, "abcd"), Entity("B", 2, 6, "cdef")])


class StreamRestorerTest(unittest.TestCase):
    def setUp(self):
        self.p = Pseudonymizer()
        self.p.placeholder_for(Entity("THAI_NATIONAL_ID", 0, 13, ID))
        self.p.placeholder_for(Entity("PERSON", 0, 5, "สมชาย"))
        self.answer = "เรียนคุณ«PERSON_1» เลขบัตร «THAI_NATIONAL_ID_1» ได้รับแล้ว PERSON_1"
        self.expected = f"เรียนคุณสมชาย เลขบัตร {ID} ได้รับแล้ว สมชาย"

    def stream(self, pieces):
        r = self.p.stream_restorer()
        return "".join(r.feed(piece) for piece in pieces) + r.flush()

    def test_every_split_point(self):
        for i in range(len(self.answer) + 1):
            self.assertEqual(self.stream([self.answer[:i], self.answer[i:]]), self.expected, i)

    def test_character_by_character(self):
        self.assertEqual(self.stream(list(self.answer)), self.expected)

    def test_unclosed_marker_is_released_after_limit(self):
        r = self.p.stream_restorer()
        released = r.feed("«" + "x" * (MAX_HOLD + 1))
        self.assertTrue(released.startswith("«"))
        self.assertFalse(r.pending)


if __name__ == "__main__":
    unittest.main()
