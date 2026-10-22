#!/usr/bin/env python3
"""Save voice-response settings in OpenRouter so Deepgram can reference them."""
import argparse
import re

import httpx
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="New preset name; an existing name creates a new version")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]+", args.slug):
        parser.error("Use letras minúsculas, números e hífens")
    values = dotenv_values(".env")
    response = httpx.post(
        "https://openrouter.ai/api/v1/presets/" + args.slug + "/chat/completions",
        headers={"Authorization": "Bearer " + values["OPENROUTER_API_KEY"]},
        json={"provider": {"sort": "latency"}, "reasoning": {"effort": "none"},
              "max_tokens": 180, "temperature": .3}, timeout=20,
    )
    if not response.is_success:
        raise SystemExit(f"Não foi possível salvar o preset (HTTP {response.status_code}).")
    print("Preset salvo: @preset/" + args.slug)


if __name__ == "__main__":
    main()
