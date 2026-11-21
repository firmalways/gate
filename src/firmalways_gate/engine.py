"""Apply a policy to text and OpenAI-style chat messages."""

from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .analyzer import analyze
from .entities import Entity
from .policy import Policy
from .pseudonymize import Pseudonymizer


class ContentNotAllowed(ValueError):
    """The request contains content Gate cannot inspect (images, files) and policy forbids it."""


@dataclass
class Protection:
    """What Gate found and did. Contains counts only, never values."""

    counts: Counter[str] = field(default_factory=Counter)
    blocked_types: set[str] = field(default_factory=set)
    masked: int = 0

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_types)


class Gate:
    def __init__(self, policy: Policy | None = None) -> None:
        self.policy = policy or Policy()

    def analyze(self, text: str) -> list[Entity]:
        return analyze(text, min_score=self.policy.min_score, lenient_thai_id=self.policy.lenient_thai_id)

    def protect_text(
        self, text: str, pseudonymizer: Pseudonymizer, protection: Protection | None = None
    ) -> tuple[str, Protection]:
        """Mask ``text`` according to policy. Blocked types are recorded, not masked."""
        protection = protection if protection is not None else Protection()
        to_mask: list[Entity] = []
        for entity in self.analyze(text):
            protection.counts[entity.type] += 1
            action = self.policy.action_for(entity.type)
            if action == "block":
                protection.blocked_types.add(entity.type)
            elif action == "mask":
                to_mask.append(entity)
        protection.masked += len(to_mask)
        return pseudonymizer.mask(text, to_mask), protection

    def protect_messages(
        self, messages: list[Any], pseudonymizer: Pseudonymizer
    ) -> tuple[list[dict[str, Any]], Protection]:
        """Return a masked deep copy of chat ``messages``.

        Raises :class:`ContentNotAllowed` for non-text parts unless policy allows
        them, and ``TypeError`` for malformed messages.
        """
        protection = Protection()
        result: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, dict):
                raise TypeError("each message must be an object")
            message = copy.deepcopy(message)
            content = message.get("content")
            if isinstance(content, str):
                message["content"], _ = self.protect_text(content, pseudonymizer, protection)
            elif isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        raise TypeError("content parts must be objects")
                    if part.get("type") == "text" and isinstance(part.get("text"), str):
                        part["text"], _ = self.protect_text(part["text"], pseudonymizer, protection)
                    elif not self.policy.allow_non_text:
                        raise ContentNotAllowed(f"content part of type {part.get('type')!r} cannot be inspected")
            elif content is not None:
                raise TypeError("message content must be a string, a list of parts or null")
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                if isinstance(function, dict) and isinstance(function.get("arguments"), str):
                    function["arguments"], _ = self.protect_text(function["arguments"], pseudonymizer, protection)
            result.append(message)
        return result, protection

    def preview(self, text: str) -> dict[str, Any]:
        """Show what an AI provider would receive for ``text``, without calling it."""
        pseudonymizer = Pseudonymizer()
        entities = self.analyze(text)
        masked, protection = self.protect_text(text, pseudonymizer)
        items = []
        for entity in entities:
            action = self.policy.action_for(entity.type)
            item = {"type": entity.type, "start": entity.start, "end": entity.end, "score": entity.score, "action": action}
            if action == "mask":
                item["placeholder"] = pseudonymizer.placeholder_for(entity)
            items.append(item)
        return {
            "masked_text": masked,
            "entities": items,
            "blocked_types": sorted(protection.blocked_types),
            "would_forward": not protection.blocked,
        }


def restore_completion(data: Any, pseudonymizer: Pseudonymizer) -> Any:
    """Restore placeholders in a non-streaming chat completion response, in place."""
    if not isinstance(data, dict):
        return data
    for choice in data.get("choices") or []:
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = pseudonymizer.restore(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    part["text"] = pseudonymizer.restore(part["text"])
        for call in message.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict) and isinstance(function.get("arguments"), str):
                function["arguments"] = pseudonymizer.restore(function["arguments"])
    return data
