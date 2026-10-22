#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from raspberry_phone.llm import OpenRouterProvider


root = Path(__file__).resolve().parent.parent
load_dotenv(root / ".env")
api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not api_key:
    raise SystemExit("Defina OPENROUTER_API_KEY no .env")

provider = OpenRouterProvider(
    api_key=api_key,
    base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    model=os.environ.get("OPENROUTER_MODEL", "google/gemini-3.1-flash-lite"),
    max_tokens=int(os.environ.get("OPENROUTER_MAX_TOKENS", "180")),
    temperature=0.0,
    reasoning_effort=os.environ.get("OPENROUTER_REASONING_EFFORT", "none"),
    timeout_seconds=30,
    system_prompt=(
        "Responda em português brasileiro com uma frase curta. "
        "Entregue somente a resposta final, sem mostrar seu raciocínio."
    ),
)
answer = "".join(
    provider.stream([{"role": "user", "content": "Diga: API funcionando."}])
).strip()
if not answer:
    raise SystemExit("O OpenRouter retornou uma resposta vazia")
print(answer)
