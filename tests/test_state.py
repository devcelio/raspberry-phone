import json
from pathlib import Path

import pytest

from raspberry_phone.state import StateStore


def test_state_store_publishes_complete_json_atomically(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json", clock=lambda: 1234.5)

    state = store.publish(
        "speaking",
        transcript="olá",
        answer="oi!",
        timings_seconds={"first_audio": 0.75},
    )

    assert json.loads((tmp_path / "state.json").read_text()) == state
    assert state == {
        "status": "speaking",
        "transcript": "olá",
        "answer": "oi!",
        "timings_seconds": {"first_audio": 0.75},
        "error": None,
        "updated_at": 1234.5,
        "revision": 1,
        "turns": [],
        "current_turn": None,
        "session_supported": False,
        "mode": "continuous",
        "session_active": False,
        "listening": False,
        "input_transcript": "",
        "response_status": "idle",
        "capture_id": None,
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_state_store_rejects_unknown_status(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")

    with pytest.raises(ValueError, match="status desconhecido"):
        store.publish("sleeping")


def test_live_publication_updates_snapshot_without_rewriting_disk(
    tmp_path: Path,
) -> None:
    turns = [{"id": "one", "status": "complete"}]
    store = StateStore(tmp_path / "state.json", turns_provider=lambda: turns)
    durable = store.publish("ready")
    disk_before = (tmp_path / "state.json").read_bytes()

    live = store.publish(
        "thinking",
        transcript="Olá",
        answer="Resposta em curso",
        durable=False,
    )

    assert live["revision"] == durable["revision"] + 1
    assert store.snapshot() == live
    assert live["turns"] == turns
    assert live["current_turn"] is None
    assert (tmp_path / "state.json").read_bytes() == disk_before


def test_subscription_receives_every_revision_in_order(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    subscription = store.subscribe()

    first = store.publish("thinking", answer="Um", durable=False)
    second = store.publish("thinking", answer="Um dois", durable=False)
    third = store.publish("thinking", answer="Um dois três", durable=False)

    assert subscription.initial["revision"] == 0
    assert subscription.next(timeout=0) == first
    assert subscription.next(timeout=0) == second
    assert subscription.next(timeout=0) == third
    assert subscription.next(timeout=0) is None
    subscription.close()


def test_last_live_partial_reaches_subscriber_even_inside_interval(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json", live_interval=.02)
    store.publish("ready")
    subscription = store.subscribe()
    latest = store.publish("thinking", answer="Primeiras palavras", durable=False)
    assert subscription.next(timeout=.2) == latest
    subscription.close()
