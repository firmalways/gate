"""Run every detector over a text and resolve overlapping matches."""

from __future__ import annotations

from collections.abc import Iterable

from .detectors import bank_account, credit_card, email, phone, secret, thai_address, thai_id, thai_name
from .entities import Entity

ENTITY_TYPES: tuple[str, ...] = (
    thai_id.ENTITY_TYPE,
    phone.ENTITY_TYPE,
    email.ENTITY_TYPE,
    bank_account.ENTITY_TYPE,
    credit_card.ENTITY_TYPE,
    secret.ENTITY_TYPE,
    thai_name.ENTITY_TYPE,
    thai_address.ENTITY_TYPE,
)

_OTHER_DETECTORS = (phone, email, bank_account, credit_card, secret, thai_name, thai_address)


def analyze(
    text: str,
    *,
    min_score: float = 0.5,
    lenient_thai_id: bool = True,
    entity_types: Iterable[str] | None = None,
) -> list[Entity]:
    """Return non-overlapping entities found in ``text``, ordered by position."""
    found = thai_id.detect(text, require_checksum=not lenient_thai_id)
    for detector in _OTHER_DETECTORS:
        found.extend(detector.detect(text))
    wanted = None if entity_types is None else frozenset(entity_types)
    found = [e for e in found if e.score >= min_score and (wanted is None or e.type in wanted)]
    return resolve_overlaps(found)


def resolve_overlaps(entities: Iterable[Entity]) -> list[Entity]:
    """Keep the longest span, then the highest score, among overlapping entities."""
    chosen: list[Entity] = []
    for entity in sorted(entities, key=lambda e: (-(e.end - e.start), -e.score, e.start)):
        if all(entity.end <= c.start or entity.start >= c.end for c in chosen):
            chosen.append(entity)
    return sorted(chosen, key=lambda e: e.start)
