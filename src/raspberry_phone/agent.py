"""Deepgram manages speech and calls our selected OpenRouter model directly."""
from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from .assistant import AssistantError, TurnResult
from .config import AppConfig
from .conversation import ConversationHistory, ConversationStore
from .state import StateStore


def agent_settings(config: AppConfig, history: ConversationHistory) -> dict[str, Any]:
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 16000},
            "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
        },
        "agent": {
            "context": {"messages": [dict(type="History", **m) for m in history.messages()]},
            "listen": {"provider": {
                "type": "deepgram", "version": "v2", "model": "flux-general-multi",
                "language_hints": ["pt"],
            }},
            "think": {
                "provider": {"type": "open_ai", "model": config.openrouter_model},
                "endpoint": {
                    "url": config.openrouter_base_url + "/chat/completions",
                    "headers": {"Authorization": "Bearer " + config.openrouter_api_key},
                },
                "prompt": config.system_prompt,
            },
            "speak": {"provider": {
                "type": "cartesia", "model_id": config.agent_voice_model,
                "voice": {"mode": "id", "id": config.agent_voice_id}, "language": "pt",
            }},
        },
    }


async def stop_process(process: Any) -> None:
    if process is None or process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 2)
    except TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()


class VoiceAgentAssistant:
    """A bounded, half-duplex turn. Close the paid session after playback drains."""

    def __init__(self, config: AppConfig, history: ConversationHistory,
                 conversation: ConversationStore, state: StateStore) -> None:
        self.config, self.history = config, history
        self.conversation, self.state = conversation, state

    def run_turn(self) -> TurnResult | None:
        return asyncio.run(self.run_session())

    async def run_session(self, *, test_text: str | None = None,
                          audio_file: str | None = None, play_audio: bool = True) -> TurnResult | None:
        started = time.monotonic()
        timings: dict[str, float] = {}
        transcript, answer = "", ""
        turn_id = self.conversation.begin_turn("")
        capture = playback = None
        tasks: list[asyncio.Task[Any]] = []
        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=256)
        input_finished = asyncio.Event()
        speech_started = asyncio.Event()
        audio_bytes = 0

        def publish(status: str, *, durable: bool = False) -> None:
            self.state.publish(status, transcript=transcript, answer=answer,
                               timings_seconds=timings, durable=durable)

        async def play() -> None:
            nonlocal playback, audio_bytes
            while (chunk := await audio_queue.get()) is not None:
                if play_audio:
                    if playback is None:
                        playback = await asyncio.create_subprocess_exec(
                            "aplay", "-q", "--buffer-time=120000", "--period-time=20000", "-D", self.config.audio_playback_device,
                            "-t", "raw", "-f", "S16_LE", "-r", "24000", "-c", "1",
                            stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                        )
                    assert playback.stdin is not None
                    playback.stdin.write(chunk)
                    await playback.stdin.drain()
                audio_bytes += len(chunk)
                if "first_audio_received" not in timings:
                    now = time.monotonic() - started
                    timings["first_audio_received"] = now
                    if "transcript_final" in timings:
                        timings["transcript_to_audio"] = now - timings["transcript_final"]
                    publish("speaking")
            if playback is not None:
                assert playback.stdin is not None
                playback.stdin.close()
                if await playback.wait() != 0:
                    raise AssistantError("Falha ao reproduzir a resposta no headset.")

        try:
            from deepgram import AsyncDeepgramClient

            publish("starting", durable=True)
            first_frame = b""
            if test_text is None and audio_file is None:
                capture = await asyncio.create_subprocess_exec(
                    "arecord", "-q", "-D", self.config.audio_capture_device,
                    "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw",
                    "-d", str(self.config.speech_max_seconds),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                assert capture.stdout is not None
                first_frame = await asyncio.wait_for(capture.stdout.read(1600), 2)
                if not first_frame: raise AssistantError("Microfone sem áudio.")
                publish("recording", durable=True)
            async with asyncio.timeout(self.config.agent_session_seconds):
                client = AsyncDeepgramClient(api_key=self.config.deepgram_api_key)
                async with client.agent.v1.connect() as connection:
                    await connection.send_raw(agent_settings(self.config, self.history))
                    # Never open the microphone before the service accepts the settings.
                    async with asyncio.timeout(15):
                        while True:
                            event = await connection.recv()
                            kind = getattr(event, "type", "")
                            if kind == "Error":
                                raise AssistantError("Deepgram recusou a configuração: " + str(getattr(event, "code", "erro")))
                            if kind == "SettingsApplied":
                                break
                    timings["connection"] = time.monotonic() - started
                    publish("recording", durable=True)

                    async def feed() -> None:
                        nonlocal capture
                        if test_text is not None:
                            await connection.send_raw({"type": "InjectUserMessage", "content": test_text})
                        elif audio_file is not None:
                            from pathlib import Path
                            pcm = Path(audio_file).read_bytes()
                            for offset in range(0, len(pcm), 1600):
                                if input_finished.is_set():
                                    break
                                await connection.send_media(pcm[offset:offset + 1600])
                                await asyncio.sleep(.05)
                            await connection.send_force_end_turn()
                        else:
                            assert capture is not None
                            await connection.send_media(first_frame)
                            assert capture.stdout is not None
                            while not input_finished.is_set():
                                chunk = await capture.stdout.read(1600)
                                if not chunk:
                                    if input_finished.is_set():
                                        break
                                    if await capture.wait() != 0:
                                        raise AssistantError("Falha no microfone. Confira AUDIO_CAPTURE_DEVICE.")
                                    await connection.send_force_end_turn()
                                    break
                                await connection.send_media(chunk)
                            await stop_process(capture)
                        while True:
                            await connection.send_keep_alive()
                            await asyncio.sleep(5)

                    async def receive() -> None:
                        nonlocal transcript, answer
                        async for event in connection:
                            if isinstance(event, bytes):
                                await audio_queue.put(event)
                                continue
                            kind = getattr(event, "type", "")
                            if kind == "Error":
                                raise AssistantError("Erro no Voice Agent: " + str(getattr(event, "code", "erro")))
                            if kind == "UserStartedSpeaking":
                                speech_started.set()
                            if kind == "ConversationText":
                                content = getattr(event, "content", "")
                                if getattr(event, "role", "") == "user":
                                    speech_started.set()
                                    transcript = (transcript + " " + content).strip()
                                    timings.setdefault("transcript_final", time.monotonic() - started)
                                    self.conversation.update_transcript(turn_id, transcript)
                                    input_finished.set()
                                    await stop_process(capture)
                                    publish("thinking")
                                else:
                                    answer = (answer + " " + content).strip()
                                    timings.setdefault("first_answer_text", time.monotonic() - started)
                                    publish("speaking" if audio_bytes else "thinking")
                            elif kind == "AgentAudioDone":
                                await audio_queue.put(None)
                                return
                        raise AssistantError("A conexão terminou antes de concluir a resposta.")

                    sender = asyncio.create_task(feed())
                    async def silence_deadline():
                        try:
                            await asyncio.wait_for(speech_started.wait(), 6)
                        except TimeoutError:
                            raise AssistantError("Nenhuma pergunta detectada em 6 segundos.") from None
                        await asyncio.Future()
                    async def response_deadline():
                        await input_finished.wait()
                        await asyncio.sleep(10)
                        if not audio_bytes:
                            raise AssistantError("Sem resposta em 10 segundos; sessão encerrada.")
                        await asyncio.Future()
                    receiver = asyncio.create_task(receive())
                    player = asyncio.create_task(play())
                    tasks = [sender, receiver, player, asyncio.create_task(response_deadline()), asyncio.create_task(silence_deadline())]
                    # A capture or playback failure must also unblock the receiver.
                    while not (receiver.done() and player.done()):
                        pending = {t for t in tasks if not t.done()}
                        done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
            if not transcript or not answer or not audio_bytes:
                raise AssistantError("A conversa não retornou texto e áudio completos. Tente novamente.")
            timings["turn_total"] = time.monotonic() - started
            self.conversation.complete_turn(turn_id, answer, timings_seconds=timings)
            self.history.add_turn(transcript, answer)
            publish("ready", durable=True)
            return TurnResult(transcript, answer, timings)
        except BaseException as exc:
            if isinstance(exc, AssistantError):
                message = str(exc)
            elif isinstance(exc, TimeoutError):
                message = "Tempo limite da conversa. Tente novamente."
            elif isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                message = "Conversa interrompida."
            else:
                # SDK errors can contain authenticated request headers.
                message = "Falha na conexão ou no áudio. Confira as chaves, a rede e o headset."
            self.conversation.fail_turn(turn_id, answer, message, timings_seconds=timings)
            self.state.publish("error", transcript=transcript, answer=answer,
                               timings_seconds=timings, error=message)
            if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                raise
            raise AssistantError(message) from None
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await stop_process(capture)
            await stop_process(playback)
