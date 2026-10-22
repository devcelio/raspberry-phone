from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_SYSTEM_PROMPT = (
    "Você é a voz de um telefone com inteligência artificial. "
    "Responda em português brasileiro. Comece com uma frase de até 8 palavras. Use no máximo três frases curtas. "
    "Entregue somente a resposta final, sem explicar ou mostrar seu raciocínio. "
    "Use texto simples, sem Markdown, listas, emojis ou URLs."
)

REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


class ConfigurationError(ValueError):
    pass


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Variável obrigatória ausente: {name}")
    return value


def _integer(environment: Mapping[str, str], name: str, default: int) -> int:
    raw = environment.get(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} deve ser um número inteiro") from exc


def _floating(environment: Mapping[str, str], name: str, default: float) -> float:
    raw = environment.get(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} deve ser um número") from exc


@dataclass(frozen=True, slots=True)
class AppConfig:
    openrouter_api_key: str
    audio_capture_device: str
    audio_playback_device: str
    root: Path
    whisper_cli: Path
    whisper_model: Path
    piper_voice: Path
    runtime_dir: Path
    openrouter_base_url: str
    openrouter_model: str
    openrouter_reasoning_effort: str
    max_tokens: int
    temperature: float
    request_timeout_seconds: float
    record_seconds: int
    max_turns: int
    phrase_max_chars: int
    system_prompt: str
    web_host: str
    web_port: int
    conversation_backend: str = "local"
    agent_session_seconds: int = 20
    agent_voice_model: str = "sonic-2"
    agent_voice_id: str = "a167e0f3-df7e-4d52-a9c3-f949145efdab"
    whisper_server_url: str = ""
    stt_backend: str = "whisper"
    deepgram_api_key: str = ""
    speech_max_seconds: int = 30
    speech_endpoint_ms: int = 600

    @classmethod
    def from_mapping(
        cls, environment: Mapping[str, str], *, root: Path | None = None
    ) -> "AppConfig":
        project_root = Path(
            environment.get("RASPBERRY_PHONE_ROOT", str(root or Path.cwd()))
        ).expanduser().resolve()

        def project_path(name: str, default: str) -> Path:
            return Path(environment.get(name, str(project_root / default))).expanduser()

        config = cls(
            openrouter_api_key=_required(environment, "OPENROUTER_API_KEY"),
            audio_capture_device=_required(environment, "AUDIO_CAPTURE_DEVICE"),
            audio_playback_device=_required(environment, "AUDIO_PLAYBACK_DEVICE"),
            root=project_root,
            whisper_cli=project_path(
                "WHISPER_CLI", ".deps/whisper.cpp/build/bin/whisper-cli"
            ),
            whisper_model=project_path("WHISPER_MODEL", "models/ggml-tiny.bin"),
            piper_voice=project_path(
                "PIPER_VOICE", "models/pt_BR-faber-medium.onnx"
            ),
            runtime_dir=project_path("RUNTIME_DIR", "runtime"),
            openrouter_base_url=environment.get(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ).rstrip("/"),
            openrouter_model=environment.get(
                "OPENROUTER_MODEL", "google/gemini-3.1-flash-lite"
            ),
            openrouter_reasoning_effort=environment.get(
                "OPENROUTER_REASONING_EFFORT", "none"
            ).strip().lower(),
            max_tokens=_integer(environment, "OPENROUTER_MAX_TOKENS", 100),
            temperature=_floating(environment, "OPENROUTER_TEMPERATURE", 0.3),
            request_timeout_seconds=_floating(
                environment, "OPENROUTER_TIMEOUT_SECONDS", 30.0
            ),
            record_seconds=_integer(environment, "RECORD_SECONDS", 10),
            max_turns=_integer(environment, "MAX_HISTORY_TURNS", 4),
            phrase_max_chars=_integer(environment, "PHRASE_MAX_CHARS", 180),
            system_prompt=environment.get("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            web_host=environment.get("WEB_HOST", "127.0.0.1").strip(),
            web_port=_integer(environment, "WEB_PORT", 8080),
            conversation_backend=environment.get("CONVERSATION_BACKEND", "local").strip(),
            agent_session_seconds=_integer(environment, "AGENT_SESSION_SECONDS", 20),
            agent_voice_model=environment.get("AGENT_VOICE_MODEL", "sonic-2").strip(),
            agent_voice_id=environment.get("AGENT_VOICE_ID", "a167e0f3-df7e-4d52-a9c3-f949145efdab").strip(),
            whisper_server_url=environment.get("WHISPER_SERVER_URL", "").strip(),
            stt_backend=environment.get("STT_BACKEND", "whisper").strip().lower(),
            deepgram_api_key=environment.get("DEEPGRAM_API_KEY", "").strip(),
            speech_max_seconds=_integer(environment, "SPEECH_MAX_SECONDS", 30),
            speech_endpoint_ms=_integer(environment, "SPEECH_ENDPOINT_MS", 600),
        )
        config._validate_ranges()
        return config

    def _validate_ranges(self) -> None:
        if self.conversation_backend not in {"local", "deepgram-agent"}:
            raise ConfigurationError("CONVERSATION_BACKEND deve ser local ou deepgram-agent")
        if not 15 <= self.agent_session_seconds <= 300:
            raise ConfigurationError("AGENT_SESSION_SECONDS deve ficar entre 15 e 300")
        if self.conversation_backend == "deepgram-agent" and not self.deepgram_api_key:
            raise ConfigurationError("DEEPGRAM_API_KEY é obrigatória no modo deepgram-agent")
        if self.stt_backend not in {"whisper", "deepgram"}:
            raise ConfigurationError("STT_BACKEND deve ser whisper ou deepgram")
        if self.stt_backend == "deepgram" and not self.deepgram_api_key:
            raise ConfigurationError("DEEPGRAM_API_KEY é obrigatória no modo deepgram")
        if not 1 <= self.speech_max_seconds <= 120:
            raise ConfigurationError("SPEECH_MAX_SECONDS deve ficar entre 1 e 120")
        if not 200 <= self.speech_endpoint_ms <= 2000:
            raise ConfigurationError("SPEECH_ENDPOINT_MS deve ficar entre 200 e 2000")
        if self.record_seconds < 1:
            raise ConfigurationError("RECORD_SECONDS deve ser maior que zero")
        if self.max_tokens < 1:
            raise ConfigurationError("OPENROUTER_MAX_TOKENS deve ser maior que zero")
        if self.openrouter_reasoning_effort not in REASONING_EFFORTS:
            allowed = ", ".join(sorted(REASONING_EFFORTS))
            raise ConfigurationError(
                f"OPENROUTER_REASONING_EFFORT deve ser um de: {allowed}"
            )
        if not 0 <= self.temperature <= 2:
            raise ConfigurationError("OPENROUTER_TEMPERATURE deve ficar entre 0 e 2")
        if self.max_turns < 1:
            raise ConfigurationError("MAX_HISTORY_TURNS deve ser maior que zero")
        if self.phrase_max_chars < 8:
            raise ConfigurationError("PHRASE_MAX_CHARS deve ser no mínimo 8")
        if not self.web_host:
            raise ConfigurationError("WEB_HOST não pode ficar vazio")
        if not 1 <= self.web_port <= 65535:
            raise ConfigurationError("WEB_PORT deve ficar entre 1 e 65535")
