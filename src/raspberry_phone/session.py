"""A server-owned microphone session with one serialized response worker."""
from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

from .cancellation import Cancellation, ResponseCancelled
from .response import respond

if TYPE_CHECKING:
    from .assistant import PhoneAssistant


class ConversationSession:
    def __init__(self, assistant: PhoneAssistant, mode: str, capture_id: str | None) -> None:
        self.assistant = assistant
        self.mode = mode
        self.capture_id = capture_id
        self.stop = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self._response: Cancellation | None = None
        self._generation = 0
        self._pending: queue.Queue[tuple[int, str] | None] = queue.Queue()
        self._errors: list[Exception] = []

    def cancel(self) -> None:
        self.stop.set()
        with self._lock:
            response = self._response
        if response:
            response.cancel()

    def speech_started(self) -> None:
        with self._lock:
            self._generation += 1
            response = self._response
        if response:
            response.cancel()

    def utterance(self, text: str) -> None:
        if text.strip() and not self.stop.is_set():
            with self._lock:
                self._pending.put((self._generation, text.strip()))
        self.assistant.state.session_update(input_transcript="", durable=False)

    def _respond(self) -> None:
        while (item := self._pending.get()) is not None:
            generation, text = item
            with self._lock:
                if self.stop.is_set() or generation != self._generation:
                    continue
                cancel = Cancellation()
                self._response = cancel
            try:
                respond(self.assistant, text, cancel)
            except ResponseCancelled:
                pass
            except Exception as exc:
                self._errors.append(exc)
                self.cancel()
            finally:
                with self._lock:
                    self._response = None

    def run(self) -> None:
        worker = threading.Thread(target=self._respond, name="session-response")
        worker.start()
        try:
            assert self.assistant.speech_input is not None
            self.assistant.speech_input.listen_session(
                stop=self.stop, release=self.release, manual=self.mode == "push-to-talk",
                on_ready=lambda: self.assistant.state.session_update(listening=True),
                on_partial=lambda text: self.assistant.state.session_update(input_transcript=text, durable=False),
                on_speech=self.speech_started, on_utterance=self.utterance,
            )
        except Exception as exc:
            self._errors.append(exc)
            self.cancel()
        finally:
            self.assistant.state.session_update(listening=False)
            self._pending.put(None)
            worker.join()
        if self._errors:
            raise self._errors[0]
