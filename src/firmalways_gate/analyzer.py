"""Run every detector over a text and resolve overlapping matches."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .detectors import (
    bank_account,
    credit_card,
    email,
    ip_address,
    line_id,
    license_plate,
    passport,
    phone,
    secret,
    sensitive,
    thai_address,
    thai_id,
    thai_name,
)
from .entities import Entity

# Types that identify a person. PDPA section 26 sensitive data is reported only
# when one of these appears in the same text.
IDENTIFIER_TYPES: frozenset[str] = frozenset(
    {
        thai_id.ENTITY_TYPE,
        phone.ENTITY_TYPE,
        email.ENTITY_TYPE,
        bank_account.ENTITY_TYPE,
        credit_card.ENTITY_TYPE,
        thai_name.ENTITY_TYPE,
        thai_address.ENTITY_TYPE,
        passport.ENTITY_TYPE,
        license_plate.ENTITY_TYPE,
        line_id.ENTITY_TYPE,
    }
)

ENTITY_TYPES: tuple[str, ...] = (
    thai_id.ENTITY_TYPE,
    thai_id.TAX_ID_TYPE,
    phone.ENTITY_TYPE,
    email.ENTITY_TYPE,
    bank_account.ENTITY_TYPE,
    credit_card.ENTITY_TYPE,
    secret.ENTITY_TYPE,
    thai_name.ENTITY_TYPE,
    thai_address.ENTITY_TYPE,
    passport.ENTITY_TYPE,
    license_plate.ENTITY_TYPE,
    line_id.ENTITY_TYPE,
    ip_address.ENTITY_TYPE,
    *sensitive.ENTITY_TYPES,
)

_OTHER_DETECTORS = (phone, email, bank_account, credit_card, secret, thai_name, thai_address, passport,
                    license_plate, line_id, ip_address)

# Optional extra detectors (for example Thai NER) registered at runtime.
_EXTRA_DETECTORS: list[Callable[[str], list[Entity]]] = []


def register_detector(detector: Callable[[str], list[Entity]]) -> None:
    if detector not in _EXTRA_DETECTORS:
        _EXTRA_DETECTORS.append(detector)


def unregister_detector(detector: Callable[[str], list[Entity]]) -> None:
    if detector in _EXTRA_DETECTORS:
        _EXTRA_DETECTORS.remove(detector)


def analyze(
    text: str,
    *,
    min_score: float = 0.5,
    lenient_thai_id: bool = True,
    entity_types: Iterable[str] | None = None,
    sensitive_requires_identifier: bool = True,
) -> list[Entity]:
    """Return non-overlapping entities found in ``text``, ordered by position."""
    found = thai_id.detect(text, require_checksum=not lenient_thai_id)
    for detector in _OTHER_DETECTORS:
        found.extend(detector.detect(text))
    for extra in _EXTRA_DETECTORS:
        found.extend(extra(text))
    found = [e for e in found if e.score >= min_score]
    identified = any(e.type in IDENTIFIER_TYPES for e in found)
    if identified or not sensitive_requires_identifier:
        flagged = [e for e in sensitive.detect(text) if e.score >= min_score]
        found = [_trim_name(e, flagged, text) for e in found] + flagged
    if entity_types is not None:
        wanted = frozenset(entity_types)
        found = [e for e in found if e.type in wanted]
    return resolve_overlaps(found)


def _trim_name(entity: Entity, flagged: list[Entity], text: str) -> Entity:
    """A title-based name may swallow following words ("นายสมชาย ป่วยเป็นมะเร็ง").

    Cut the name before the first sensitive keyword inside it, so the sensitive
    term is reported (and can be blocked) instead of hidden inside the name.
    """
    if entity.type != thai_name.ENTITY_TYPE:
        return entity
    cuts = [s.start for s in flagged if entity.start < s.start < entity.end]
    if not cuts:
        return entity
    end = min(cuts)
    while end > entity.start and text[end - 1].isspace():
        end -= 1
    return Entity(entity.type, entity.start, end, text[entity.start : end], entity.score)


def resolve_overlaps(entities: Iterable[Entity]) -> list[Entity]:
    """Keep the longest span, then the highest score, among overlapping entities."""
    chosen: list[Entity] = []
    for entity in sorted(entities, key=lambda e: (-(e.end - e.start), -e.score, e.start)):
        if all(entity.end <= c.start or entity.start >= c.end for c in chosen):
            chosen.append(entity)
    return sorted(chosen, key=lambda e: e.start)
