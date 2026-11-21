"""Reversible placeholders: replace values before sending, restore them in the answer.

One :class:`Pseudonymizer` lives for one request and only in memory. The same
value gets the same placeholder (``«PHONE_1»``) everywhere in that request.
Chat clients resend the whole history on every turn, so placeholders stay
consistent across turns without storing anything between requests.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from .detectors._common import THAI_TO_ARABIC
from .entities import Entity

_STRIP = re.compile(r"[\s\-.()+ ]")
_TOKEN_CHAR = re.compile(r"[A-Z0-9_]")
MAX_HOLD = 64


def _key(entity: Entity) -> tuple[str, str]:
    value = _STRIP.sub("", entity.text).translate(THAI_TO_ARABIC).casefold()
    if entity.type == "PHONE" and value.startswith("66"):
        value = "0" + value[2:]
    return entity.type, value


class Pseudonymizer:
    def __init__(self) -> None:
        self._token_by_key: dict[tuple[str, str], str] = {}
        self._value_by_token: dict[str, str] = {}
        self._counters: Counter[str] = Counter()
        self._restore_re: re.Pattern[str] | None = None

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(self._value_by_token)

    def placeholder_for(self, entity: Entity) -> str:
        key = _key(entity)
        token = self._token_by_key.get(key)
        if token is None:
            self._counters[entity.type] += 1
            token = f"{entity.type}_{self._counters[entity.type]}"
            self._token_by_key[key] = token
            self._value_by_token[token] = entity.text
            self._restore_re = None
        return f"«{token}»"

    def mask(self, text: str, entities: Iterable[Entity]) -> str:
        """Replace each entity span in ``text`` with its placeholder."""
        parts: list[str] = []
        pos = 0
        for entity in sorted(entities, key=lambda e: e.start):
            if entity.start < pos:
                raise ValueError("entities overlap; resolve them before masking")
            parts.append(text[pos : entity.start])
            parts.append(self.placeholder_for(entity))
            pos = entity.end
        parts.append(text[pos:])
        return "".join(parts)

    def restore(self, text: str) -> str:
        """Put real values back. Accepts ``«TOKEN»``, spaced ``« TOKEN »`` and bare ``TOKEN``.

        Placeholders this request did not create are left unchanged.
        """
        if not self._value_by_token or not text:
            return text
        if self._restore_re is None:
            alternatives = "|".join(re.escape(t) for t in sorted(self._value_by_token, key=len, reverse=True))
            self._restore_re = re.compile(
                rf"«\s*(?P<wrapped>{alternatives})\s*»|(?<![A-Za-z0-9_])(?P<bare>{alternatives})(?![A-Za-z0-9_])"
            )
        return self._restore_re.sub(lambda m: self._value_by_token[m.group("wrapped") or m.group("bare")], text)

    def stream_restorer(self) -> StreamRestorer:
        return StreamRestorer(self)


class StreamRestorer:
    """Restore placeholders in streamed text where a placeholder may span chunks.

    Holds back a possible partial placeholder (an unclosed ``«`` or a trailing
    run of ``A-Z0-9_``) until the next chunk, up to ``MAX_HOLD`` characters.
    """

    def __init__(self, pseudonymizer: Pseudonymizer) -> None:
        self._p = pseudonymizer
        self._buffer = ""

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        cut = _safe_cut(self._buffer)
        ready, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return self._p.restore(ready)

    def flush(self) -> str:
        ready, self._buffer = self._buffer, ""
        return self._p.restore(ready)

    @property
    def pending(self) -> bool:
        return bool(self._buffer)


def _safe_cut(text: str) -> int:
    opened = text.rfind("«")
    if opened != -1 and "»" not in text[opened:] and len(text) - opened <= MAX_HOLD:
        return opened
    end = len(text)
    while end > 0 and _TOKEN_CHAR.match(text[end - 1]):
        end -= 1
    return end if len(text) - end <= MAX_HOLD else len(text)
