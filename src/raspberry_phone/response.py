"""Generate one cancellable answer independently of microphone capture."""
from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

from .cancellation import Cancellation, ResponseCancelled
from .chunking import SentenceChunker

if TYPE_CHECKING:
    from .assistant import PhoneAssistant

INTERRUPTED_CONTEXT = "[A resposta foi interrompida. Não presuma que o usuário a ouviu.]"


def respond(assistant: PhoneAssistant, transcript: str, cancel: Cancellation) -> None:
    cancel.check()
    turn_id = assistant.conversation.begin_turn(transcript)
    parts: list[str] = []
    phrases: queue.Queue[str | None] = queue.Queue(maxsize=8)
    errors: list[Exception] = []
    speaking = threading.Event()

    def publish(*, durable: bool = False) -> None:
        def update() -> None:
            status = "speaking" if speaking.is_set() else "thinking"
            assistant.state.publish(status, transcript=transcript, answer="".join(parts),
                                    response_status=status, durable=durable)
        cancel.apply(update)

    def put(phrase: str | None) -> None:
        while True:
            cancel.check()
            try:
                phrases.put(phrase, timeout=.05)
                return
            except queue.Full:
                continue

    def produce() -> None:
        try:
            chunker = SentenceChunker(max_chars=assistant.phrase_max_chars)
            messages = [*assistant.history.messages(), {"role": "user", "content": transcript}]
            for delta in assistant.llm.stream(messages, cancel=cancel):
                cancel.apply(lambda: parts.append(delta))
                publish()
                for phrase in chunker.feed(delta):
                    put(phrase)
            for phrase in chunker.flush():
                put(phrase)
        except ResponseCancelled:
            pass
        except Exception as exc:
            errors.append(exc)
        finally:
            try:
                put(None)
            except ResponseCancelled:
                pass

    def phrase_stream():
        while True:
            cancel.check()
            try:
                phrase = phrases.get(timeout=.05)
            except queue.Empty:
                continue
            if phrase is None:
                return
            yield phrase

    def first_audio() -> None:
        speaking.set()
        publish(durable=True)

    producer = threading.Thread(target=produce, name="session-llm")
    failed = False
    try:
        cancel.apply(lambda: assistant.state.publish("thinking", transcript=transcript, response_status="thinking"))
        publish()
        producer.start()
        assistant.speaker.speak(phrase_stream(), on_first_audio=first_audio, cancel=cancel)
        producer.join()
        cancel.check()
        if errors:
            raise errors[0]
        answer = "".join(parts).strip()
        if not answer or not speaking.is_set():
            raise RuntimeError("A resposta não gerou áudio.")
        def complete() -> None:
            assistant.conversation.complete_turn(turn_id, answer)
            assistant.history.add_turn(transcript, answer)
            assistant.state.publish("ready", transcript=transcript, answer=answer, response_status="idle")
        cancel.apply(complete)
    except ResponseCancelled:
        assistant.conversation.interrupt_turn(turn_id, "".join(parts).strip())
        assistant.history.add_turn(transcript, INTERRUPTED_CONTEXT)
    except Exception as exc:
        failed = True
        cancel.cancel()
        assistant.conversation.fail_turn(turn_id, "".join(parts).strip(), str(exc))
        raise
    finally:
        if producer.ident is not None:
            producer.join()
        if not failed:
            assistant.state.session_update(response_status="idle")
