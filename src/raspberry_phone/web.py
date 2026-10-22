from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from socketserver import TCPServer
from typing import Protocol
from urllib.parse import urlsplit

from .state import StateStore


class WebTurnController(Protocol):
    def start_turn(self) -> bool: ...

    def reset_conversation(self) -> bool: ...

    def set_mode(self, mode: str) -> bool: ...

    def start_session(self, mode: str, capture_id: str | None = None) -> bool: ...

    def stop_session(self, *, capture_id: str | None = None, release: bool = False) -> bool: ...


class PhoneHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class PhoneWebServer:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        state: StateStore,
        controller: WebTurnController,
        record_seconds: int = 7,
        keepalive_seconds: float = 15,
        streaming: bool = False,
    ) -> None:
        self.host = host
        self.state = state
        self.controller = controller
        handler = _handler_for(
            state, controller, record_seconds, keepalive_seconds, streaming
        )
        try:
            self._server = PhoneHTTPServer((host, port), handler)
        except OSError as exc:
            raise RuntimeError(
                f"Não foi possível abrir a interface em {host}:{port}: {exc}"
            ) from exc
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        port = self._server.server_address[1]
        return f"http://{self.host}:{port}/"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="phone-web",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            self._server.server_close()
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        self._thread = None


def _handler_for(
    state: StateStore,
    controller: WebTurnController,
    record_seconds: int,
    keepalive_seconds: float,
    streaming: bool,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "RaspberryPhone/0.1"

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/events":
                self._send_events()
                return
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.css": ("app.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/ui.mjs": ("ui.mjs", "text/javascript; charset=utf-8"),
            }
            asset = assets.get(path)
            if asset is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            name, content_type = asset
            body = files("raspberry_phone").joinpath("web", name).read_bytes()
            if name == "index.html":
                body = body.replace(
                    b"__RECORD_SECONDS__", str(record_seconds).encode("ascii")
                ).replace(b"__STREAMING__", b"true" if streaming else b"false")
            self.send_response(HTTPStatus.OK)
            self._common_headers(content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.headers.get_content_type() != "application/json":
                self._send_json(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    {"error": "Envie application/json."},
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 4096:
                    raise ValueError("Corpo inválido")
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("Objeto JSON obrigatório")
            except (ValueError, json.JSONDecodeError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "JSON inválido."})
                return

            path = urlsplit(self.path).path
            session_paths = {"/api/session/mode", "/api/session/start", "/api/session/stop",
                             "/api/ptt/press", "/api/ptt/release", "/api/ptt/cancel"}
            if path in session_paths:
                if not state.snapshot().get("session_supported"):
                    self._send_json(HTTPStatus.CONFLICT, {"error": "Modo indisponível neste fluxo de voz."})
                    return
                capture_id = payload.get("capture_id")
                if path.startswith("/api/ptt/") and (
                    not isinstance(capture_id, str) or not 1 <= len(capture_id) <= 128
                ):
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "capture_id obrigatório."})
                    return
                if path == "/api/session/mode":
                    mode = payload.get("mode")
                    if mode not in ("continuous", "push-to-talk"):
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Modo inválido."})
                        return
                    accepted = controller.set_mode(mode)
                elif path == "/api/session/start":
                    accepted = controller.start_session("continuous")
                elif path == "/api/ptt/press":
                    accepted = controller.start_session("push-to-talk", capture_id)
                else:
                    accepted = controller.stop_session(capture_id=capture_id,
                                                       release=path == "/api/ptt/release")
                self._send_json(HTTPStatus.ACCEPTED if accepted else HTTPStatus.CONFLICT,
                                state.snapshot() if accepted else {"error": "Comando incompatível com a sessão atual."})
                return
            if path == "/api/turn":
                if controller.start_turn():
                    self._send_json(HTTPStatus.ACCEPTED, state.snapshot())
                else:
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        {"error": "Já existe um turno em andamento."},
                    )
                return
            if path == "/api/conversation/reset":
                if controller.reset_conversation():
                    self._send_json(HTTPStatus.OK, state.snapshot())
                else:
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        {"error": "Espere o turno terminar para começar de novo."},
                    )
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _send_events(self) -> None:
            self.send_response(HTTPStatus.OK)
            self._common_headers("text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            subscription = state.subscribe()
            snapshot = subscription.initial
            previous_turns = None
            try:
                while True:
                    turns = snapshot.get("turns")
                    if turns == previous_turns:
                        self._write_event({k:v for k,v in snapshot.items() if k not in {"turns", "current_turn"}}, "delta")
                    else:
                        self._write_event(snapshot)
                        previous_turns = turns
                    next_snapshot = subscription.next(timeout=keepalive_seconds)
                    while next_snapshot is None:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        next_snapshot = subscription.next(timeout=keepalive_seconds)
                    snapshot = next_snapshot
            except (BrokenPipeError, ConnectionResetError):
                return
            finally:
                subscription.close()

        def _write_event(self, snapshot: dict[str, object], event_type: str = "state") -> None:
            data = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
            event = (
                f"id: {snapshot['revision']}\n"
                f"event: {event_type}\n"
                f"data: {data}\n\n"
            ).encode()
            self.wfile.write(event)
            self.wfile.flush()

        def _send_json(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self._common_headers("application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _common_headers(self, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; "
                "script-src 'self'; style-src 'self'; img-src 'self' data:",
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler
