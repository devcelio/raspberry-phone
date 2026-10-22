import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from raspberry_phone.tts import PiperSpeechPlayer, SpeechError


class FakeVoice:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> list[object]:
        self.spoken.append(text)
        return [
            SimpleNamespace(
                sample_rate=22050,
                sample_width=2,
                sample_channels=1,
                audio_int16_bytes=text.encode(),
            )
        ]


class FakeProcess:
    def __init__(self, returncode: int = 0) -> None:
        class InspectableBytesIO(io.BytesIO):
            def close(self) -> None:
                self.flush()

        self.stdin = InspectableBytesIO()
        self.returncode = returncode

    def wait(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15


def test_piper_player_loads_once_and_streams_phrases_to_one_aplay(
    tmp_path: Path,
) -> None:
    voice = FakeVoice()
    process = FakeProcess()
    commands: list[list[str]] = []
    first_audio: list[str] = []

    def popen(command: list[str], **_: object) -> FakeProcess:
        commands.append(command)
        return process

    player = PiperSpeechPlayer(
        tmp_path / "voice.onnx",
        "plughw:CARD=Phone,DEV=0",
        voice_loader=lambda _: voice,
        popen=popen,
    )
    player.speak(["Primeira.", "Segunda."], on_first_audio=lambda: first_audio.append("ok"))

    assert voice.spoken == ["Primeira.", "Segunda."]
    assert process.stdin.getvalue() == b"Primeira.Segunda."
    assert first_audio == ["ok"]
    assert commands == [
        [
            "aplay",
            "-q",
            "--buffer-time=120000",
            "--period-time=20000",
            "-D",
            "plughw:CARD=Phone,DEV=0",
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-r",
            "22050",
            "-c",
            "1",
        ]
    ]


def test_piper_player_reports_aplay_failure(tmp_path: Path) -> None:
    voice = FakeVoice()
    process = FakeProcess(returncode=1)
    player = PiperSpeechPlayer(
        tmp_path / "voice.onnx",
        "device",
        voice_loader=lambda _: voice,
        popen=lambda *_args, **_kwargs: process,
    )

    with pytest.raises(SpeechError, match="aplay terminou com código 1"):
        player.speak(["Teste."])


def test_piper_player_reports_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "piper", None)

    with pytest.raises(SpeechError, match="piper-tts ausente"):
        PiperSpeechPlayer(tmp_path / "voice.onnx", "device")


def test_piper_player_never_synthesizes_phrases_concurrently(tmp_path: Path) -> None:
    process = FakeProcess()

    class TrackingVoice:
        active = 0
        maximum_active = 0

        def synthesize(self, text: str):
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            yield SimpleNamespace(
                sample_rate=22050,
                sample_width=2,
                sample_channels=1,
                audio_int16_bytes=text.encode(),
            )
            self.active -= 1

    voice = TrackingVoice()
    player = PiperSpeechPlayer(
        tmp_path / "voice.onnx",
        "device",
        voice_loader=lambda _: voice,
        popen=lambda *_args, **_kwargs: process,
    )

    player.speak(["Uma.", "Duas.", "Três."])

    assert voice.maximum_active == 1


def test_cancellation_terminates_and_reaps_playback(tmp_path):
    import subprocess
    import threading
    from raspberry_phone.cancellation import Cancellation, ResponseCancelled
    processes, results = [], []
    ready = threading.Event()
    cancel = Cancellation()
    def spawn(*args, **kwargs):
        process = subprocess.Popen([sys.executable, '-c', 'import sys,time; sys.stdin.buffer.read(); time.sleep(30)'], **kwargs)
        processes.append(process)
        return process
    player = PiperSpeechPlayer(tmp_path / 'voice.onnx', 'fake', voice_loader=lambda _: FakeVoice(), popen=spawn)
    def play():
        try:
            player.speak(['Uma frase.'], on_first_audio=ready.set, cancel=cancel)
        except ResponseCancelled:
            results.append('interrupted')
    thread = threading.Thread(target=play)
    thread.start()
    assert ready.wait(2)
    cancel.cancel()
    thread.join(2)
    assert not thread.is_alive()
    assert results == ['interrupted']
    assert processes[0].poll() is not None
