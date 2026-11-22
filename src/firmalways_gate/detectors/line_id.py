"""LINE IDs written after a LINE label (ไลน์, ไอดีไลน์, LINE ID:, line:)."""

from __future__ import annotations

import re

from ..entities import Entity

ENTITY_TYPE = "LINE_ID"
SCORE = 0.85

_PATTERN = re.compile(
    r"(?:ไอดีไลน์|ไลน์ไอดี|ไลน์|(?<![A-Za-z])line\s*id|(?<![A-Za-z])line(?=\s*[:：]))"
    r"\s*[:：]?\s*"
    r"(?P<value>@?[A-Za-z0-9][A-Za-z0-9._\-]{2,29})(?![A-Za-z0-9._\-])",
    re.IGNORECASE,
)


def detect(text: str) -> list[Entity]:
    found = []
    for m in _PATTERN.finditer(text):
        value = m.group("value")
        if value.startswith("@") or any(c.isalpha() for c in value):
            found.append(Entity(ENTITY_TYPE, m.start("value"), m.end("value"), value, SCORE))
    return found
