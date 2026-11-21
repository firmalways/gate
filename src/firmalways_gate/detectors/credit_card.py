"""Payment card numbers (13–19 digits) validated with the Luhn checksum."""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import DIGIT, digits_only

ENTITY_TYPE = "CREDIT_CARD"
SCORE = 0.95

_D = DIGIT
_PATTERN = re.compile(
    rf"(?<!{_D})(?:"
    rf"[2-6]{_D}{{12,18}}"  # unseparated
    rf"|[2-6]{_D}{{3}}(?P<sep>[- ]){_D}{{4}}(?P=sep){_D}{{4}}(?P=sep){_D}{{4}}(?:(?P=sep){_D}{{1,3}})?"  # 4-4-4-4
    rf"|3{_D}{{3}}[- ]{_D}{{6}}[- ]{_D}{{5}}"  # Amex 4-6-5
    rf")(?!{_D})"
)


def luhn_valid(value: str) -> bool:
    digits = digits_only(value)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def detect(text: str) -> list[Entity]:
    return [
        Entity(ENTITY_TYPE, m.start(), m.end(), m.group(0), SCORE)
        for m in _PATTERN.finditer(text)
        if luhn_valid(m.group(0))
    ]
