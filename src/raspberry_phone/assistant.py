from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .chunking import SentenceChunker
from .cancellation import Cancellation
from .conversation import ConversationHistory, ConversationStore
from .state import StateStore


class Recorder(Protocol):
    def record(self, destination: Path) -> None: ...


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...


class SpeechInput(Protocol):
    def listen_session(self, **callbacks) -> None: ...

    def listen(self, on_partial: Callable[[str], None], on_ready: Callable[[], None] | None = None) -> str: ...


class LanguageModel(Protocol):
    def stream(self, messages: Sequence[dict[str, str]], *, cancel: Cancellation | None = None) -> Iterable[str]: ...


class Speaker(Protocol):
    def speak(
        self,
        phrases: Iterable[str],
        *,
        on_first_audio: Callable[[], None] | None = None,
        cancel: Cancellation | None = None,
    ) -> None: ...


class AssistantError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TurnResult:
    transcript: str
    answer: str
    timings_seconds: dict[str, float]


class PhoneAssistant:
    def __init__(
        self,
        *,
        recorder: Recorder,
        transcriber: Transcriber,
        llm: LanguageModel,
        speaker: Speaker,
        history: ConversationHistory,
        conversation: ConversationStore,
        state: StateStore,
        runtime_dir: Path,
        phrase_max_chars: int,
        clock: Callable[[], float] = time.monotonic,
        speech_input: SpeechInput | None = None,
    ) -> None:
        self.speech_input = speech_input
        self.recorder = recorder
        self.transcriber = transcriber
        self.llm = llm
        self.speaker = speaker
        self.history = history
        self.conversation = conversation
        self.state = state
        self.runtime_dir = runtime_dir
        self.phrase_max_chars = phrase_max_chars
        self._clock = clock

    def run_turn(self) -> TurnResult | None:
        started_at = self._clock()
        timings: dict[str, float] = {}
        transcript = ""
        answer_parts: list[str] = []
        turn_id: str | None = None
        turn_finished = False
        audio_path = self.runtime_dir / "input.wav"

        def fail_pending_turn(message: str) -> None:
            nonlocal turn_finished
            if turn_id is None or turn_finished:
                return
            self.conversation.fail_turn(
                turn_id,
                answer="".join(answer_parts).strip(),
                error=message,
                timings_seconds=timings,
            )
            turn_finished = True

        try:
            turn_id = self.conversation.begin_turn("")
            self.state.publish("starting" if self.speech_input else "recording")
            if self.speech_input is not None:
                def on_partial(text: str) -> None:
                    nonlocal transcript
                    transcript = text
                    self.state.publish("recording", transcript=text, durable=False)

                def on_ready() -> None:
                    self.state.publish("recording")
                transcript = self.speech_input.listen(on_partial, on_ready=on_ready).strip()
                transcribed_at = self._clock()
                timings["streaming_input"] = transcribed_at - started_at
            else:
                self.recorder.record(audio_path)
                recorded_at = self._clock()
                timings["recording"] = recorded_at - started_at
                self.state.publish("transcribing", timings_seconds=timings)
                transcript = self.transcriber.transcribe(audio_path).strip()
                transcribed_at = self._clock()
                timings["transcription"] = transcribed_at - recorded_at
            self.conversation.update_transcript(turn_id, transcript)

            if not transcript:
                fail_pending_turn("Não foi possível entender a gravação.")
                self.state.publish("ready", timings_seconds=timings)
                return None

            self.state.publish(
                "thinking", transcript=transcript, timings_seconds=timings
            )
            llm_started_at = self._clock()
            phrases: queue.Queue[str | object] = queue.Queue()
            sentinel = object()
            producer_errors: list[BaseException] = []
            audio_started = threading.Event()

            def publish_partial(*, durable: bool = False) -> None:
                self.state.publish(
                    "speaking" if audio_started.is_set() else "thinking",
                    transcript=transcript,
                    answer="".join(answer_parts).strip(),
                    timings_seconds=timings,
                    durable=durable,
                )

            def produce() -> None:
                chunker = SentenceChunker(max_chars=self.phrase_max_chars)
                try:
                    request_messages = [
                        *self.history.messages(),
                        {"role": "user", "content": transcript},
                    ]
                    for delta in self.llm.stream(request_messages):
                        if "first_llm_token" not in timings:
                            timings["first_llm_token"] = self._clock() - llm_started_at
                        answer_parts.append(delta)
                        publish_partial()
                        for phrase in chunker.feed(delta):
                            phrases.put(phrase)
                    for phrase in chunker.flush():
                        phrases.put(phrase)
                except BaseException as exc:
                    producer_errors.append(exc)
                finally:
                    timings["llm_total"] = self._clock() - llm_started_at
                    phrases.put(sentinel)

            def phrase_stream() -> Iterable[str]:
                while True:
                    item = phrases.get()
                    if item is sentinel:
                        return
                    assert isinstance(item, str)
                    yield item

            def mark_first_audio() -> None:
                audio_started.set()
                audio_at = self._clock()
                timings["first_audio"] = audio_at - started_at
                timings["transcript_to_audio"] = audio_at - transcribed_at
                publish_partial(durable=True)

            producer = threading.Thread(
                target=produce, name="openrouter-stream", daemon=True
            )
            producer.start()
            speaker_error: BaseException | None = None
            try:
                self.speaker.speak(
                    phrase_stream(), on_first_audio=mark_first_audio
                )
            except BaseException as exc:
                speaker_error = exc
            producer.join()

            if speaker_error is not None:
                raise speaker_error
            if producer_errors:
                raise producer_errors[0]

            answer = "".join(answer_parts).strip()
            if not answer:
                raise AssistantError("O modelo retornou uma resposta vazia")
            if "first_audio" not in timings:
                raise AssistantError("A resposta não gerou áudio")

            timings["turn_total"] = self._clock() - started_at
            self.conversation.complete_turn(
                turn_id,
                answer,
                timings_seconds=timings,
            )
            turn_finished = True
            self.history.add_turn(transcript, answer)
            self.state.publish(
                "ready",
                transcript=transcript,
                answer=answer,
                timings_seconds=timings,
            )
            return TurnResult(
                transcript=transcript,
                answer=answer,
                timings_seconds=dict(timings),
            )
        except KeyboardInterrupt:
            fail_pending_turn("Turno interrompido.")
            self.state.publish(
                "stopped",
                transcript=transcript,
                answer="".join(answer_parts).strip(),
                timings_seconds=timings,
            )
            raise
        except Exception as exc:
            fail_pending_turn(str(exc))
            self.state.publish(
                "error",
                transcript=transcript,
                answer="".join(answer_parts).strip(),
                timings_seconds=timings,
                error=str(exc),
            )
            if isinstance(exc, AssistantError):
                raise
            raise AssistantError(str(exc)) from exc
