"""OpenAI-compatible HTTP proxy built on the standard library.

Endpoints:
- ``GET  /healthz``                  liveness, no auth
- ``GET  /v1/models``                models allowed by policy
- ``POST /v1/chat/completions``      masked, forwarded, restored (streaming and non-streaming)
- ``POST /v1/firmalways/preview``    show what the AI would receive, without calling it

Fail closed: if inspection fails for any reason, the request is not forwarded.
"""

from __future__ import annotations

import hmac
import json
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from . import __version__
from .audit import AuditLog
from .engine import ContentNotAllowed, Gate, ResponseScanner, restore_completion
from .policy import Policy, Upstream
from .pseudonymize import Pseudonymizer, StreamRestorer

CLIENT_KEY_ENV = "FIRMALWAYS_GATE_API_KEY"


class GateHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        policy: Policy,
        *,
        audit: AuditLog | None = None,
        client_api_key: str | None = None,
        verbose: bool = False,
    ) -> None:
        self.policy = policy
        self.gate = Gate(policy)
        self.audit = audit if audit is not None else AuditLog(policy.audit_path)
        self.client_api_key = client_api_key or None
        self.verbose = verbose
        super().__init__(address, _Handler)

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


def open_upstream(upstream: Upstream, body: dict[str, Any], stream: bool):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
        "User-Agent": f"FirmAlwaysGate/{__version__}",
    }
    key = upstream.api_key()
    if key:
        headers[upstream.auth_header] = f"Bearer {key}" if upstream.auth_header.lower() == "authorization" else key
    request = urllib.request.Request(upstream.chat_url, data=data, headers=headers, method="POST")
    return urllib.request.urlopen(request, timeout=upstream.timeout)


class _Pipe:
    """Restore placeholders, then (optionally) redact new personal data, for one streamed field."""

    def __init__(self, restorer: StreamRestorer, scanner: ResponseScanner | None) -> None:
        self._restorer = restorer
        self._scanner = scanner

    @property
    def pending(self) -> bool:
        return self._restorer.pending or bool(self._scanner and self._scanner.pending)

    def feed(self, text: str) -> str:
        out = self._restorer.feed(text)
        return self._scanner.feed(out) if self._scanner else out

    def flush(self) -> str:
        out = self._restorer.flush()
        if self._scanner:
            out = self._scanner.feed(out) + self._scanner.flush()
        return out


def _format_counts(counts: dict[str, int]) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"


class _Handler(BaseHTTPRequestHandler):
    server: GateHTTPServer
    server_version = f"FirmAlwaysGate/{__version__}"
    sys_version = ""

    # ----- plumbing -------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature from base class
        if self.server.verbose:
            sys.stderr.write(f"{self.address_string()} - {format % args}\n")

    def _send_bytes(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8", headers)

    def _error(self, status: int, code: str, message: str, **extra: Any) -> None:
        self._send_json(status, {"error": {"message": message, "type": "firmalways_gate", "code": code, **extra}})

    def _authorized(self) -> bool:
        expected = self.server.client_api_key
        if not expected:
            return True
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if hmac.compare_digest(token.encode(), expected.encode()):
            return True
        self._error(401, "unauthorized", "Missing or invalid Gate API key")
        return False

    def _read_json(self) -> dict[str, Any] | None:
        length = self.headers.get("Content-Length")
        try:
            size = int(length) if length is not None else -1
        except ValueError:
            size = -1
        if size < 0:
            self._error(400, "invalid_request", "Content-Length header is required")
            return None
        if size > self.server.policy.max_body_bytes:
            self._error(413, "body_too_large", "Request body exceeds server.max_body_bytes")
            return None
        try:
            data = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            self._error(400, "invalid_json", "Request body must be JSON")
            return None
        if not isinstance(data, dict):
            self._error(400, "invalid_json", "Request body must be a JSON object")
            return None
        return data

    # ----- routes ---------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._send_json(200, {"status": "ok", "version": __version__})
        elif path in ("/v1/models", "/models"):
            if self._authorized():
                models = [{"id": m, "object": "model", "owned_by": name} for m, name in self.server.policy.models]
                self._send_json(200, {"object": "list", "data": models})
        else:
            self._error(404, "not_found", "Unknown path")

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path in ("/v1/chat/completions", "/chat/completions"):
            if self._authorized():
                self._chat()
        elif path == "/v1/firmalways/preview":
            if self._authorized():
                self._preview()
        else:
            self._error(404, "not_found", "Unknown path")

    def _preview(self) -> None:
        body = self._read_json()
        if body is None:
            return
        text = body.get("text")
        if not isinstance(text, str):
            self._error(400, "invalid_request", 'Body must be {"text": "..."}')
            return
        try:
            result = self.server.gate.preview(text)
        except Exception:  # noqa: BLE001 - fail closed, never echo the input
            self._error(500, "detection_failed", "Gate could not inspect the text")
            return
        self._send_json(200, result)

    def _chat(self) -> None:
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        audit = self.server.audit
        body = self._read_json()
        if body is None:
            return
        model = body.get("model")
        messages = body.get("messages")
        stream = body.get("stream") is True
        user = audit.user_ref(self.headers.get("X-FirmAlways-User") or body.get("user"))
        upstream = self.server.policy.route(model) if isinstance(model, str) else None

        def record(action: str, status: int, **fields: Any) -> None:
            audit.write(
                request_id=request_id,
                user=user,
                model=model if isinstance(model, str) else None,
                upstream=upstream.name if upstream else None,
                action=action,
                status=status,
                stream=stream,
                latency_ms=round((time.monotonic() - started) * 1000, 1),
                **fields,
            )

        if not isinstance(model, str) or not isinstance(messages, list):
            self._error(400, "invalid_request", "Body must include a string 'model' and a 'messages' array")
            return
        if upstream is None:
            record("blocked", 403, reason="model_not_allowed")
            self._error(403, "model_not_allowed", f"Model {model!r} is not allowed by the Gate policy")
            return

        pseudonymizer = Pseudonymizer()
        try:
            protected, protection = self.server.gate.protect_messages(messages, pseudonymizer)
        except ContentNotAllowed as exc:
            record("blocked", 422, reason="non_text_content")
            self._error(422, "content_not_allowed", str(exc))
            return
        except TypeError as exc:
            self._error(400, "invalid_request", str(exc))
            return
        except Exception:  # noqa: BLE001 - fail closed
            record("error", 500, reason="detection_failed")
            self._error(500, "detection_failed", "Gate could not inspect the request; it was not forwarded")
            return

        counts = dict(protection.counts)
        if protection.blocked:
            record("blocked", 422, reason="blocked_entity", entities=counts)
            self._error(
                422,
                "blocked_entity",
                "The request contains data that the Gate policy blocks: " + ", ".join(sorted(protection.blocked_types)),
                entity_types=sorted(protection.blocked_types),
            )
            return

        forward = dict(body)
        forward["messages"] = protected
        headers = {"X-FirmAlways-Request-Id": request_id, "X-FirmAlways-Entities": _format_counts(counts)}
        try:
            response = open_upstream(upstream, forward, stream)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            record("upstream_error", exc.code, entities=counts, masked=protection.masked)
            self._send_bytes(exc.code, payload, exc.headers.get("Content-Type", "application/json"), headers)
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            record("upstream_error", 502, reason="upstream_unreachable", entities=counts, masked=protection.masked)
            self._error(502, "upstream_unreachable", f"Could not reach upstream {upstream.name!r}")
            return

        redacted: Counter[str] = Counter()
        try:
            with response:
                if stream:
                    self._relay_stream(response, pseudonymizer, headers, redacted)
                    record("forwarded", 200, entities=counts, masked=protection.masked,
                           response_redacted=dict(redacted) or None)
                    return
                raw = response.read()
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            record("upstream_error", 499, reason="stream_interrupted", entities=counts, masked=protection.masked)
            return
        try:
            data = json.loads(raw)
        except ValueError:
            record("forwarded", 200, entities=counts, masked=protection.masked)
            self._send_bytes(200, raw, response.headers.get("Content-Type", "text/plain"), headers)
            return
        restore_completion(data, pseudonymizer, self.server.gate, redacted)
        record("forwarded", 200, entities=counts, masked=protection.masked, response_redacted=dict(redacted) or None)
        headers["X-FirmAlways-Response-Redacted"] = _format_counts(dict(redacted))
        self._send_json(200, data, headers)

    # ----- streaming ------------------------------------------------------

    def _emit(self, text: str) -> None:
        self.wfile.write(text.encode("utf-8"))
        self.wfile.flush()

    def _relay_stream(
        self, response: Iterable[bytes], pseudonymizer: Pseudonymizer, headers: dict[str, str], redacted: Counter[str]
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()

        restorers: dict[tuple[Any, ...], _Pipe] = {}
        template: dict[str, Any] | None = None
        gate = self.server.gate

        def restorer(key: tuple[Any, ...]) -> _Pipe:
            if key not in restorers:
                scanner = gate.response_scanner(pseudonymizer, redacted) if gate.policy.response_scan else None
                restorers[key] = _Pipe(pseudonymizer.stream_restorer(), scanner)
            return restorers[key]

        for raw in response:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            if not line.startswith("data:"):
                self._emit(line + "\n" if not line.startswith(":") else line + "\n\n")
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                self._flush_remaining(restorers, template)
                self._emit("data: [DONE]\n\n")
                return
            try:
                chunk = json.loads(payload)
            except ValueError:
                self._emit(line + "\n\n")
                continue
            if isinstance(chunk, dict):
                template = chunk
                for choice in chunk.get("choices") or []:
                    if isinstance(choice, dict):
                        self._restore_choice(choice, restorer, restorers)
            self._emit("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n")
        self._flush_remaining(restorers, template)

    @staticmethod
    def _restore_choice(choice: dict[str, Any], restorer, restorers: dict[tuple[Any, ...], _Pipe]) -> None:
        index = choice.get("index", 0)
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            delta = {}
            choice["delta"] = delta
        if isinstance(delta.get("content"), str):
            delta["content"] = restorer((index, "content")).feed(delta["content"])
        calls = delta.get("tool_calls") if isinstance(delta.get("tool_calls"), list) else []
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict) and isinstance(function.get("arguments"), str):
                key = (index, "tool", call.get("index", 0))
                function["arguments"] = restorer(key).feed(function["arguments"])
        if choice.get("finish_reason") is None:
            return
        # The choice is finished: release everything still held, in order, in this chunk.
        content_key = (index, "content")
        if content_key in restorers and restorers[content_key].pending:
            delta["content"] = (delta.get("content") or "") + restorers.pop(content_key).flush()
        for key in [k for k in restorers if k[0] == index and k[1] == "tool"]:
            rest = restorers.pop(key).flush()
            if not rest:
                continue
            match = next((c for c in calls if isinstance(c, dict) and c.get("index", 0) == key[2]), None)
            if match is not None:
                match["function"]["arguments"] += rest
            else:
                delta.setdefault("tool_calls", []).append({"index": key[2], "function": {"arguments": rest}})

    def _flush_remaining(self, restorers: dict[tuple[Any, ...], _Pipe], template: dict[str, Any] | None) -> None:
        by_choice: dict[Any, dict[str, Any]] = {}
        for key, item in list(restorers.items()):
            rest = item.flush()
            if not rest:
                continue
            delta = by_choice.setdefault(key[0], {})
            if key[1] == "content":
                delta["content"] = rest
            else:
                delta.setdefault("tool_calls", []).append({"index": key[2], "function": {"arguments": rest}})
        restorers.clear()
        if not by_choice:
            return
        base = {k: v for k, v in (template or {}).items() if k in ("id", "object", "created", "model")}
        base.setdefault("object", "chat.completion.chunk")
        base["choices"] = [{"index": i, "delta": d, "finish_reason": None} for i, d in by_choice.items()]
        self._emit("data: " + json.dumps(base, ensure_ascii=False) + "\n\n")


def create_server(
    policy: Policy,
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    audit: AuditLog | None = None,
    client_api_key: str | None = None,
    verbose: bool = False,
) -> GateHTTPServer:
    return GateHTTPServer((host, port), policy, audit=audit, client_api_key=client_api_key, verbose=verbose)
