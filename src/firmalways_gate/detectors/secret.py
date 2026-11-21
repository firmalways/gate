"""Credentials that must never reach an AI provider: API keys, tokens, private keys, passwords."""

from __future__ import annotations

import re

from ..entities import Entity

ENTITY_TYPE = "SECRET"

# (pattern, group to report or 0 for the whole match, score)
_PATTERNS: tuple[tuple[re.Pattern[str], int | str, float], ...] = (
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z0-9 ]*PRIVATE KEY-----"), 0, 1.0),
    (re.compile(r"(?<![A-Za-z0-9_\-])sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"), 0, 1.0),  # OpenAI / Anthropic
    (re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"), 0, 1.0),  # AWS access key id
    (re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{36,}"), 0, 1.0),  # GitHub
    (re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{22,}"), 0, 1.0),
    (re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9\-]{10,}"), 0, 1.0),  # Slack
    (re.compile(r"(?<![A-Za-z0-9_\-])AIza[0-9A-Za-z_\-]{35}"), 0, 1.0),  # Google API key
    (re.compile(r"(?<![A-Za-z0-9])[rs]k_live_[0-9A-Za-z]{20,}"), 0, 1.0),  # Stripe live key
    (re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), 0, 1.0),  # JWT
    (
        re.compile(
            r"(?:password|passwd|pwd|รหัสผ่าน|พาสเวิร์ด)\s*(?:[:=]|คือ|is)\s*[\"']?(?P<value>[^\s\"',;]{4,})",
            re.IGNORECASE,
        ),
        "value",
        0.9,
    ),
)


def detect(text: str) -> list[Entity]:
    found: list[Entity] = []
    for pattern, group, score in _PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.span(group)
            found.append(Entity(ENTITY_TYPE, start, end, text[start:end], score))
    return found
