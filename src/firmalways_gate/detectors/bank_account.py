"""Thai bank account numbers.

Two signals:
1. The printed ``XXX-X-XXXXX-X`` format used by most Thai banks (score 0.9).
2. A 10–15 digit number shortly after an account or bank keyword (score 0.85).
"""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import DIGIT

ENTITY_TYPE = "BANK_ACCOUNT"

_FORMATTED = re.compile(rf"(?<!{DIGIT}){DIGIT}{{3}}-{DIGIT}-{DIGIT}{{5}}-{DIGIT}(?!{DIGIT})")

_KEYWORD = (
    r"(?:เลขที่บัญชี|เลขบัญชี|บัญชีเลขที่|บัญชี|บช\.|account\s*(?:no\.?|number|#)?|acct\.?|a/c|"
    r"ธนาคาร|ธ\.ก\.ส\.|กสิกรไทย|กสิกร|ไทยพาณิชย์|กรุงไทย|กรุงศรี|บัวหลวง|ทีทีบี|ออมสิน|"
    r"kbank|scb|ktb|bbl|ttb|krungsri|gsb|baac)"
)
_CONTEXT = re.compile(
    rf"{_KEYWORD}[^0-9๐-๙\n]{{0,30}}?(?P<num>(?<!{DIGIT}){DIGIT}(?:[- ]?{DIGIT}){{9,14}})(?!{DIGIT})",
    re.IGNORECASE,
)


def detect(text: str) -> list[Entity]:
    found = [Entity(ENTITY_TYPE, m.start(), m.end(), m.group(0), 0.9) for m in _FORMATTED.finditer(text)]
    for m in _CONTEXT.finditer(text):
        start, end = m.span("num")
        found.append(Entity(ENTITY_TYPE, start, end, m.group("num"), 0.85))
    return found
