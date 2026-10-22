import json
from pathlib import Path

import pytest

from raspberry_phone.conversation import ConversationStore


def test_conversation_store_persists_completed_turns(tmp_path: Path) -> None:
    path = tmp_path / "conversation.json"
    store = ConversationStore(path, clock=lambda: 100.0, id_generator=lambda: "turn-1")

    turn_id = store.begin_turn("Como vai?")
    store.complete_turn(
        turn_id,
        "Tudo certo.",
        timings_seconds={"turn_total": 1.25},
    )

    restored = ConversationStore(path, clock=lambda: 200.0)
    assert restored.turns() == [
        {
            "id": "turn-1",
            "transcript": "Como vai?",
            "answer": "Tudo certo.",
            "status": "complete",
            "error": None,
            "started_at": 100.0,
            "completed_at": 100.0,
            "timings_seconds": {"turn_total": 1.25},
        }
    ]
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_conversation_store_keeps_failed_turn_with_partial_answer(
    tmp_path: Path,
) -> None:
    store = ConversationStore(
        tmp_path / "conversation.json",
        clock=lambda: 20.0,
        id_generator=lambda: "failed-turn",
    )

    turn_id = store.begin_turn("Pergunta")
    store.fail_turn(
        turn_id,
        answer="Resposta parcial",
        error="rede caiu",
        timings_seconds={"llm_total": 0.5},
    )

    assert store.turns()[0] == {
        "id": "failed-turn",
        "transcript": "Pergunta",
        "answer": "Resposta parcial",
        "status": "error",
        "error": "rede caiu",
        "started_at": 20.0,
        "completed_at": 20.0,
        "timings_seconds": {"llm_total": 0.5},
    }
    assert store.successful_turns() == []


def test_conversation_store_recovers_pending_turn_and_can_clear(
    tmp_path: Path,
) -> None:
    path = tmp_path / "conversation.json"
    store = ConversationStore(
        path, clock=lambda: 10.0, id_generator=lambda: "pending-turn"
    )
    store.begin_turn("Fala antes da queda")

    recovered = ConversationStore(path, clock=lambda: 11.0)

    assert recovered.turns()[0]["status"] == "interrupted"
    assert recovered.turns()[0]["completed_at"] == 11.0
    assert recovered.turns()[0]["error"] == "Turno interrompido antes de terminar."
    assert recovered.successful_turns() == []
    recovered.clear()
    assert recovered.turns() == []
    assert json.loads(path.read_text())["turns"] == []


def test_conversation_store_rejects_malformed_turns(tmp_path: Path) -> None:
    path = tmp_path / "conversation.json"
    path.write_text('{"version": 1, "turns": [{"status": "pending"}]}')

    with pytest.raises(RuntimeError, match="Histórico inválido"):
        ConversationStore(path)
