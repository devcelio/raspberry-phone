from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Literal, TypedDict, cast
from uuid import uuid4

from .storage import atomic_write_json


TurnStatus = Literal["pending", "complete", "error", "interrupted"]


class ConversationTurn(TypedDict):
    id: str
    transcript: str
    answer: str
    status: TurnStatus
    error: str | None
    started_at: float
    completed_at: float | None
    timings_seconds: dict[str, float]


class ConversationHistory:
    """Keep a bounded number of complete user/assistant turns in memory."""

    def __init__(self, max_turns: int = 4) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        self._turns: deque[tuple[str, str]] = deque(maxlen=max_turns)

    def add_turn(self, user_text: str, assistant_text: str) -> None:
        self._turns.append((user_text, assistant_text))

    def clear(self) -> None:
        self._turns.clear()

    def messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for user_text, assistant_text in self._turns:
            messages.extend(
                (
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                )
            )
        return messages


class ConversationStore:
    """Persist the visible conversation independently from the model context."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float] = time.time,
        id_generator: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self.path = path
        self._clock = clock
        self._id_generator = id_generator
        self._lock = threading.Lock()
        self._turns = self._read()
        self._turns = self._turns[-100:]
        self._recover_interrupted_turns()

    def begin_turn(self, transcript: str) -> str:
        turn_id = self._id_generator()
        with self._lock:
            self._turns.append(
                {
                    "id": turn_id,
                    "transcript": transcript,
                    "answer": "",
                    "status": "pending",
                    "error": None,
                    "started_at": self._clock(),
                    "completed_at": None,
                    "timings_seconds": {},
                }
            )
            self._turns = self._turns[-100:]
            self._write_locked()
        return turn_id

    def update_transcript(self, turn_id: str, transcript: str) -> None:
        with self._lock:
            turn = self._find_locked(turn_id)
            turn["transcript"] = transcript
            self._write_locked()

    def complete_turn(
        self,
        turn_id: str,
        answer: str,
        *,
        timings_seconds: Mapping[str, float] | None = None,
    ) -> None:
        with self._lock:
            turn = self._find_locked(turn_id)
            turn["answer"] = answer
            turn["status"] = "complete"
            turn["error"] = None
            turn["completed_at"] = self._clock()
            turn["timings_seconds"] = dict(timings_seconds or {})
            self._write_locked()

    def fail_turn(
        self,
        turn_id: str,
        answer: str,
        error: str,
        *,
        timings_seconds: Mapping[str, float] | None = None,
    ) -> None:
        with self._lock:
            turn = self._find_locked(turn_id)
            turn["answer"] = answer
            turn["status"] = "error"
            turn["error"] = error
            turn["completed_at"] = self._clock()
            turn["timings_seconds"] = dict(timings_seconds or {})
            self._write_locked()

    def interrupt_turn(self, turn_id: str, answer: str) -> None:
        with self._lock:
            turn = self._find_locked(turn_id)
            turn["answer"] = answer
            turn["status"] = "interrupted"
            turn["error"] = "Resposta interrompida; o texto pode não ter sido ouvido por inteiro."
            turn["completed_at"] = self._clock()
            self._write_locked()

    def turns(self) -> list[ConversationTurn]:
        with self._lock:
            return deepcopy(self._turns)

    def successful_turns(self) -> list[ConversationTurn]:
        with self._lock:
            return deepcopy(
                [turn for turn in self._turns if turn["status"] == "complete"]
            )

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._write_locked()

    def _recover_interrupted_turns(self) -> None:
        interrupted = False
        for turn in self._turns:
            if turn["status"] == "pending":
                turn["status"] = "interrupted"
                turn["error"] = "Turno interrompido antes de terminar."
                turn["completed_at"] = self._clock()
                interrupted = True
        if interrupted:
            self._write_locked()

    def _find_locked(self, turn_id: str) -> ConversationTurn:
        for turn in self._turns:
            if turn["id"] == turn_id:
                return turn
        raise KeyError(f"turno desconhecido: {turn_id}")

    def _read(self) -> list[ConversationTurn]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Não foi possível ler o histórico em {self.path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Histórico inválido: {self.path}")
        turns = payload.get("turns")
        if payload.get("version") != 1 or not isinstance(turns, list):
            raise RuntimeError(f"Histórico inválido: {self.path}")
        try:
            return [self._parse_turn(turn) for turn in turns]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Histórico inválido: {self.path}") from exc

    @staticmethod
    def _parse_turn(raw: object) -> ConversationTurn:
        if not isinstance(raw, dict):
            raise TypeError("turno deve ser um objeto")
        status = raw["status"]
        if status not in {"pending", "complete", "error", "interrupted"}:
            raise ValueError("status inválido")
        timings = raw["timings_seconds"]
        if not isinstance(timings, dict) or not all(
            isinstance(key, str) and isinstance(value, (int, float))
            for key, value in timings.items()
        ):
            raise TypeError("tempos inválidos")
        if not all(isinstance(raw[key], str) for key in ("id", "transcript", "answer")):
            raise TypeError("campos inválidos")
        if not isinstance(raw["started_at"], (int, float)):
            raise TypeError("campos inválidos")
        error = raw["error"]
        completed_at = raw["completed_at"]
        if error is not None and not isinstance(error, str):
            raise TypeError("erro inválido")
        if completed_at is not None and not isinstance(completed_at, (int, float)):
            raise TypeError("horário inválido")
        return ConversationTurn(
            id=cast(str, raw["id"]),
            transcript=cast(str, raw["transcript"]),
            answer=cast(str, raw["answer"]),
            status=cast(TurnStatus, status),
            error=cast(str | None, error),
            started_at=float(cast(float, raw["started_at"])),
            completed_at=(
                None if completed_at is None else float(cast(float, completed_at))
            ),
            timings_seconds={key: float(value) for key, value in timings.items()},
        )

    def _write_locked(self) -> None:
        atomic_write_json(self.path, {"version": 1, "turns": self._turns})
