import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from raspberry_phone.state import StateStore
from raspberry_phone.web import PhoneWebServer


class FakeController:
    def __init__(self) -> None:
        self.busy = False

    def start_turn(self) -> bool:
        if self.busy:
            return False
        self.busy = True
        return True

    def reset_conversation(self) -> bool:
        return not self.busy


def post(url: str) -> int:
    request = Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=2) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def read_event(response) -> dict[str, object]:
    lines = [response.readline().decode().strip() for _ in range(4)]
    assert lines[0].startswith("id: ")
    assert lines[1] in {"event: state", "event: delta"}
    return json.loads(lines[2].removeprefix("data: "))


def test_web_server_serves_ui_and_serializes_commands(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.publish("ready")
    controller = FakeController()
    server = PhoneWebServer(
        "127.0.0.1",
        0,
        state=state,
        controller=controller,
        record_seconds=11,
    )
    server.start()
    try:
        with urlopen(server.url, timeout=2) as response:
            html = response.read().decode()
        assert "Falar" in html
        assert 'data-record-seconds="11"' in html
        assert post(f"{server.url}api/turn") == 202
        assert post(f"{server.url}api/turn") == 409
        assert post(f"{server.url}api/conversation/reset") == 409
    finally:
        server.stop()


def test_sse_starts_with_current_snapshot(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.json")
    current = state.publish("thinking", transcript="Olá", answer="Oi")
    server = PhoneWebServer(
        "127.0.0.1", 0, state=state, controller=FakeController()
    )
    server.start()
    try:
        with urlopen(f"{server.url}api/events", timeout=2) as response:
            payload = read_event(response)
        assert payload["revision"] == current["revision"]
        assert payload["answer"] == "Oi"
    finally:
        server.stop()


def test_sse_delivers_every_fast_delta_and_reconnects_to_latest_state(
    tmp_path: Path,
) -> None:
    state = StateStore(tmp_path / "state.json")
    state.publish("ready")
    server = PhoneWebServer(
        "127.0.0.1", 0, state=state, controller=FakeController()
    )
    server.start()
    try:
        with urlopen(f"{server.url}api/events", timeout=2) as response:
            read_event(response)
            states = [
                state.publish("thinking", answer=answer, durable=False)
                for answer in ("Um", "Um dois", "Um dois três")
            ]
            received = [read_event(response) for _ in states]

        assert [item["revision"] for item in received] == [
            item["revision"] for item in states
        ]
        assert [item["answer"] for item in received] == [
            "Um",
            "Um dois",
            "Um dois três",
        ]

        latest = state.publish("speaking", answer="Reconectado", durable=False)
        with urlopen(f"{server.url}api/events", timeout=2) as response:
            reconnected = read_event(response)
        assert reconnected["revision"] == latest["revision"]
        assert reconnected["answer"] == "Reconectado"
    finally:
        server.stop()


def test_sse_sends_keepalive_while_state_is_unchanged(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.json")
    server = PhoneWebServer(
        "127.0.0.1",
        0,
        state=state,
        controller=FakeController(),
        keepalive_seconds=0.01,
    )
    server.start()
    try:
        with urlopen(f"{server.url}api/events", timeout=2) as response:
            read_event(response)
            assert response.readline().decode().strip() == ": keepalive"
    finally:
        server.stop()


def test_ui_uses_safe_rendering_and_accessible_responsive_behaviour(
    tmp_path: Path,
) -> None:
    state = StateStore(tmp_path / "state.json")
    server = PhoneWebServer(
        "127.0.0.1", 0, state=state, controller=FakeController()
    )
    server.start()
    try:
        assets = {}
        for path in ("", "app.js", "ui.mjs", "app.css"):
            with urlopen(f"{server.url}{path}", timeout=2) as response:
                assets[path or "index.html"] = response.read().decode()

        html = assets["index.html"]
        javascript = assets["app.js"]
        ui_javascript = assets["ui.mjs"]
        css = assets["app.css"]
        assert 'aria-live="polite"' in html
        assert "textContent" in ui_javascript
        assert "innerHTML" not in javascript + ui_javascript
        assert "new EventSource" in javascript
        assert "nearBottom" in javascript
        assert "prefers-reduced-motion" in javascript
        assert 'addEventListener("click"' in javascript
        assert "@media (max-width: 540px)" in css
        assert "@media (prefers-reduced-motion: reduce)" in css
        assert ":focus-visible" in css
        assert "rail-travel" not in css
    finally:
        server.stop()


def test_session_endpoints_validate_payload_and_capture_identity(tmp_path):
    from test_session import setup, eventually
    a, controller = setup(tmp_path)
    server = PhoneWebServer('127.0.0.1', 0, state=a.state, controller=controller)
    def command(path, payload):
        request = Request(server.url + path, data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=2) as response:
                return response.status
        except HTTPError as exc:
            return exc.code
    server.start()
    try:
        assert command('api/session/mode', []) == 400
        assert command('api/session/mode', {'mode': 'invalid'}) == 400
        assert command('api/session/start', {}) == 202
        assert command('api/turn', {}) == 409
        assert command('api/conversation/reset', {}) == 409
        assert command('api/session/stop', {}) == 202
        eventually(lambda: not controller.busy)
        assert command('api/session/mode', {'mode': 'push-to-talk'}) == 202
        assert command('api/ptt/press', {}) == 400
        assert command('api/ptt/press', {'capture_id': 'new'}) == 202
        assert command('api/ptt/cancel', {'capture_id': 'old'}) == 409
        assert command('api/ptt/cancel', {'capture_id': 'new'}) == 202
        eventually(lambda: not controller.busy)
    finally:
        controller.shutdown()
        server.stop()
