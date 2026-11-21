"""Character classes and helpers shared by detectors.

Thai is written without spaces between words and Python's ``\\w``/``\\b`` treat
Thai letters as word characters, so detectors use explicit ASCII or digit
look-arounds instead of ``\\b``.
"""

from __future__ import annotations

import re

DIGIT = "[0-9๐-๙]"
# Thai letters and vowel/tone marks, excluding the baht sign (U+0E3F) and Thai digits.
THAI_LETTER = "[ก-ฺเ-๎]"
THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

_NON_DIGIT = re.compile(r"[^0-9๐-๙]")


def digits_only(value: str) -> str:
    """Return only the digits of ``value``, with Thai digits converted to 0–9."""
    return _NON_DIGIT.sub("", value).translate(THAI_TO_ARABIC)
