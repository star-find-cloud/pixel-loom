from __future__ import annotations

import hmac
import json
import queue
import secrets
import threading
from concurrent.futures import Future, TimeoutError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .model import PixelError, atomic_json
from .paths import SESSION, SOURCE_ROOT


ROOT = SOURCE_ROOT  # Compatibility for local authoring scripts; user data uses paths.py.


class Bridge:
    """Loopback transport; every document request runs on the GUI's main thread."""

    def __init__(self, session_path=None):
        self.requests = queue.Queue()
        self.session_path = Path(session_path or SESSION)
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value, content_type="application/json; charset=utf-8"):
                body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def handle_request(self, method):
                parsed = urlparse(self.path)
                if parsed.path == "/health" and method == "GET":
                    self.reply(200, {"ok": True, "app": "Pixel Loom", "version": __version__})
                    return
                if not hmac.compare_digest(self.headers.get("X-Pixel-Loom-Token", ""), owner.token):
                    self.reply(401, {"ok": False, "error": "Use the local session token"})
                    return
                if self.headers.get("Origin"):
                    self.reply(403, {"ok": False, "error": "Browser-origin requests are not supported"})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 16_000_000:
                        raise PixelError("Request exceeds the 16 MB limit")
                    if method == "POST" and "application/json" not in self.headers.get("Content-Type", ""):
                        raise PixelError("POST requires application/json")
                    payload = json.loads(self.rfile.read(size).decode("utf-8-sig")) if size else {}
                    if not isinstance(payload, dict):
                        raise PixelError("Request body must be a JSON object")
                    future = Future()
                    owner.requests.put((method, parsed.path, parse_qs(parsed.query), payload, future))
                    result, content_type = future.result(timeout=20)
                    self.reply(200, result, content_type)
                except TimeoutError:
                    # A queued request that hasn't started must never mutate later.
                    cancelled = future.cancel()
                    message = ("Editor is busy; queued request cancelled. Read state before retrying." if cancelled else
                               "Editor is still processing the request; its outcome is not yet known. Read state before retrying.")
                    self.reply(503, {"ok": False, "error": message})
                except Exception as exc:
                    code = getattr(exc, "code", "INVALID_ARGUMENT")
                    if code == "INVALID_ARGUMENT" and "conflict" in str(exc).lower():
                        code = "REVISION_CONFLICT"
                    status = 409 if code in ("REVISION_CONFLICT", "DOCUMENT_CONFLICT", "UNSAVED_CHANGES", "FILE_EXISTS", "REQUEST_ID_REUSED") else 400
                    error = {"ok": False, "error": str(exc), "code": code,
                             "recovery": getattr(exc, "recovery", None)}
                    if getattr(exc, "details", None) is not None:
                        error["details"] = exc.details
                    self.reply(status, error)

            def do_GET(self):
                self.handle_request("GET")

            def do_POST(self):
                self.handle_request("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        atomic_json(self.session_path, {"url": self.url, "token": self.token, "version": __version__})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="pixel-loom-bridge")
        self.thread.start()

    def pump(self, callback):
        for _ in range(10):
            try:
                method, path, query, payload, future = self.requests.get_nowait()
            except queue.Empty:
                break
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(callback(method, path, query, payload))
            except Exception as exc:
                future.set_exception(exc)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        try:
            if json.loads(self.session_path.read_text(encoding="utf-8"))["token"] == self.token:
                self.session_path.unlink(missing_ok=True)
        except (OSError, KeyError, ValueError):
            pass
