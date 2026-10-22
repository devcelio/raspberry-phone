from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from raspberry_phone.assistant import AssistantError, PhoneAssistant
from raspberry_phone.conversation import ConversationHistory, ConversationStore
from raspberry_phone.state import StateStore


class FakeRecorder:
    def record(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"wav")


class FakeTranscriber:
    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe(self, _audio_path: Path) -> str:
        return self.text


class ConcurrentLLM:
    def __init__(self, first_audio: threading.Event) -> None:
        self.first_audio = first_audio
        self.completed = False

    def stream(self, _messages: list[dict[str, str]]):
        yield "Primeira frase."
        assert self.first_audio.wait(timeout=2), "a primeira frase não tocou durante o stream"
        yield " Segunda frase."
        self.completed = True


class ObservingSpeaker:
    def __init__(self, first_audio: threading.Event, llm: ConcurrentLLM) -> None:
        self.first_audio = first_audio
        self.llm = llm
        self.phrases: list[str] = []
        self.first_audio_preceded_llm_completion = False

    def speak(self, phrases, *, on_first_audio=None) -> None:
        for phrase in phrases:
            self.phrases.append(phrase)
            if len(self.phrases) == 1:
                self.first_audio_preceded_llm_completion = not self.llm.completed
                if on_first_audio:
                    on_first_audio()
                self.first_audio.set()


def build_assistant(
    tmp_path: Path, *, transcript: str, llm, speaker
) -> tuple[PhoneAssistant, ConversationHistory, StateStore]:
    history = ConversationHistory(max_turns=4)
    conversation = ConversationStore(tmp_path / "conversation.json")
    state = StateStore(
        tmp_path / "state.json", turns_provider=conversation.turns
    )
    assistant = PhoneAssistant(
        recorder=FakeRecorder(),
        transcriber=FakeTranscriber(transcript),
        llm=llm,
        speaker=speaker,
        history=history,
        conversation=conversation,
        state=state,
        runtime_dir=tmp_path,
        phrase_max_chars=180,
    )
    return assistant, history, state


def test_turn_speaks_first_sentence_before_llm_stream_completes(tmp_path: Path) -> None:
    first_audio = threading.Event()
    llm = ConcurrentLLM(first_audio)
    speaker = ObservingSpeaker(first_audio, llm)
    assistant, history, _state = build_assistant(
        tmp_path, transcript="Conte algo", llm=llm, speaker=speaker
    )

    result = assistant.run_turn()

    assert result is not None
    assert result.transcript == "Conte algo"
    assert result.answer == "Primeira frase. Segunda frase."
    assert speaker.phrases == ["Primeira frase.", "Segunda frase."]
    assert speaker.first_audio_preceded_llm_completion
    assert history.messages()[-1] == {
        "role": "assistant",
        "content": "Primeira frase. Segunda frase.",
    }
    assert set(result.timings_seconds) == {
        "recording",
        "transcription",
        "first_llm_token",
        "first_audio",
        "transcript_to_audio",
        "llm_total",
        "turn_total",
    }
    assert json.loads((tmp_path / "state.json").read_text())["status"] == "ready"
    assert assistant.conversation.turns()[0]["status"] == "complete"


def test_empty_transcript_returns_to_ready_without_calling_llm(tmp_path: Path) -> None:
    class Forbidden:
        def __getattr__(self, name: str):
            raise AssertionError(f"não deveria chamar {name}")

    assistant, history, _state = build_assistant(
        tmp_path, transcript="   ", llm=Forbidden(), speaker=Forbidden()
    )

    assert assistant.run_turn() is None
    assert history.messages() == []
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["status"] == "ready"
    assert state["answer"] == ""
    assert assistant.conversation.turns()[0]["status"] == "error"
    assert assistant.conversation.turns()[0]["transcript"] == ""


def test_turn_publishes_every_model_delta_to_live_state(tmp_path: Path) -> None:
    class TokenLLM:
        def stream(self, _messages):
            yield "Uma "
            yield "resposta"
            yield "."

    class DrainingSpeaker:
        def speak(self, phrases, *, on_first_audio=None) -> None:
            for _phrase in phrases:
                if on_first_audio:
                    on_first_audio()
                    on_first_audio = None

    assistant, _history, state = build_assistant(
        tmp_path,
        transcript="Pergunta",
        llm=TokenLLM(),
        speaker=DrainingSpeaker(),
    )

    result = assistant.run_turn()

    assert result is not None
    assert result.answer == "Uma resposta."
    assert state.snapshot()["revision"] == 8


def test_failed_stream_does_not_append_incomplete_turn(tmp_path: Path) -> None:
    class FailingLLM:
        def stream(self, _messages):
            yield "Trecho parcial."
            raise RuntimeError("rede caiu")

    class DrainingSpeaker:
        def speak(self, phrases, *, on_first_audio=None) -> None:
            for _phrase in phrases:
                if on_first_audio:
                    on_first_audio()
                    on_first_audio = None

    assistant, history, _state = build_assistant(
        tmp_path,
        transcript="Pergunta",
        llm=FailingLLM(),
        speaker=DrainingSpeaker(),
    )

    with pytest.raises(AssistantError, match="rede caiu"):
        assistant.run_turn()

    assert history.messages() == []
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["status"] == "error"
    assert state["answer"] == "Trecho parcial."
    assert assistant.conversation.turns()[0]["status"] == "error"
    assert assistant.conversation.turns()[0]["answer"] == "Trecho parcial."


def test_recording_failure_is_persisted_without_a_transcript(tmp_path: Path) -> None:
    class FailingRecorder:
        def record(self, _destination: Path) -> None:
            raise RuntimeError("microfone ausente")

    class Forbidden:
        def __getattr__(self, name: str):
            raise AssertionError(f"não deveria chamar {name}")

    assistant, history, _state = build_assistant(
        tmp_path, transcript="", llm=Forbidden(), speaker=Forbidden()
    )
    assistant.recorder = FailingRecorder()

    with pytest.raises(AssistantError, match="microfone ausente"):
        assistant.run_turn()

    assert history.messages() == []
    assert assistant.conversation.turns()[0]["status"] == "error"
    assert assistant.conversation.turns()[0]["transcript"] == ""
    assert assistant.conversation.turns()[0]["error"] == "microfone ausente"
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["status"] == "error"
    assert state["answer"] == ""


def test_keyboard_interrupt_publishes_stopped_state(tmp_path: Path) -> None:
    class InterruptedRecorder:
        def record(self, _destination: Path) -> None:
            raise KeyboardInterrupt

    class Forbidden:
        def __getattr__(self, name: str):
            raise AssertionError(f"não deveria chamar {name}")

    state = StateStore(tmp_path / "state.json")
    conversation = ConversationStore(tmp_path / "conversation.json")
    assistant = PhoneAssistant(
        recorder=InterruptedRecorder(),
        transcriber=Forbidden(),
        llm=Forbidden(),
        speaker=Forbidden(),
        history=ConversationHistory(),
        conversation=conversation,
        state=state,
        runtime_dir=tmp_path,
        phrase_max_chars=180,
    )

    with pytest.raises(KeyboardInterrupt):
        assistant.run_turn()

    assert json.loads((tmp_path / "state.json").read_text())["status"] == "stopped"
    assert conversation.turns()[0]["status"] == "error"
    assert conversation.turns()[0]["error"] == "Turno interrompido."
