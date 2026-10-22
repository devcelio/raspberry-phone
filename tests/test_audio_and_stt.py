import subprocess
from pathlib import Path

import pytest

from raspberry_phone.audio import AudioError, AudioRecorder
from raspberry_phone.stt import TranscriptionError, WhisperTranscriber


def test_recorder_invokes_arecord_with_phone_format(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    destination = tmp_path / "runtime/input.wav"
    AudioRecorder("plughw:CARD=Phone,DEV=0", 7, runner=runner).record(destination)

    assert calls == [
        [
            "arecord",
            "-q",
            "-D",
            "plughw:CARD=Phone,DEV=0",
            "-f",
            "S16_LE",
            "-r",
            "16000",
            "-c",
            "1",
            "-d",
            "7",
            str(destination),
        ]
    ]
    assert destination.parent.is_dir()


def test_recorder_reports_missing_arecord(tmp_path: Path) -> None:
    def missing(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    with pytest.raises(AudioError, match="arecord não foi encontrado"):
        AudioRecorder("device", 7, runner=missing).record(tmp_path / "input.wav")


def test_recorder_reports_unavailable_audio_device(tmp_path: Path) -> None:
    def failing(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            1, command, stderr="audio open error: No such device"
        )

    with pytest.raises(AudioError, match="No such device"):
        AudioRecorder("missing", 7, runner=failing).record(tmp_path / "input.wav")


def test_whisper_transcriber_returns_clean_text(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "  Olá, telefone.  \n", "")

    cli = tmp_path / "whisper-cli"
    model = tmp_path / "ggml-tiny.bin"
    audio = tmp_path / "input.wav"
    result = WhisperTranscriber(cli, model, runner=runner).transcribe(audio)

    assert result == "Olá, telefone."
    assert calls == [
        [
            str(cli),
            "-m",
            str(model),
            "-f",
            str(audio),
            "-l",
            "pt",
            "-nt",
            "-np",
        ]
    ]


def test_whisper_transcriber_includes_stderr_on_failure(tmp_path: Path) -> None:
    def failing(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(2, command, stderr="modelo inválido")

    transcriber = WhisperTranscriber(
        tmp_path / "whisper-cli", tmp_path / "model.bin", runner=failing
    )

    with pytest.raises(TranscriptionError, match="modelo inválido"):
        transcriber.transcribe(tmp_path / "input.wav")
