"""Persistent Deepgram input; silence is idle, never a failed conversation turn."""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode

from .stt import TranscriptionError


async def listen_session(source, *, stop, release, manual, on_ready, on_partial,
                         on_speech, on_utterance) -> None:
    from websockets.asyncio.client import connect
    from .agent import stop_process

    loop = asyncio.get_running_loop()
    began = loop.time()
    process = await asyncio.create_subprocess_exec(
        "arecord", "-q", "-D", source.device, "-f", "S16_LE", "-r", "16000",
        "-c", "1", "-t", "raw", stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    frames: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=100)
    tasks: list[asyncio.Task] = []
    parts: list[str] = []
    speech_at: float | None = None
    finalize_at: float | None = None
    last_word_end = 0.0
    closing = False

    def commit() -> None:
        nonlocal speech_at, finalize_at
        text = " ".join(parts).strip()
        parts.clear()
        speech_at = finalize_at = None
        if text:
            on_utterance(text)
        on_partial("")

    async def capture() -> None:
        first = True
        assert process.stdout is not None
        while True:
            # Keep the outstanding read alive across polls: no dropped first syllable.
            read = asyncio.create_task(process.stdout.read(1600))
            read_at = loop.time()
            try:
                while not read.done():
                    if stop.is_set():
                        return
                    if manual and (release.is_set() or loop.time() - began >= source.max_seconds):
                        await frames.put(None)
                        return
                    if loop.time() - read_at > 5:
                        raise TranscriptionError("O microfone não está enviando áudio.")
                    await asyncio.wait({read}, timeout=.02)
                chunk = read.result()
            finally:
                if not read.done():
                    read.cancel()
                    await asyncio.gather(read, return_exceptions=True)
            if not chunk:
                raise TranscriptionError("O microfone encerrou a captura.")
            if first:
                first = False
                on_ready()
            try:
                frames.put_nowait(chunk)
            except asyncio.QueueFull:
                raise TranscriptionError("A conexão não acompanha o áudio do microfone.") from None

    async def connection() -> None:
        nonlocal closing, speech_at, finalize_at, last_word_end
        query = urlencode(dict(model="nova-3", language="pt-BR", encoding="linear16",
            sample_rate=16000, channels=1, interim_results="true", punctuate="true",
            endpointing=source.endpoint_ms, utterance_end_ms=1000, vad_events="true"))
        async with connect("wss://api.deepgram.com/v1/listen?" + query,
            additional_headers={"Authorization": "Token " + source.api_key},
            open_timeout=5, close_timeout=1) as socket:
            async def send() -> None:
                nonlocal closing
                while (frame := await frames.get()) is not None:
                    await socket.send(frame)
                closing = True
                await stop_process(process)
                await socket.send(json.dumps({"type": "CloseStream"}))

            async def limits() -> None:
                nonlocal finalize_at, speech_at
                while True:
                    await asyncio.sleep(.05)
                    if closing:
                        # CloseStream must deliver finals/Metadata within a bounded wait.
                        await asyncio.sleep(5)
                        raise TranscriptionError("Tempo limite ao finalizar a gravação.")
                    if not manual and speech_at is not None:
                        if finalize_at is None and loop.time() - speech_at >= source.max_seconds:
                            finalize_at = loop.time()
                            await socket.send(json.dumps({"type": "Finalize"}))
                        elif finalize_at is not None and loop.time() - finalize_at >= 5:
                            raise TranscriptionError("Tempo limite ao finalizar a pergunta.")

            async def receive() -> None:
                nonlocal speech_at, finalize_at, last_word_end
                async for raw in socket:
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "Error":
                        raise TranscriptionError("Erro no serviço de transcrição.")
                    if kind == "SpeechStarted":
                        if speech_at is None:
                            speech_at = loop.time()
                        on_speech()
                    elif kind == "Results":
                        alternative = event["channel"]["alternatives"][0]
                        text = alternative["transcript"].strip()
                        if text and speech_at is None:
                            speech_at = loop.time()
                            on_speech()
                        if event.get("is_final"):
                            if text:
                                parts.append(text)
                                words = alternative.get("words", [])
                                last_word_end = words[-1]["end"] if words else 0
                            on_partial(" ".join(parts))
                        else:
                            on_partial(" ".join([*parts, text]).strip())
                        if not manual and (event.get("from_finalize") or event.get("speech_final")):
                            commit()
                    elif kind == "UtteranceEnd" and not manual:
                        # Ignore a delayed boundary belonging to an earlier segment.
                        if parts and event.get("last_word_end", last_word_end) >= last_word_end:
                            commit()
                    elif kind == "Metadata":
                        if closing:
                            commit()
                            return
                        raise TranscriptionError("Conexão de voz encerrada inesperadamente.")
                if closing:
                    commit()
                    return
                raise TranscriptionError("Conexão de voz encerrada inesperadamente.")

            sender = asyncio.create_task(send())
            limiter = asyncio.create_task(limits())
            receiver = asyncio.create_task(receive())
            inner = [sender, limiter, receiver]
            try:
                while True:
                    done, _ = await asyncio.wait([t for t in inner if not t.done()], return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    if receiver.done():
                        return
            finally:
                for task in inner:
                    task.cancel()
                await asyncio.gather(*inner, return_exceptions=True)

    async def stopped() -> None:
        while not stop.is_set():
            await asyncio.sleep(.02)

    try:
        recorder = asyncio.create_task(capture())
        network = asyncio.create_task(connection())
        stopper = asyncio.create_task(stopped())
        tasks = [recorder, network, stopper]
        while True:
            done, _ = await asyncio.wait([t for t in tasks if not t.done()], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            if stopper.done() or network.done():
                return
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await stop_process(process)
