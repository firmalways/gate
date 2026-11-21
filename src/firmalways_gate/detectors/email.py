"""Email addresses. ASCII-only boundaries so ``somchai@example.co.thค่ะ`` still matches."""

from __future__ import annotations

import re

from ..entities import Entity

ENTITY_TYPE = "EMAIL"
SCORE = 1.0

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9][A-Za-z0-9._%+\-]*"
    rf"@{_LABEL}(?:\.{_LABEL})*\.[A-Za-z]{{2,24}}"
    r"(?![A-Za-z0-9\-])"
)


def detect(text: str) -> list[Entity]:
    return [Entity(ENTITY_TYPE, m.start(), m.end(), m.group(0), SCORE) for m in _PATTERN.finditer(text)]
