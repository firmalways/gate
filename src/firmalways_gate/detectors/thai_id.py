"""Thai national ID card number (เลขประจำตัวประชาชน 13 หลัก).

Validation uses the official mod-11 check digit: multiply digits 1–12 by
weights 13 down to 2, then ``check = (11 - sum % 11) % 10`` must equal digit 13.

Arabic (0–9) and Thai (๐–๙) digits are both accepted, with optional ``-`` or
space separators in the printed 1-4-5-2-1 grouping.
"""

from __future__ import annotations

import re

from ..entities import Entity
from ._common import DIGIT, digits_only

ENTITY_TYPE = "THAI_NATIONAL_ID"
# A 13-digit juristic-person tax ID (starts with 0) near a tax/company keyword.
# It identifies a company, not a person, so it is reported separately.
TAX_ID_TYPE = "TAX_ID"

_TAX_CONTEXT = re.compile(
    r"(?:เลขประจำตัวผู้เสียภาษี|เลขผู้เสียภาษี|ผู้เสียภาษี|เลขทะเบียนนิติบุคคล|นิติบุคคล|tax\s*id|tin)"
    r"[^0-9๐-๙\n]{0,30}$",
    re.IGNORECASE,
)

_SEP = "[-  ]?"
_PATTERN = re.compile(
    rf"(?<!{DIGIT})"
    rf"{DIGIT}{_SEP}{DIGIT}{{4}}{_SEP}{DIGIT}{{5}}{_SEP}{DIGIT}{{2}}{_SEP}{DIGIT}"
    rf"(?!{DIGIT})"
)


def is_valid_thai_id(value: str) -> bool:
    """Return True if ``value`` contains exactly 13 digits with a valid check digit."""
    digits = digits_only(value)
    if len(digits) != 13:
        return False
    total = sum(int(d) * w for d, w in zip(digits[:12], range(13, 1, -1)))
    return (11 - total % 11) % 10 == int(digits[12])


def detect(text: str, *, require_checksum: bool = True) -> list[Entity]:
    """Find Thai national ID numbers in ``text``.

    With ``require_checksum=False``, 13-digit numbers that fail the checksum are
    also returned with ``score=0.5``: a mistyped ID is still personal data.
    """
    found: list[Entity] = []
    for match in _PATTERN.finditer(text):
        raw = match.group(0)
        valid = is_valid_thai_id(raw)
        if require_checksum and not valid:
            continue
        kind = ENTITY_TYPE
        if digits_only(raw).startswith("0") and _TAX_CONTEXT.search(text, max(0, match.start() - 60), match.start()):
            kind = TAX_ID_TYPE
        found.append(Entity(kind, match.start(), match.end(), raw, 1.0 if valid else 0.5))
    return found
