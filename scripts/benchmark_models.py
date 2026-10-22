#!/usr/bin/env python3
"""Small Portuguese voice-response benchmark. Uses paid OpenRouter tokens."""
import argparse
import json
import re
import statistics
import time
from pathlib import Path

from dotenv import dotenv_values
from openai import OpenAI

PROMPTS = [
    "Oi! Me explica em poucas palavras por que chove.",
    "Tenho arroz, ovo e tomate. O que posso fazer de jantar?",
    "Você disse para eu reiniciar o roteador. Isso apaga minha senha do Wi-Fi?",
    "Quanto é quinze por oito?",
    "Como faço café sem ficar amargo?",
    "Me dê uma ideia de passeio barato num dia de chuva.",
    "O que significa ter uma conexão de internet instável?",
    "Como organizar três tarefas urgentes?",
    "Me conte uma curiosidade sobre a Lua.",
    "Pode repetir sua dica de jantar em uma frase?",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runtime/model-benchmark.json")
    parser.add_argument("--models", nargs="+", default=[
        "deepseek/deepseek-v4.1-flash", "qwen/qwen3.8-27b",
        "qwen/qwen3.8-flash", "google/gemini-3.1-flash-lite", "openai/gpt-oss-120b",
    ])
    args = parser.parse_args()
    env = dotenv_values(".env")
    client = OpenAI(api_key=env["OPENROUTER_API_KEY"],
                    base_url="https://openrouter.ai/api/v1", timeout=25, max_retries=0)
    rows = []
    # Interleave models to reduce bias from temporary load changes.
    for prompt in PROMPTS:
        for model in args.models:
            start = time.monotonic()
            text, first, sentence = "", None, None
            row = {"model": model, "prompt": prompt}
            try:
                with client.chat.completions.create(
                    model=model, stream=True, stream_options={"include_usage":True}, max_tokens=100, temperature=.3,
                    messages=[{"role":"system", "content":"Responda em português brasileiro, em até duas frases curtas. Use texto simples, sem listas. Responda diretamente, sem mostrar raciocínio."},
                              {"role":"user", "content":prompt}],
                    extra_body={"reasoning":{"effort":"minimal" if "gemini-3.1-flash-lite" in model else "low" if "gpt-oss" in model else "none"},
                                "provider":{"sort":"latency"}},
                ) as stream:
                    for chunk in stream:
                        if chunk.usage:
                            row["usage"] = chunk.usage.model_dump()
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta.content
                        if delta:
                            now = time.monotonic() - start
                            first = first if first is not None else now
                            text += delta
                            if sentence is None and re.search(r"[.!?]", text):
                                sentence = now
                if not text:
                    raise ValueError("Resposta sem texto")
                row.update(first_text_seconds=first, first_sentence_seconds=sentence,
                           total_seconds=time.monotonic()-start, answer=text)
                print(model, "first=", round(first, 3), "sentence=", round(sentence or 0, 3), flush=True)
            except Exception as exc:
                # Provider exceptions may contain headers. Store only the type.
                row["error"] = type(exc).__name__
                print(model, row["error"], flush=True)
            rows.append(row)
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    for model in args.models:
        good = [r for r in rows if r["model"] == model and "error" not in r]
        if good:
            print(model, "success",len(good),"median_first",round(statistics.median(r["first_text_seconds"] for r in good),3),flush=True)


if __name__ == "__main__":
    main()
