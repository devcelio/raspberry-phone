#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from raspberry_phone.tts import PiperSpeechPlayer


root = Path(__file__).resolve().parent.parent
load_dotenv(root / ".env")
device = os.environ.get("AUDIO_PLAYBACK_DEVICE", "").strip()
if not device:
    raise SystemExit("Defina AUDIO_PLAYBACK_DEVICE no .env")
voice = Path(
    os.environ.get("PIPER_VOICE", root / "models/pt_BR-faber-medium.onnx")
)
PiperSpeechPlayer(voice, device).speak(
    ["Olá. A voz do telefone está funcionando."]
)
print("Teste de voz concluído.")
