"""Content-free audit log (JSON Lines).

Each record says who (an HMAC of the user id, if a key is configured), when,
which model, how many of each data type were found and what Gate did. It never
contains prompt text, answer text, placeholder mappings or raw values.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HMAC_KEY_ENV = "FIRMALWAYS_AUDIT_HMAC_KEY"

_ALLOWED_FIELDS = frozenset(
    {"request_id", "user", "model", "upstream", "action", "status", "reason", "entities", "masked", "latency_ms", "stream"}
)


class AuditLog:
    """Append audit records to ``path`` (``"-"`` for stdout, ``None`` to disable)."""

    def __init__(self, path: str | None = None, hmac_key: bytes | None = None) -> None:
        self.path = path
        self._key = hmac_key
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, path: str | None) -> AuditLog:
        key = os.environ.get(HMAC_KEY_ENV)
        return cls(path, key.encode() if key else None)

    def user_ref(self, user: Any) -> str | None:
        """Pseudonymous user reference, or None when no HMAC key or user id is available."""
        if not self._key or not isinstance(user, str) or not user:
            return None
        return hmac.new(self._key, user.encode(), hashlib.sha256).hexdigest()[:32]

    def write(self, **fields: Any) -> None:
        if not self.path:
            return
        unknown = set(fields) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"audit fields not allowed: {sorted(unknown)}")
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}
        record.update({k: v for k, v in fields.items() if v is not None})
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            if self.path == "-":
                sys.stdout.write(line)
                sys.stdout.flush()
            else:
                with Path(self.path).open("a", encoding="utf-8") as fh:
                    fh.write(line)
