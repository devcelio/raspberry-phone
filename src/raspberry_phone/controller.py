from __future__ import annotations

import threading
from typing import Any, Protocol, cast

from .assistant import PhoneAssistant

from .conversation import ConversationHistory, ConversationStore
from .state import StateStore
from .session import ConversationSession


class AssistantRunner(Protocol):
    def run_turn(self) -> Any: ...


class TurnBusyError(RuntimeError):
    pass


class TurnController:
    def __init__(
        self,
        assistant: AssistantRunner,
        *,
        history: ConversationHistory,
        conversation: ConversationStore,
        state: StateStore,
    ) -> None:
        self.assistant = assistant
        self.history = history
        self.conversation = conversation
        self.state = state
        self._condition = threading.Condition()
        self._busy = False
        self._accepting = True
        self._session: ConversationSession | None = None
        self.session_supported = callable(getattr(getattr(assistant, "speech_input", None), "listen_session", None))
        self.state.session_update(session_supported=self.session_supported)

    @property
    def busy(self) -> bool:
        with self._condition:
            return self._busy

    def run_turn(self) -> Any:
        self._reserve_turn()
        try:
            return self.assistant.run_turn()
        finally:
            self._release_turn()

    def start_turn(self) -> bool:
        try:
            self._reserve_turn()
        except TurnBusyError:
            return False
        thread = threading.Thread(
            target=self._run_reserved,
            name="phone-turn",
        )
        try:
            thread.start()
        except BaseException:
            self._release_turn()
            raise
        return True

    def set_mode(self, mode: str) -> bool:
        with self._condition:
            if not self.session_supported or self._busy or not self._accepting:
                return False
            if mode not in {"continuous", "push-to-talk"}:
                return False
            self.state.session_update(mode=mode)
            return True

    def start_session(self, mode: str, capture_id: str | None = None) -> bool:
        with self._condition:
            if not self.session_supported or self._busy or not self._accepting:
                return False
            if mode != self.state.snapshot()["mode"]:
                return False
            if mode == "push-to-talk" and not capture_id:
                return False
            self._busy = True
            session = ConversationSession(cast(PhoneAssistant, self.assistant), mode, capture_id)
            self._session = session
            self.state.publish("starting")
            self.state.session_update(session_active=True, capture_id=capture_id)
            try:
                threading.Thread(target=self._run_session, args=(session,), name="phone-session").start()
            except BaseException:
                self._session = None
                self._busy = False
                self.state.session_update(session_active=False, capture_id=None)
                raise
            return True

    def stop_session(self, *, capture_id: str | None = None, release: bool = False) -> bool:
        with self._condition:
            session = self._session
            if session is None:
                return False
            if session.mode == "push-to-talk" and capture_id != session.capture_id:
                return False
            if release:
                if session.mode != "push-to-talk":
                    return False
                session.release.set()
                return True
        session.cancel()
        return True

    def _run_session(self, session: ConversationSession) -> None:
        error = None
        try:
            session.run()
        except Exception as exc:
            error = str(exc)
        finally:
            with self._condition:
                self._session = None
                self.state.publish("error" if error else "ready", error=error)
                self.state.session_update(session_active=False, listening=False,
                                          response_status="idle", input_transcript="", capture_id=None)
                self._busy = False
                self._condition.notify_all()

    def reset_conversation(self) -> bool:
        with self._condition:
            if self._busy or not self._accepting:
                return False
            self.conversation.clear()
            self.history.clear()
            self.state.publish("ready")
            return True

    def shutdown(self) -> None:
        with self._condition:
            self._accepting = False
            session = self._session
        if session:
            session.cancel()
        with self._condition:
            self._condition.wait_for(lambda: not self._busy)

    def _reserve_turn(self) -> None:
        with self._condition:
            if self._busy or not self._accepting:
                raise TurnBusyError("Já existe um turno em andamento")
            self._busy = True

    def _release_turn(self) -> None:
        with self._condition:
            self._busy = False
            self._condition.notify_all()

    def _run_reserved(self) -> None:
        try:
            self.assistant.run_turn()
        except Exception:
            # PhoneAssistant already publishes a user-facing error state.
            pass
        finally:
            self._release_turn()
