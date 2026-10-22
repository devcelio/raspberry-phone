from __future__ import annotations

import argparse
import os
import threading
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TextIO

from .agent import VoiceAgentAssistant
from .assistant import AssistantError, PhoneAssistant
from .audio import AudioRecorder
from .config import AppConfig, ConfigurationError
from .controller import TurnBusyError, TurnController
from .conversation import ConversationHistory, ConversationStore
from .live_stt import DeepgramSpeechInput
from .llm import OpenRouterProvider
from .state import StateStore
from .stt import WhisperTranscriber, WhisperServerTranscriber
from .tts import PiperSpeechPlayer
from .web import PhoneWebServer


class InteractiveAssistant(Protocol):
    state: Any

    def run_turn(self) -> Any: ...


def build_assistant(config: AppConfig) -> PhoneAssistant | VoiceAgentAssistant:
    conversation = ConversationStore(config.runtime_dir / "conversation.json")
    history = ConversationHistory(max_turns=config.max_turns)
    from .response import INTERRUPTED_CONTEXT
    for turn in conversation.turns():
        if turn["status"] == "complete":
            history.add_turn(turn["transcript"], turn["answer"])
        elif turn["status"] == "interrupted" and turn["transcript"]:
            history.add_turn(turn["transcript"], INTERRUPTED_CONTEXT)
    state = StateStore(
        config.runtime_dir / "state.json",
        turns_provider=conversation.turns,
        live_interval=.1,
    )
    state.publish("starting")
    if config.conversation_backend == "deepgram-agent":
        return VoiceAgentAssistant(config, history, conversation, state)
    speaker = PiperSpeechPlayer(config.piper_voice, config.audio_playback_device)
    speaker.warmup()
    return PhoneAssistant(
        speech_input=(DeepgramSpeechInput(
            api_key=config.deepgram_api_key, device=config.audio_capture_device,
            max_seconds=config.speech_max_seconds, endpoint_ms=config.speech_endpoint_ms,
        ) if config.stt_backend == "deepgram" else None),
        recorder=AudioRecorder(
            config.audio_capture_device, config.record_seconds
        ),
        transcriber=(WhisperServerTranscriber(config.whisper_server_url) if config.whisper_server_url
                     else WhisperTranscriber(config.whisper_cli, config.whisper_model)),
        llm=OpenRouterProvider(
            api_key=config.openrouter_api_key,
            base_url=config.openrouter_base_url,
            model=config.openrouter_model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            reasoning_effort=config.openrouter_reasoning_effort,
            timeout_seconds=config.request_timeout_seconds,
            system_prompt=config.system_prompt,
        ),
        speaker=speaker,
        history=history,
        conversation=conversation,
        state=state,
        runtime_dir=config.runtime_dir,
        phrase_max_chars=config.phrase_max_chars,
    )


def run_interactive(
    assistant: InteractiveAssistant,
    *,
    controller: TurnController | None = None,
    web_server: PhoneWebServer | None = None,
    input_fn: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
) -> int:
    runner = controller or assistant
    assistant.state.publish("ready")
    if web_server is not None:
        web_server.start()
    print("Telefone com IA pronto.", file=output)
    print("ENTER inicia uma pergunta. No dashboard, use Iniciar conversa para escuta contínua no fluxo Deepgram STT + Piper.", file=output)
    if web_server is not None:
        print(f"Conversa ao vivo: {web_server.url}", file=output)

    try:
        while True:
            try:
                command = input_fn("\nENTER para falar | q para sair: ").strip().lower()
            except (EOFError, StopIteration):
                break
            if command == "q":
                break
            if command:
                print("Digite apenas ENTER para falar ou q para sair.", file=output)
                continue

            try:
                result = runner.run_turn()
            except TurnBusyError:
                print("Já existe um turno em andamento.", file=output)
                continue
            except AssistantError as exc:
                print(f"Erro: {exc}", file=output)
                continue
            if result is None:
                print("Não consegui entender a gravação. Tente novamente.", file=output)
                continue

            print(f"Você: {result.transcript}", file=output)
            print(f"Telefone: {result.answer}", file=output)
            timing_text = " | ".join(
                f"{name}={value:.2f}s"
                for name, value in result.timings_seconds.items()
            )
            print(f"Tempos: {timing_text}", file=output)
    except KeyboardInterrupt:
        print("\nInterrompido.", file=output)
    finally:
        if controller is not None:
            controller.shutdown()
        assistant.state.publish("stopped")
        if web_server is not None:
            web_server.stop()

    return 0


def run_web(assistant: InteractiveAssistant, controller: TurnController,
            web_server: PhoneWebServer) -> int:
    assistant.state.publish("ready")
    web_server.start()
    print(f"Conversa ao vivo: {web_server.url}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown()
        assistant.state.publish("stopped")
        web_server.stop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Telefone com IA")
    parser.add_argument("--web-only", action="store_true", help="Controlar pelo dashboard sem manter um terminal aberto")
    args = parser.parse_args()
    try:
        try:
            from dotenv import load_dotenv
        except ImportError as exc:
            raise ConfigurationError(
                "Dependência python-dotenv ausente; execute scripts/bootstrap_pi.sh"
            ) from exc

        load_dotenv()
        config = AppConfig.from_mapping(os.environ, root=Path.cwd())
        assistant = build_assistant(config)
        controller = TurnController(
            assistant,
            history=assistant.history,
            conversation=assistant.conversation,
            state=assistant.state,
        )
        web_server = PhoneWebServer(
            config.web_host,
            config.web_port,
            state=assistant.state,
            controller=controller,
            record_seconds=config.record_seconds,
            streaming=config.stt_backend == "deepgram" or config.conversation_backend == "deepgram-agent",
        )
        if args.web_only:
            return run_web(assistant, controller, web_server)
        return run_interactive(
            assistant,
            controller=controller,
            web_server=web_server,
        )
    except (ConfigurationError, AssistantError, RuntimeError) as exc:
        print(f"Falha ao iniciar: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
