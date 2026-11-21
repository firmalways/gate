"""Person names introduced by a title (นาย, นางสาว, คุณ, ด.ช., Mr. ...).

This is a rule-based heuristic, not NER. Only the name is reported; the title
stays visible so the AI can still write grammatical Thai ("นาย«PERSON_1»").

Known limits: names without a title are missed, a first name longer than 20
letters written without a following space is missed, and names that begin with
a common word in the stop lists below are missed. Thai NER is planned as an
optional extra.
"""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import THAI_LETTER as T

ENTITY_TYPE = "PERSON"

_FORMAL = (
    "เด็กชาย", "เด็กหญิง", "ด.ช.", "ด.ญ.", "นางสาว", "น.ส.", "นายแพทย์", "แพทย์หญิง",
    "นพ.", "พญ.", "ดร.", "คุณหญิง", "นาง", "นาย",
)
_CASUAL = ("คุณ",)
_TITLES = "|".join(re.escape(t) for t in sorted(_FORMAL + _CASUAL, key=len, reverse=True))

_THAI = re.compile(
    rf"(?P<title>{_TITLES})[  ]?(?P<first>{T}{{2,20}})(?!{T})"
    rf"(?:[  ](?P<last>{T}{{2,25}})(?!{T}))?"
)
_ENGLISH = re.compile(
    r"(?<![A-Za-z])(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+(?P<first>[A-Z][a-z]+)(?:\s+(?P<last>[A-Z][a-z]+))?"
)

# Text right before a title that means the title is part of another word:
# ขอบคุณ (thank you), บุญคุณ, พระคุณ, ทนาย (lawyer), ทำนาย (predict).
_BLOCK_BEFORE = {"คุณ": ("ขอบ", "บุญ", "พระ"), "นาย": ("ท", "ทำ")}

# Words that follow a title but are not names.
_FORMAL_STOP_EXACT = frozenset({"ก", "พล", "ทุน", "ช่าง", "ด่าน", "ท่าน", "ร้อย", "สิบ", "พัน", "พราน",
                                "ห้าง", "งาน", "เรือ", "ฟ้า", "งาม", "เอก", "รำ"})
_FORMAL_STOP_PREFIX = ("จ้าง", "หน้า", "กรัฐ", "กเทศ", "อำเภอ", "ประกัน", "ทะเบียน", "ตรวจ", "ธนาคาร",
                       "ความ", "แบบ", "พยาบาล", "กวัก", "สนม", "ร้าย", "เงือก", "ข้าหลวง")
_CASUAL_STOP_PREFIX = (
    "ภาพ", "ค่า", "สมบัติ", "ประโยชน์", "ธรรม", "ลักษณะ", "วุฒิ", "ูป", "ครับ", "ค่ะ", "คะ", "นะ",
    "ช่วย", "คิด", "เป็น", "จะ", "มี", "ได้", "สามารถ", "ควร", "ต้อง", "อยาก", "ทำ", "รู้", "เห็น",
    "ชอบ", "ไม่", "ก็", "เคย", "กำลัง", "ยัง", "อาจ", "ว่า", "บอก", "ใช้", "ลอง", "ขอ", "ให้", "คือ",
    "เลือก", "ดู", "อ่าน", "ส่ง", "เขียน", "ถาม", "ตอบ", "และ", "กับ", "ทุก", "เอง", "ที่", "สำหรับ",
    "จริง", "มาก", "ลูกค้า", "ผู้", "แม่", "พ่อ", "ครู", "หมอ", "ป้า", "ลุง", "ยาย", "ปู่", "ย่า",
    "น้า", "พี่", "น้อง", "ต่อ", "ไป",
)
_SURNAME_STOP_PREFIX = (
    "เลข", "โทร", "อายุ", "ที่", "ตำแหน่ง", "รหัส", "เบอร์", "อีเมล", "เป็น", "ได้", "มา", "ไป", "จะ",
    "และ", "กับ", "ซึ่ง", "ผู้", "ขอ", "ช่วย", "แจ้ง", "ทำ", "มี", "ใน", "จาก", "ถึง", "ให้", "ว่า",
    "บ้าน", "หมู่", "ถนน", "ซอย", "ตำบล", "อำเภอ", "จังหวัด", "แผนก", "ฝ่าย", "ค้าง", "ยอด", "ครับ",
    "ค่ะ", "คะ", "นะ", "เรื่อง", "เพื่อ", "แล้ว", "ด้วย", "หรือ", "บัตร", "บัญชี", "ลูกค้า", "พนักงาน",
    "วันที่", "เมื่อ", "ซื้อ", "จ่าย", "โอน", "ส่ง", "ติดต่อ", "รหัสผ่าน",
)


def _is_name(title: str, first: str, text_before: str) -> bool:
    if any(text_before.endswith(b) for b in _BLOCK_BEFORE.get(title, ())):
        return False
    if title in _CASUAL:
        return not first.startswith(_CASUAL_STOP_PREFIX)
    return first not in _FORMAL_STOP_EXACT and not first.startswith(_FORMAL_STOP_PREFIX)


def detect(text: str) -> list[Entity]:
    found: list[Entity] = []
    for m in _THAI.finditer(text):
        title, first, last = m.group("title"), m.group("first"), m.group("last")
        if not _is_name(title, first, text[: m.start()]):
            continue
        start = m.start("first")
        end = m.end("last") if last and not last.startswith(_SURNAME_STOP_PREFIX) else m.end("first")
        score = 0.6 if title in _CASUAL else 0.75
        found.append(Entity(ENTITY_TYPE, start, end, text[start:end], score))
    for m in _ENGLISH.finditer(text):
        start = m.start("first")
        end = m.end("last") if m.group("last") else m.end("first")
        found.append(Entity(ENTITY_TYPE, start, end, text[start:end], 0.7))
    return found
