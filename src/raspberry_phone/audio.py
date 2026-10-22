from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any


class AudioError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(
        self,
        device: str,
        duration_seconds: int,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.device = device
        self.duration_seconds = duration_seconds
        self._runner = runner

    def record(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        command = [
            "arecord",
            "-q",
            "-D",
            self.device,
            "-f",
            "S16_LE",
            "-r",
            "16000",
            "-c",
            "1",
            "-d",
            str(self.duration_seconds),
            str(destination),
        ]
        options: dict[str, Any] = {
            "check": True,
            "capture_output": True,
            "text": True,
        }
        try:
            self._runner(command, **options)
        except FileNotFoundError as exc:
            raise AudioError("arecord não foi encontrado; instale alsa-utils") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise AudioError(f"Falha ao gravar no dispositivo {self.device}: {detail}") from exc
