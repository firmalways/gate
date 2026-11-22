"""Policy: what to do with each kind of data, and which AI models may receive requests.

Policies are TOML files (``tomllib`` is in the standard library). See
``policy.example.toml`` for every option.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ACTIONS = ("allow", "mask", "block")

DEFAULT_ENTITY_ACTIONS: dict[str, str] = {
    "THAI_NATIONAL_ID": "mask",
    "PHONE": "mask",
    "EMAIL": "mask",
    "BANK_ACCOUNT": "mask",
    "CREDIT_CARD": "mask",
    "PERSON": "mask",
    "THAI_ADDRESS": "mask",
    "PASSPORT": "mask",
    "LICENSE_PLATE": "mask",
    "LINE_ID": "mask",
    "IP_ADDRESS": "mask",
    "TAX_ID": "mask",
    "DATE_OF_BIRTH": "mask",
    "NATIONALITY": "mask",
    "SECRET": "block",
    # PDPA section 26 sensitive data (reported only next to a personal identifier)
    "SENSITIVE_HEALTH": "block",
    "SENSITIVE_RELIGION": "block",
    "SENSITIVE_CRIMINAL": "block",
    "SENSITIVE_DISABILITY": "block",
    "SENSITIVE_BIOMETRIC": "block",
    "SENSITIVE_GENETIC": "block",
    "SENSITIVE_POLITICAL": "block",
    "SENSITIVE_UNION": "block",
    "SENSITIVE_SEXUAL": "block",
    "SENSITIVE_RACE": "block",
}

RESPONSE_ACTIONS = ("allow", "mask")

# New values (not present in the request) that are redacted from AI answers by default.
DEFAULT_RESPONSE_ACTIONS: dict[str, str] = {
    "SECRET": "mask",
    "THAI_NATIONAL_ID": "mask",
    "CREDIT_CARD": "mask",
    "BANK_ACCOUNT": "mask",
    "PASSPORT": "mask",
}


class PolicyError(ValueError):
    """The policy file is invalid. Gate refuses to start rather than guess."""


@dataclass(frozen=True)
class Upstream:
    name: str
    base_url: str
    models: tuple[str, ...]
    api_key_env: str | None = None
    auth_header: str = "Authorization"
    timeout: float = 120.0

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None

    def allows(self, model: str) -> bool:
        return "*" in self.models or model in self.models


@dataclass(frozen=True)
class Client:
    """An application or team that calls Gate with its own key (``[[clients]]``)."""

    name: str
    api_key_env: str

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


@dataclass(frozen=True)
class Policy:
    default_action: str = "mask"
    entity_actions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ENTITY_ACTIONS))
    min_score: float = 0.5
    lenient_thai_id: bool = True
    sensitive_requires_identifier: bool = True
    thai_ner: bool = False
    allow_non_text: bool = False
    files: str = "extract"
    response_scan: bool = True
    response_default_action: str = "allow"
    response_entity_actions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RESPONSE_ACTIONS))
    upstreams: tuple[Upstream, ...] = ()
    clients: tuple[Client, ...] = ()
    audit_path: str | None = None
    max_body_bytes: int = 2_000_000

    def action_for(self, entity_type: str) -> str:
        return self.entity_actions.get(entity_type, self.default_action)

    def response_action_for(self, entity_type: str) -> str:
        return self.response_entity_actions.get(entity_type, self.response_default_action)

    def route(self, model: str) -> Upstream | None:
        return next((u for u in self.upstreams if u.allows(model)), None)

    @property
    def models(self) -> list[tuple[str, str]]:
        return [(m, u.name) for u in self.upstreams for m in u.models if m != "*"]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Policy:
        default_action = _action(data.get("default_action", "mask"), "default_action")

        actions = dict(DEFAULT_ENTITY_ACTIONS)
        for name, value in _table(data, "entities").items():
            actions[str(name).upper()] = _action(value, f"entities.{name}")

        detection = _table(data, "detection")
        min_score = detection.get("min_score", 0.5)
        if not isinstance(min_score, (int, float)) or not 0 <= min_score <= 1:
            raise PolicyError("detection.min_score must be a number between 0 and 1")

        response = _table(data, "response")
        response_default = response.get("default_action", "allow")
        if response_default not in RESPONSE_ACTIONS:
            raise PolicyError("response.default_action must be allow or mask")
        response_actions = dict(DEFAULT_RESPONSE_ACTIONS)
        raw_response_entities = response.get("entities", {})
        if not isinstance(raw_response_entities, dict):
            raise PolicyError("[response.entities] must be a table")
        for name, value in raw_response_entities.items():
            if value not in RESPONSE_ACTIONS:
                raise PolicyError(f"response.entities.{name} must be allow or mask; got {value!r}")
            response_actions[str(name).upper()] = value

        audit_path = _table(data, "audit").get("path")
        if audit_path is not None and not isinstance(audit_path, str):
            raise PolicyError("audit.path must be a string")

        max_body = _table(data, "server").get("max_body_bytes", 2_000_000)
        if not isinstance(max_body, int) or max_body <= 0:
            raise PolicyError("server.max_body_bytes must be a positive integer")

        raw_upstreams = data.get("upstreams", [])
        if not isinstance(raw_upstreams, list):
            raise PolicyError("upstreams must be an array of tables ([[upstreams]])")
        upstreams = tuple(_upstream(u, i) for i, u in enumerate(raw_upstreams))
        names = [u.name for u in upstreams]
        if len(names) != len(set(names)):
            raise PolicyError("upstream names must be unique")

        raw_clients = data.get("clients", [])
        if not isinstance(raw_clients, list):
            raise PolicyError("clients must be an array of tables ([[clients]])")
        clients = []
        for i, raw in enumerate(raw_clients):
            if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) and raw[k] for k in ("name", "api_key_env")):
                raise PolicyError(f"clients[{i}] needs a name and an api_key_env")
            clients.append(Client(raw["name"], raw["api_key_env"]))
        if len({c.name for c in clients}) != len(clients):
            raise PolicyError("client names must be unique")

        return cls(
            default_action=default_action,
            entity_actions=actions,
            min_score=float(min_score),
            lenient_thai_id=_bool(detection.get("lenient_thai_id", True), "detection.lenient_thai_id"),
            sensitive_requires_identifier=_bool(
                detection.get("sensitive_requires_identifier", True), "detection.sensitive_requires_identifier"
            ),
            thai_ner=_bool(detection.get("thai_ner", False), "detection.thai_ner"),
            allow_non_text=_bool(_table(data, "content").get("allow_non_text", False), "content.allow_non_text"),
            files=_files(_table(data, "content").get("files", "extract")),
            response_scan=_bool(response.get("scan", True), "response.scan"),
            response_default_action=response_default,
            response_entity_actions=response_actions,
            upstreams=upstreams,
            clients=tuple(clients),
            audit_path=audit_path or None,
            max_body_bytes=max_body,
        )


def load_policy(path: str | os.PathLike[str]) -> Policy:
    try:
        with Path(path).open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise PolicyError(f"cannot read policy file {path}: {exc.strerror}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"invalid TOML in {path}: {exc}") from exc
    return Policy.from_dict(data)


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise PolicyError(f"[{key}] must be a table")
    return value


def _action(value: Any, where: str) -> str:
    if value not in ACTIONS:
        raise PolicyError(f"{where} must be one of {', '.join(ACTIONS)}; got {value!r}")
    return value


def _files(value: Any) -> str:
    if value not in ("extract", "block"):
        raise PolicyError('content.files must be "extract" or "block"')
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyError(f"{where} must be true or false")
    return value


def _upstream(raw: Any, index: int) -> Upstream:
    where = f"upstreams[{index}]"
    if not isinstance(raw, dict):
        raise PolicyError(f"{where} must be a table")
    for key in ("name", "base_url"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise PolicyError(f"{where}.{key} is required")
    if not raw["base_url"].startswith(("http://", "https://")):
        raise PolicyError(f"{where}.base_url must start with http:// or https://")
    models = raw.get("models")
    if not isinstance(models, list) or not models or not all(isinstance(m, str) and m for m in models):
        raise PolicyError(f'{where}.models must list allowed model names (use ["*"] to allow any)')
    timeout = raw.get("timeout", 120.0)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise PolicyError(f"{where}.timeout must be a positive number")
    api_key_env = raw.get("api_key_env")
    if api_key_env is not None and not isinstance(api_key_env, str):
        raise PolicyError(f"{where}.api_key_env must be a string")
    auth_header = raw.get("auth_header", "Authorization")
    if not isinstance(auth_header, str) or not auth_header:
        raise PolicyError(f"{where}.auth_header must be a header name")
    return Upstream(
        name=raw["name"],
        base_url=raw["base_url"],
        models=tuple(models),
        api_key_env=api_key_env or None,
        auth_header=auth_header,
        timeout=float(timeout),
    )
