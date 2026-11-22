"""Passport numbers (1–2 letters followed by 6–8 digits) near a passport keyword."""

from __future__ import annotations

import re

from ..entities import Entity

ENTITY_TYPE = "PASSPORT"
SCORE = 0.85

_PATTERN = re.compile(
    r"(?:หนังสือเดินทาง|พาสปอร์ต|passport(?:\s*(?:no\.?|number|#))?)"
    r"[^A-Za-z0-9\n]{0,20}?"
    r"(?P<value>(?<![A-Za-z0-9])[A-Za-z]{1,2}[0-9]{6,8})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def detect(text: str) -> list[Entity]:
    return [
        Entity(ENTITY_TYPE, m.start("value"), m.end("value"), m.group("value"), SCORE)
        for m in _PATTERN.finditer(text)
    ]
