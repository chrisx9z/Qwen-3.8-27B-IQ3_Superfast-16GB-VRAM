from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from llm.server_lifecycle import _is_process_alive
from llm.server_manager import LocalLLMServerManager


FAKE_HTTP_SERVER_CODE = r"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

host = sys.argv[1]
port = int(sys.argv[2])

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/props":
            body = json.dumps({"default_generation_settings": {"n_ctx": 32768}}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception:
            req = {}

        if req.get("stream"):
            chunk1 = json.dumps({"choices": [{"delta": {"content": "fake-server-ok"}}]})
            sse = f"data: {chunk1}\n\ndata: [DONE]\n\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(sse)))
            self.end_headers()
            self.wfile.write(sse)
            return

        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "fake-server-ok",
                    }
                }
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

server = ThreadingHTTPServer((host, port), Handler)
server.serve_forever()
"""

SLEEP_PROCESS_CODE = "import time; time.sleep(60)"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def creation_flags(*, new_group: bool = False) -> int:
    if sys.platform != "win32":
        return 0
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if new_group:
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return flags


def wait_dead(pid: int, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            return True
        time.sleep(0.1)
    return not _is_process_alive(pid)


def make_dummy_model(tmp_path: Path) -> Path:
    model = tmp_path / "dummy.gguf"
    model.write_bytes(b"GGUF")
    return model


class FakeServerManager(LocalLLMServerManager):
    """Dùng toàn bộ logic thật của LocalLLMServerManager nhưng chạy fake HTTP server."""

    def _build_command(self) -> list[str]:
        return [sys.executable, "-c", FAKE_HTTP_SERVER_CODE, self.host, str(self.port)]
