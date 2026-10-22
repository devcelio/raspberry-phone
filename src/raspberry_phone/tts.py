from __future__ import annotations

import subprocess
import json
import queue
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, BinaryIO

from .cancellation import Cancellation, ResponseCancelled


class SpeechError(RuntimeError):
    pass


def _load_piper_voice(model_path: Path) -> Any:
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise SpeechError(
            "Dependência piper-tts ausente; execute o bootstrap do projeto"
        ) from exc
    try:
        from piper.config import PiperConfig
        import onnxruntime
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        return PiperVoice(config=PiperConfig.from_dict(json.loads(Path(str(model_path) + ".json").read_text())),
                          session=onnxruntime.InferenceSession(str(model_path), sess_options=options,
                                                              providers=["CPUExecutionProvider"]))
    except Exception as exc:
        raise SpeechError(f"Não foi possível carregar a voz Piper: {exc}") from exc


class PiperSpeechPlayer:
    """Synthesize queued phrases and send their PCM to one ordered aplay stream."""

    def __init__(
        self,
        model_path: Path,
        playback_device: str,
        *,
        voice_loader: Callable[[Path], Any] = _load_piper_voice,
        popen: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self.playback_device = playback_device
        self._voice = voice_loader(model_path)
        self._popen = popen

    def warmup(self) -> None:
        for _ in self._voice.synthesize("Oi."):
            pass

    def speak(
        self,
        phrases: Iterable[str],
        *,
        on_first_audio: Callable[[], None] | None = None,
        cancel: Cancellation | None = None,
    ) -> None:
        process: Any | None = None
        stream: BinaryIO | None = None
        first_audio_sent = False
        remove_cancel = lambda: None

        def abort_playback() -> None:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        chunks: queue.Queue[Any] = queue.Queue(maxsize=2)
        stop = threading.Event()
        end = object()
        errors: list[Exception] = []
        def put(item: Any) -> None:
            while not stop.is_set() and not (cancel and cancel.event.is_set()):
                try:
                    chunks.put(item, timeout=.1)
                    return
                except queue.Full:
                    pass
        def synthesize() -> None:
            try:
                for phrase in phrases:
                    if stop.is_set() or (cancel and cancel.event.is_set()): break
                    for chunk in self._voice.synthesize(phrase):
                        put(chunk)
                        if stop.is_set() or (cancel and cancel.event.is_set()): return
            except Exception as exc:
                errors.append(exc)
            finally:
                put(end)
        producer = threading.Thread(target=synthesize, daemon=True, name="piper-synthesis")
        producer.start()
        try:
            while True:
                if cancel:
                    cancel.check()
                try:
                    chunk = chunks.get(timeout=.05)
                except queue.Empty:
                    continue
                if chunk is end:
                    break
                if chunk is not None:
                    if chunk.sample_width != 2:
                        raise SpeechError(
                            f"Piper retornou sample width inesperado: {chunk.sample_width}"
                        )
                    if process is None:
                        command = [
                            "aplay",
                            "-q",
                            "--buffer-time=120000",
                            "--period-time=20000",
                            "-D",
                            self.playback_device,
                            "-t",
                            "raw",
                            "-f",
                            "S16_LE",
                            "-r",
                            str(chunk.sample_rate),
                            "-c",
                            str(chunk.sample_channels),
                        ]
                        try:
                            process = self._popen(
                                command, stdin=subprocess.PIPE, stderr=subprocess.PIPE
                            )
                        except FileNotFoundError as exc:
                            raise SpeechError(
                                "aplay não foi encontrado; instale alsa-utils"
                            ) from exc
                        if cancel:
                            remove_cancel = cancel.register(abort_playback)
                            cancel.check()
                        stream = process.stdin
                        if stream is None:
                            raise SpeechError("Não foi possível abrir a entrada do aplay")

                    assert stream is not None
                    stream.write(chunk.audio_int16_bytes)
                    stream.flush()
                    if not first_audio_sent:
                        first_audio_sent = True
                        if on_first_audio:
                            on_first_audio()

            if errors:
                raise SpeechError("Falha na síntese de voz") from errors[0]
            if process is not None:
                assert stream is not None
                stream.close()
                return_code = process.wait()
                if cancel:
                    cancel.check()
                if return_code != 0:
                    raise SpeechError(f"aplay terminou com código {return_code}")
        except ResponseCancelled:
            raise
        except SpeechError:
            if cancel:
                cancel.check()
                cancel.cancel()
            if process is not None and process.returncode is None:
                process.terminate()
            raise
        except (BrokenPipeError, OSError) as exc:
            was_cancelled = bool(cancel and cancel.event.is_set())
            if cancel:
                cancel.cancel()
            if process is not None and process.returncode is None:
                process.terminate()
            if was_cancelled and cancel:
                cancel.check()
            raise SpeechError(f"Falha ao reproduzir áudio: {exc}") from exc
        except Exception as exc:
            was_cancelled = bool(cancel and cancel.event.is_set())
            if cancel:
                cancel.cancel()
            if process is not None and process.returncode is None:
                process.terminate()
            if was_cancelled and cancel:
                cancel.check()
            raise SpeechError(f"Falha ao sintetizar voz: {exc}") from exc

        finally:
            stop.set()
            # A cancelled phrase iterator is bounded; finish synthesis before reuse.
            producer.join()
            remove_cancel()
            if process is not None and hasattr(process, "poll"):
                abort_playback()
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
                if process.stderr:
                    process.stderr.close()
