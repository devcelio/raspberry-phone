#!/usr/bin/env python3
"""Validate the paid hybrid API without touching the saved conversation."""
import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from raspberry_phone.agent import VoiceAgentAssistant
from raspberry_phone.config import AppConfig
from raspberry_phone.conversation import ConversationHistory, ConversationStore
from raspberry_phone.state import StateStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", help="Raw 16 kHz mono PCM S16_LE file; streams at real-time speed")
    parser.add_argument("--play", action="store_true", help="Play the response on the headset")
    parser.add_argument("--model", help="Override OpenRouter model for this test")
    args = parser.parse_args()
    env = dict(dotenv_values(".env"))
    env["CONVERSATION_BACKEND"] = "deepgram-agent"
    if args.model:
        env["OPENROUTER_MODEL"] = args.model
    config = AppConfig.from_mapping(env)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = ConversationStore(root / "conversation.json")
        agent = VoiceAgentAssistant(config, ConversationHistory(), store,
                                   StateStore(root / "state.json", turns_provider=store.turns))
        result = asyncio.run(agent.run_session(
            test_text=None if args.audio else "Olá! Explique em uma frase por que chove.",
            audio_file=args.audio, play_audio=args.play,
        ))
        print(json.dumps({"model":config.openrouter_model, "transcript":result.transcript,
                          "answer":result.answer,"timings_seconds":result.timings_seconds},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
