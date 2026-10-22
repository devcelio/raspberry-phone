"""Cancellation shared by response generation and audio playback."""
from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import suppress


class ResponseCancelled(Exception):
    pass


class Cancellation:
    def __init__(self) -> None:
        self.event = threading.Event()
        self._lock = threading.RLock()
        self._callbacks: list[Callable[[], None]] = []

    def check(self) -> None:
        if self.event.is_set():
            raise ResponseCancelled()

    def apply(self, action: Callable[[], object]) -> None:
        """Serialize publication with cancellation, excluding stale output."""
        with self._lock:
            self.check()
            action()

    def register(self, callback: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            cancelled = self.event.is_set()
            if not cancelled:
                self._callbacks.append(callback)
        if cancelled:
            callback()
        def remove() -> None:
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)
        return remove

    def cancel(self) -> None:
        with self._lock:
            self.event.set()
            callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            with suppress(Exception):
                callback()
