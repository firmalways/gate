"""Optional Thai named-entity recognition for person names (PyThaiNLP).

Finds names written without a title ("ส่งรายงานให้สมชายตรวจ"), which the
rule-based ``thai_name`` detector cannot. Enable with
``[detection] thai_ner = true`` after ``pip install "firmalways-gate[thai-ner]"``.

PyThaiNLP downloads its ``thainer`` model on first use. For an offline
deployment, run Gate once with network access, or pre-load the corpus with
``thainlp data get thainer``. The model runs locally; no text leaves the machine.
"""

from __future__ import annotations

from ..entities import Entity
from .thai_name import _CASUAL, _FORMAL

ENTITY_TYPE = "PERSON"
SCORE = 0.65
INSTALL_HINT = 'Thai NER needs PyThaiNLP: pip install "firmalways-gate[thai-ner]"'

_PREFIXES = tuple(sorted(_FORMAL + _CASUAL + ("ลูกค้า", "พนักงาน", "ผู้ป่วย", "คนไข้", "พี่", "น้อง"), key=len, reverse=True))


class ThaiNER:
    """Callable detector: ``ThaiNER()(text) -> list[Entity]``."""

    def __init__(self, engine: str = "thainer", tagger=None) -> None:
        if tagger is not None:  # any object with .tag(text, pos=False) -> [(word, tag)], used in tests
            self._ner = tagger
            return
        try:
            from pythainlp.tag import NER
        except ImportError as exc:
            raise ImportError(INSTALL_HINT) from exc
        self._ner = NER(engine=engine)

    def __call__(self, text: str) -> list[Entity]:
        spans: list[list[int]] = []
        current: list[int] | None = None
        pos = 0
        for word, tag in self._ner.tag(text, pos=False):
            index = text.find(word, pos)
            if index < 0:
                current = None
                continue
            start, end = index, index + len(word)
            pos = end
            if tag == "B-PERSON" or (tag == "I-PERSON" and current is None):
                current = [start, end]
                spans.append(current)
            elif tag == "I-PERSON" and current is not None:
                current[1] = end
            else:
                current = None
        found: list[Entity] = []
        for start, end in spans:
            start, end = _trim(text, start, end)
            if end - start >= 2:
                found.append(Entity(ENTITY_TYPE, start, end, text[start:end], SCORE))
        return found


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Drop titles and role words the model includes ("ลูกค้าคุณมีนา" → "มีนา") and edge spaces."""
    changed = True
    while changed:
        changed = False
        while start < end and text[start].isspace():
            start += 1
        for prefix in _PREFIXES:
            if text.startswith(prefix, start) and end - start > len(prefix) + 1:
                start += len(prefix)
                changed = True
                break
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
