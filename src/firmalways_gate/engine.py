"""Apply a policy to text and OpenAI-style chat messages."""

from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .analyzer import analyze
from .entities import Entity
from .files import FileNotSupported, decode_data_url, extract_text
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
    allowed: Counter[str] = field(default_factory=Counter)
    file_parts: int = 0

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_types)


class Gate:
    def __init__(self, policy: Policy | None = None) -> None:
        self.policy = policy or Policy()

    def analyze(self, text: str) -> list[Entity]:
        return analyze(
            text,
            min_score=self.policy.min_score,
            lenient_thai_id=self.policy.lenient_thai_id,
            sensitive_requires_identifier=self.policy.sensitive_requires_identifier,
        )

    def scan_response(self, text: str, pseudonymizer: Pseudonymizer, redacted: Counter[str] | None = None) -> str:
        """Redact values in an AI answer that were not in the request, per ``[response]`` policy."""
        if not self.policy.response_scan or not text:
            return text
        to_redact = [
            e
            for e in self.analyze(text)
            if not pseudonymizer.knows(e) and self.policy.response_action_for(e.type) == "mask"
        ]
        if redacted is not None:
            redacted.update(e.type for e in to_redact)
        return redact(text, to_redact)

    def response_scanner(self, pseudonymizer: Pseudonymizer, redacted: Counter[str]) -> ResponseScanner:
        return ResponseScanner(self, pseudonymizer, redacted)

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
            else:
                protection.allowed[entity.type] += 1
                pseudonymizer.note(entity)
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
                    elif part.get("type") == "file" and self.policy.files == "extract":
                        text = self._file_text(part)
                        masked, _ = self.protect_text(text, pseudonymizer, protection)
                        name = (part.get("file") or {}).get("filename") or "file"
                        part.clear()
                        part.update({"type": "text", "text": f"[ไฟล์แนบ: {name}]\n{masked}"})
                        protection.file_parts += 1
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

    @staticmethod
    def _file_text(part: dict[str, Any]) -> str:
        file = part.get("file")
        if not isinstance(file, dict) or not isinstance(file.get("file_data"), str):
            raise ContentNotAllowed("file parts must carry inline file_data; uploaded file_id cannot be inspected")
        try:
            mime, data = decode_data_url(file["file_data"])
            return extract_text(str(file.get("filename") or ""), mime, data)
        except FileNotSupported as exc:
            raise ContentNotAllowed(str(exc)) from exc

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


def redact(text: str, entities: list[Entity]) -> str:
    """Replace entity spans with ``«REDACTED_TYPE»`` (not restorable)."""
    parts: list[str] = []
    pos = 0
    for entity in sorted(entities, key=lambda e: e.start):
        parts.append(text[pos : entity.start])
        parts.append(f"«REDACTED_{entity.type}»")
        pos = entity.end
    parts.append(text[pos:])
    return "".join(parts)


class ResponseScanner:
    """Redact new personal data from streamed answer text.

    Holds back the last ``HOLD`` characters (and any entity crossing that point)
    so a value split across chunks is still seen whole. This delays streamed
    output by up to ``HOLD`` characters.
    """

    HOLD = 200

    def __init__(self, gate: Gate, pseudonymizer: Pseudonymizer, redacted: Counter[str]) -> None:
        self._gate = gate
        self._p = pseudonymizer
        self._redacted = redacted
        self._buffer = ""

    @property
    def pending(self) -> bool:
        return bool(self._buffer)

    def feed(self, text: str) -> str:
        self._buffer += text
        if len(self._buffer) <= self.HOLD:
            return ""
        cut = len(self._buffer) - self.HOLD
        entities = self._gate.analyze(self._buffer)
        for entity in entities:
            if entity.start < cut < entity.end:
                cut = entity.start
        ready, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return self._gate.scan_response(ready, self._p, self._redacted)

    def flush(self) -> str:
        ready, self._buffer = self._buffer, ""
        return self._gate.scan_response(ready, self._p, self._redacted)


def restore_completion(data: Any, pseudonymizer: Pseudonymizer, gate: Gate | None = None,
                       redacted: Counter[str] | None = None) -> Any:
    """Restore placeholders in a non-streaming chat completion, in place.

    With ``gate``, also redact new personal data from the answer per ``[response]`` policy.
    """
    if not isinstance(data, dict):
        return data

    def fix(text: str) -> str:
        text = pseudonymizer.restore(text)
        return gate.scan_response(text, pseudonymizer, redacted) if gate is not None else text

    for choice in data.get("choices") or []:
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = fix(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    part["text"] = fix(part["text"])
        for call in message.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict) and isinstance(function.get("arguments"), str):
                function["arguments"] = fix(function["arguments"])
    return data
