"""A fake OpenAI-compatible AI that answers with exactly what it received.

Use it to see what an AI provider would get through Gate, without an API key
and without sending anything off the machine:

    firmalways-gate echo-upstream --port 8788
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PREFIX = "AI ได้รับข้อความนี้: "
MODEL = "echo"


def _last_user_text(messages: Any) -> str:
    for message in reversed(messages if isinstance(messages, list) else []):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


class EchoUpstreamServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, verbose: bool = False, chunk_size: int = 5) -> None:
        self.received: list[dict[str, Any]] = []
        self.verbose = verbose
        self.chunk_size = chunk_size
        self._lock = threading.Lock()
        super().__init__(address, _EchoHandler)

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/v1"

    def remember(self, body: dict[str, Any]) -> None:
        with self._lock:
            self.received.append(body)
        if self.verbose:
            sys.stderr.write("[echo-upstream] AI received: " + _last_user_text(body.get("messages")) + "\n")


class _EchoHandler(BaseHTTPRequestHandler):
    server: EchoUpstreamServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "echo"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        self.server.remember(body)
        text = PREFIX + _last_user_text(body.get("messages"))
        completion_id = "chatcmpl-echo-" + uuid.uuid4().hex[:12]
        created = int(time.time())
        model = body.get("model", MODEL)
        if body.get("stream") is True:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            base = {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model}

            def send(delta: dict[str, Any], finish: str | None = None) -> None:
                chunk = dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": finish}])
                self.wfile.write(("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()

            send({"role": "assistant", "content": ""})
            size = self.server.chunk_size
            for i in range(0, len(text), size):
                send({"content": text[i : i + size]})
            send({}, "stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        self._json(
            200,
            {
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )
