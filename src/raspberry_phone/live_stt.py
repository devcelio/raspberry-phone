"""Bounded live input with microphone pre-roll and finalized utterances."""
from __future__ import annotations
import asyncio
import json
from collections.abc import Callable
from urllib.parse import urlencode
from .stt import TranscriptionError


class DeepgramSpeechInput:
    def __init__(self, *, api_key: str, device: str, max_seconds: int = 30,
                 endpoint_ms: int = 600, no_speech_seconds: float = 6) -> None:
        self.api_key, self.device = api_key, device
        self.max_seconds, self.endpoint_ms = max_seconds, endpoint_ms
        self.no_speech_seconds = no_speech_seconds

    def listen(self, on_partial: Callable[[str], None],
               on_ready: Callable[[], None] | None = None) -> str:
        try:
            return asyncio.run(self._listen(on_partial, on_ready))
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError("Falha na transcrição ao vivo. Confira rede e chave Deepgram.") from exc

    def listen_session(self, **callbacks) -> None:
        from .session_input import listen_session
        try:
            asyncio.run(listen_session(self, **callbacks))
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError("Falha na sessão de voz. Confira o microfone e a conexão.") from exc

    async def _listen(self, on_partial, on_ready=None) -> str:
        from websockets.asyncio.client import connect
        from .agent import stop_process
        capture_started = asyncio.get_running_loop().time()
        process = await asyncio.create_subprocess_exec(
            "arecord", "-q", "-D", self.device, "-f", "S16_LE", "-r", "16000",
            "-c", "1", "-t", "raw", "-d", str(self.max_seconds),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        # Bound memory without dropping the first syllables during connection setup.
        frames: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=640)
        started_speech = asyncio.Event()
        async def capture():
            assert process.stdout is not None
            first = True
            while chunk := await process.stdout.read(1600):
                if first:
                    first = False
                    if on_ready: on_ready()
                await frames.put(chunk)
            if await process.wait() != 0:
                raise TranscriptionError("Falha no microfone.")
            await frames.put(None)
        recorder = asyncio.create_task(capture())
        tasks = [recorder]
        try:
            query = urlencode(dict(model="nova-3", language="pt-BR", encoding="linear16",
                sample_rate=16000, channels=1, interim_results="true", punctuate="true",
                endpointing=self.endpoint_ms, utterance_end_ms=1000, vad_events="true"))
            async with asyncio.timeout(self.max_seconds + 5):
                async with connect("wss://api.deepgram.com/v1/listen?" + query,
                    additional_headers={"Authorization": "Token " + self.api_key},
                    open_timeout=5, close_timeout=1) as socket:
                    async def send():
                        while (chunk := await frames.get()) is not None:
                            await socket.send(chunk)
                        await socket.send(json.dumps({"type":"CloseStream"}))
                    async def receive():
                        parts = []
                        async for raw in socket:
                            event = json.loads(raw)
                            kind = event.get("type")
                            if kind == "Error": raise TranscriptionError("Erro no serviço de transcrição.")
                            if kind == "SpeechStarted": started_speech.set()
                            if kind in {"UtteranceEnd", "Metadata"}:
                                return " ".join(parts).strip()
                            if kind != "Results": continue
                            text = event["channel"]["alternatives"][0]["transcript"].strip()
                            if text: started_speech.set()
                            if event.get("is_final"):
                                if text: parts.append(text)
                                partial = " ".join(parts)
                            else: partial = " ".join([*parts, text]).strip()
                            on_partial(partial)
                            # speech_final commits a segment; UtteranceEnd confirms 1 s gap.
                        raise TranscriptionError("Conexão encerrada antes da transcrição final.")
                    async def silence_timeout():
                        try:
                            await asyncio.wait_for(started_speech.wait(), max(.001, self.no_speech_seconds - (asyncio.get_running_loop().time() - capture_started)))
                        except TimeoutError:
                            raise TranscriptionError("Nenhuma fala detectada. Toque em Falar e tente novamente.") from None
                        await asyncio.Future()
                    receiver = asyncio.create_task(receive())
                    tasks.extend([asyncio.create_task(send()), receiver, asyncio.create_task(silence_timeout())])
                    while not receiver.done():
                        done, _ = await asyncio.wait({t for t in tasks if not t.done()}, return_when=asyncio.FIRST_COMPLETED)
                        for task in done: task.result()
                    return receiver.result()
        except TimeoutError:
            raise TranscriptionError("Tempo limite da transcrição.") from None
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await stop_process(process)
