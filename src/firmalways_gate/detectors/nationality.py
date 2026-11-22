"""Nationality written on Thai ID cards and forms (สัญชาติไทย, nationality: Thai).

Like PDPA section 26 data, it is reported only when the same text also
identifies a person, so a general question about nationality is not masked.
"""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import THAI_LETTER as T

ENTITY_TYPE = "NATIONALITY"
SCORE = 0.7

_PATTERN = re.compile(
    rf"(?P<th>สัญชาติ\s*{T}{{2,15}})(?!{T})|(?<![A-Za-z])nationality\s*[:：]?\s*(?P<en>[A-Z][a-z]{{2,20}})",
    re.IGNORECASE,
)


def detect(text: str) -> list[Entity]:
    found = []
    for m in _PATTERN.finditer(text):
        group = "th" if m.group("th") else "en"
        found.append(Entity(ENTITY_TYPE, m.start(group), m.end(group), m.group(group), SCORE))
    return found
