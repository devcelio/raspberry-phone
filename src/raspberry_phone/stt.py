from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any


class TranscriptionError(RuntimeError):
    pass


class WhisperTranscriber:
    def __init__(
        self,
        cli_path: Path,
        model_path: Path,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.cli_path = cli_path
        self.model_path = model_path
        self._runner = runner

    def transcribe(self, audio_path: Path) -> str:
        command = [
            str(self.cli_path),
            "-m",
            str(self.model_path),
            "-f",
            str(audio_path),
            "-l",
            "pt",
            "-nt",
            "-np",
        ]
        options: dict[str, Any] = {
            "check": True,
            "capture_output": True,
            "text": True,
        }
        try:
            completed = self._runner(command, **options)
        except FileNotFoundError as exc:
            raise TranscriptionError(
                f"whisper-cli não encontrado em {self.cli_path}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise TranscriptionError(f"Falha na transcrição: {detail}") from exc

        return " ".join(line.strip() for line in completed.stdout.splitlines()).strip()


class WhisperServerTranscriber:
    """Use a resident localhost whisper-server; never upload offline audio."""
    def __init__(self, url: str = "http://127.0.0.1:8081/inference") -> None:
        self.url = url

    def transcribe(self, audio_path: Path) -> str:
        import httpx
        try:
            with audio_path.open("rb") as audio:
                response = httpx.post(self.url, files={"file": ("input.wav", audio, "audio/wav")},
                                      data={"response_format":"json", "language":"pt"}, timeout=120)
            response.raise_for_status()
            return str(response.json().get("text", "")).strip()
        except Exception as exc:
            raise TranscriptionError("Whisper residente indisponível; execute scripts/start_whisper_server.sh") from exc
