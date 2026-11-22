"""Thai vehicle registration plates (กข 1234, 1กข 1234) near a plate keyword."""

from __future__ import annotations

import re

from ..entities import Entity

ENTITY_TYPE = "LICENSE_PLATE"
SCORE = 0.85

_CONSONANT = "[ก-ฮ]"
_PATTERN = re.compile(
    r"(?:ป้ายทะเบียน|ทะเบียนรถ|ทะเบียน|license\s+plate|plate\s*(?:no\.?|number)?)"
    r"[^\n0-9ก-ฮ]{0,10}?"
    rf"(?P<value>(?:[0-9]\s?)?{_CONSONANT}{{2}}\s?-?\s?[0-9]{{1,4}})(?![0-9])",
    re.IGNORECASE,
)


def detect(text: str) -> list[Entity]:
    return [
        Entity(ENTITY_TYPE, m.start("value"), m.end("value"), m.group("value"), SCORE)
        for m in _PATTERN.finditer(text)
    ]
