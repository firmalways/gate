"""Thai phone numbers: mobile (06/08/09, 10 digits) and landline (02–05/07, 9 digits).

Accepts ``0`` or ``+66`` prefixes and ``-``, ``.`` or space separators.
"""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import DIGIT

ENTITY_TYPE = "PHONE"
SCORE = 0.8

_S = "[-.  ]?"
_PATTERN = re.compile(
    rf"(?<![0-9๐-๙+])"
    rf"(?:\(\+66\)|\+66|0|๐)"
    rf"{_S}"
    rf"(?:[689๖๘๙](?:{_S}{DIGIT}){{8}}|[2-57๒-๕๗](?:{_S}{DIGIT}){{7}})"
    rf"(?!{DIGIT})"
)


def detect(text: str) -> list[Entity]:
    return [Entity(ENTITY_TYPE, m.start(), m.end(), m.group(0), SCORE) for m in _PATTERN.finditer(text)]
