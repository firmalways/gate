"""Sensitive personal data under Thailand's PDPA, section 26.

Section 26 covers race, ethnicity, political opinions, religious or philosophical
beliefs, sexual behaviour, criminal records, health data, disability, trade
union information, genetic data and biometric data. Processing it generally
needs explicit consent, and sending it to an external AI provider is a cross-
border transfer to a processor.

A keyword on its own is not personal data ("อาการเบาหวานมีอะไรบ้าง" is a general
question). The analyzer therefore reports these entities only when the same
text also identifies a person (see ``analyzer.IDENTIFIER_TYPES``).

Keyword lists are deliberately conservative. They are a heuristic, not a
classifier: review and extend them for your organisation.
"""

from __future__ import annotations

import re

from ..entities import Entity

SCORE = 0.7

CATEGORIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # type: (Thai keywords, English keywords)
    "SENSITIVE_HEALTH": (
        ("ป่วยเป็น", "เป็นโรค", "โรคเบาหวาน", "เบาหวาน", "มะเร็ง", "ความดันโลหิตสูง", "โรคหัวใจ", "โรคไต",
         "ซึมเศร้า", "ไบโพลาร์", "จิตเภท", "โรคจิต", "เอชไอวี", "เอดส์", "ติดเชื้อ", "ตั้งครรภ์", "แท้ง",
         "ผลตรวจเลือด", "ผลตรวจสุขภาพ", "ผลตรวจโรค", "ผลแล็บ", "วินิจฉัย", "ประวัติการรักษา", "ใบรับรองแพทย์",
         "เวชระเบียน", "ผ่าตัด", "ยาต้านไวรัส", "กรุ๊ปเลือด", "หมู่เลือด", "บำบัดยาเสพติด"),
        ("diagnosed", "diagnosis", "cancer", "diabetes", "depression", "bipolar", "schizophrenia", "hiv",
         "pregnant", "pregnancy", "medical record", "blood test", "surgery"),
    ),
    "SENSITIVE_RELIGION": (
        ("นับถือศาสนา", "ศาสนาพุทธ", "ศาสนาอิสลาม", "ศาสนาคริสต์", "ศาสนาฮินดู", "ศาสนาซิกข์", "ชาวพุทธ",
         "มุสลิม", "คริสเตียน", "ไม่มีศาสนา", "ความเชื่อทางศาสนา"),
        ("religion", "muslim", "christian", "buddhist", "hindu", "atheist"),
    ),
    "SENSITIVE_CRIMINAL": (
        ("ประวัติอาชญากรรม", "ประวัติคดี", "ต้องโทษ", "จำคุก", "ติดคุก", "ถูกจับ", "หมายจับ", "คดีอาญา",
         "ศาลพิพากษา", "พ้นโทษ"),
        ("criminal record", "convicted", "arrested", "arrest warrant", "prison"),
    ),
    "SENSITIVE_DISABILITY": (
        ("ผู้พิการ", "พิการ", "ทุพพลภาพ", "บัตรคนพิการ", "ตาบอด", "หูหนวก", "ออทิสติก", "สมาธิสั้น"),
        ("disability", "disabled", "wheelchair", "autism", "adhd"),
    ),
    "SENSITIVE_BIOMETRIC": (
        ("ลายนิ้วมือ", "สแกนใบหน้า", "ข้อมูลใบหน้า", "จำลองใบหน้า", "ม่านตา", "ลายเสียง"),
        ("fingerprint", "face scan", "facial recognition", "iris scan", "biometric", "voiceprint"),
    ),
    "SENSITIVE_GENETIC": (
        ("ดีเอ็นเอ", "พันธุกรรม", "ผลตรวจยีน"),
        ("dna", "genetic", "genome"),
    ),
    "SENSITIVE_POLITICAL": (
        ("ความคิดเห็นทางการเมือง", "สมาชิกพรรค", "เลือกพรรค", "ฝักใฝ่การเมือง", "แนวคิดทางการเมือง"),
        ("political opinion", "party member", "political affiliation"),
    ),
    "SENSITIVE_UNION": (
        ("สหภาพแรงงาน", "สมาชิกสหภาพ"),
        ("trade union", "labor union", "labour union", "union member"),
    ),
    "SENSITIVE_SEXUAL": (
        ("เพศวิถี", "รสนิยมทางเพศ", "เกย์", "เลสเบี้ยน", "ไบเซ็กชวล", "คนข้ามเพศ", "แปลงเพศ", "พฤติกรรมทางเพศ"),
        ("sexual orientation", "gay", "lesbian", "bisexual", "transgender", "lgbtq"),
    ),
    "SENSITIVE_RACE": (
        ("เชื้อชาติ", "เผ่าพันธุ์", "ชาติพันธุ์"),
        ("ethnicity", "ethnic origin", "race"),
    ),
}

ENTITY_TYPES: tuple[str, ...] = tuple(CATEGORIES)


def _compile(thai: tuple[str, ...], english: tuple[str, ...]) -> re.Pattern[str]:
    thai_part = "|".join(re.escape(k) for k in sorted(thai, key=len, reverse=True))
    english_part = "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in sorted(english, key=len, reverse=True))
    return re.compile(rf"(?:{thai_part})|(?<![A-Za-z])(?:{english_part})(?![A-Za-z])", re.IGNORECASE)


_PATTERNS = {kind: _compile(*words) for kind, words in CATEGORIES.items()}


def detect(text: str) -> list[Entity]:
    found: list[Entity] = []
    for kind, pattern in _PATTERNS.items():
        for m in pattern.finditer(text):
            found.append(Entity(kind, m.start(), m.end(), m.group(0), SCORE))
    return found
