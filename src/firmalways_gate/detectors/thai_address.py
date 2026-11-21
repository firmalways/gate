"""Thai postal addresses.

Finds address components (เลขที่, หมู่, ซอย, ถนน, ตำบล/แขวง, อำเภอ/เขต, จังหวัด,
postal code) and reports runs of at least two adjacent components as one
address. A single component such as "เขตพื้นที่" or a five-digit number is not
reported on its own.
"""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import DIGIT
from ._common import THAI_LETTER as T

ENTITY_TYPE = "THAI_ADDRESS"

_NUM = rf"{DIGIT}+(?:/{DIGIT}+)?"
_COMPONENT = re.compile(
    "|".join(
        (
            rf"(?:บ้านเลขที่|เลขที่)\s*{_NUM}",
            rf"หมู่บ้าน\s*{T}+",
            rf"(?:หมู่ที่|หมู่|ม\.)\s*{DIGIT}{{1,3}}",
            rf"(?:ซอย|ซ\.)\s*(?:{T}+(?:\s*{_NUM})?|{_NUM})",
            rf"(?:ถนน|ถ\.)\s*{T}+",
            rf"(?:ตำบล|แขวง|ต\.)\s*{T}+",
            rf"(?:อำเภอ|เขต|อ\.)\s*{T}+",
            rf"(?:จังหวัด|จ\.)\s*{T}+",
            r"กรุงเทพมหานคร|กรุงเทพฯ|กทม\.?",
            rf"(?<!{DIGIT})[1-9]{DIGIT}{{4}}(?!{DIGIT})",
        )
    )
)
_GAP = re.compile(r"[\s,]{0,3}")


def detect(text: str) -> list[Entity]:
    groups: list[list[int]] = []  # [start, end, component_count]
    for m in _COMPONENT.finditer(text):
        start, end = m.span()
        if groups and _GAP.fullmatch(text[groups[-1][1] : start]):
            groups[-1][1] = end
            groups[-1][2] += 1
        else:
            groups.append([start, end, 1])
    return [
        Entity(ENTITY_TYPE, start, end, text[start:end], 0.7 if count >= 3 else 0.6)
        for start, end, count in groups
        if count >= 2
    ]
