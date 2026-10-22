from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .storage import atomic_write_json


STATUSES = frozenset(
    {
        "starting",
        "ready",
        "recording",
        "transcribing",
        "thinking",
        "speaking",
        "error",
        "stopped",
    }
)


class StateStore:
    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float] = time.time,
        turns_provider: Callable[[], object] = list,
        live_interval: float = 0,
    ) -> None:
        self.live_interval = live_interval
        self.path = path
        self._clock = clock
        self._turns_provider = turns_provider
        self._lock = threading.RLock()
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self._revision = 0
        self._last_live_emit = 0.0
        self._live_timer: threading.Timer | None = None
        self._cached_turns: object = []
        self._session: dict[str, Any] = {
            "session_supported": False, "mode": "continuous", "session_active": False,
            "listening": False, "input_transcript": "", "response_status": "idle",
            "capture_id": None,
        }
        self._state: dict[str, Any] = {
            "status": "starting",
            "transcript": "",
            "answer": "",
            "timings_seconds": {},
            "error": None,
            "updated_at": self._clock(),
        }

    def publish(
        self,
        status: str,
        *,
        transcript: str = "",
        answer: str = "",
        timings_seconds: Mapping[str, float] | None = None,
        error: str | None = None,
        durable: bool = True,
        response_status: str | None = None,
    ) -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"status desconhecido: {status}")

        with self._lock:
            if response_status is not None:
                self._session["response_status"] = response_status
            self._revision += 1
            self._state = {
                "status": status,
                "transcript": transcript,
                "answer": answer,
                "timings_seconds": dict(timings_seconds or {}),
                "error": error,
                "updated_at": self._clock(),
            }
            if durable:
                self._cached_turns = self._turns_provider()
            now = time.monotonic()
            if not durable and now - self._last_live_emit < self.live_interval:
                # Coalesce a burst, but always deliver its final text, even if
                # no further token arrives (silence or slow first audio).
                if self._live_timer is None:
                    self._live_timer = threading.Timer(
                        self.live_interval - (now - self._last_live_emit),
                        self._flush_live,
                    )
                    self._live_timer.daemon = True
                    self._live_timer.start()
                return self._snapshot_locked()
            if self._live_timer is not None:
                self._live_timer.cancel()
                self._live_timer = None
            self._last_live_emit = now
            state = self._snapshot_locked()
            if durable:
                self._write_locked(state)
            for subscriber in self._subscribers:
                subscriber.put_nowait(state)
            return state

    def _flush_live(self) -> None:
        with self._lock:
            self._live_timer = None
            self._last_live_emit = time.monotonic()
            snapshot = self._snapshot_locked()
            for subscriber in self._subscribers:
                subscriber.put_nowait(snapshot)

    def session_update(self, *, durable: bool = True, **fields: Any) -> None:
        with self._lock:
            self._session.update(fields)
            self.publish(**{k: v for k, v in self._state.items() if k != "updated_at"}, durable=durable)

    def subscribe(self) -> "StateSubscription":
        events: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._lock:
            self._subscribers.add(events)
            initial = self._snapshot_locked()
        return StateSubscription(self, events, initial)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, Any]:
        turns = self._cached_turns
        current_turn = None
        if isinstance(turns, list):
            current_turn = next(
                (
                    turn
                    for turn in reversed(turns)
                    if isinstance(turn, dict) and turn.get("status") == "pending"
                ),
                None,
            )
        return {
            **self._state,
            **self._session,
            "revision": self._revision,
            "turns": turns,
            "current_turn": current_turn,
        }

    def _write_locked(self, state: Mapping[str, Any]) -> None:
        atomic_write_json(self.path, state)

    def _unsubscribe(self, events: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(events)


class StateSubscription:
    def __init__(
        self,
        store: StateStore,
        events: queue.Queue[dict[str, Any]],
        initial: dict[str, Any],
    ) -> None:
        self._store = store
        self._events = events
        self.initial = initial
        self._closed = False

    def next(self, *, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        if not self._closed:
            self._store._unsubscribe(self._events)
            self._closed = True
