"""Dates of birth written after a birth-date keyword (วันเกิด, เกิดวันที่, DOB ...).

A date of birth together with a name or ID is what lets fraudsters pass identity
checks or pose convincingly as a relative, so it is masked by default.
"""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import DIGIT

ENTITY_TYPE = "DATE_OF_BIRTH"
SCORE = 0.85

_D = DIGIT
_THAI_MONTH = (
    r"(?:มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม|"
    r"ม\.ค\.|ก\.พ\.|มี\.ค\.|เม\.ย\.|พ\.ค\.|มิ\.ย\.|ก\.ค\.|ส\.ค\.|ก\.ย\.|ต\.ค\.|พ\.ย\.|ธ\.ค\.)"
)
_EN_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE = (
    rf"(?:{_D}{{1,2}}\s*[/\-.]\s*{_D}{{1,2}}\s*[/\-.]\s*{_D}{{2,4}}"
    rf"|{_D}{{4}}-{_D}{{2}}-{_D}{{2}}"
    rf"|{_D}{{1,2}}\s*{_THAI_MONTH}\s*(?:พ\.ศ\.\s*|ค\.ศ\.\s*)?{_D}{{2,4}}"
    rf"|{_D}{{1,2}}\s+{_EN_MONTH}\s+{_D}{{4}}"
    rf"|{_EN_MONTH}\s+{_D}{{1,2}},?\s+{_D}{{4}})"
)
_PATTERN = re.compile(
    r"(?:วัน\s*/?\s*เดือน\s*/?\s*ปี\s*เกิด|ว\s*/\s*ด\s*/\s*ป\s*เกิด|วันเกิด|เกิดวันที่|เกิดเมื่อ|"
    r"date\s+of\s+birth|d\.?o\.?b\.?|birthday|born\s+on)"
    rf"\s*(?:คือ|is)?\s*[:：]?\s*(?P<value>{_DATE})(?![0-9๐-๙])",
    re.IGNORECASE,
)


def detect(text: str) -> list[Entity]:
    return [
        Entity(ENTITY_TYPE, m.start("value"), m.end("value"), m.group("value"), SCORE)
        for m in _PATTERN.finditer(text)
    ]
