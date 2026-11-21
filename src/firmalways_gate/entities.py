"""Shared types for detected personal data."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Entity:
    """A span of personal data found in a text.

    ``text`` holds the raw value and is excluded from ``repr`` so that
    logging an entity never leaks the value it describes.
    """

    type: str
    start: int
    end: int
    text: str = field(repr=False)
    score: float = 1.0
