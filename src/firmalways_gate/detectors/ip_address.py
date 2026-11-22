"""IPv4 addresses and full-form IPv6 addresses (compressed ``::`` forms are not covered)."""

from __future__ import annotations

import re

from ..entities import Entity

ENTITY_TYPE = "IP_ADDRESS"
SCORE = 0.75

_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
_IPV4 = re.compile(rf"(?<![0-9.]){_OCTET}(?:\.{_OCTET}){{3}}(?![0-9]|\.[0-9])")
_IPV6 = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}(?![0-9A-Fa-f:])")


def detect(text: str) -> list[Entity]:
    return [
        Entity(ENTITY_TYPE, m.start(), m.end(), m.group(0), SCORE)
        for pattern in (_IPV4, _IPV6)
        for m in pattern.finditer(text)
    ]
