# Benchmark único de LLMs — 21/10/2026

Dez prompts pt-BR por modelo, no Pi, stream de conteúdo, provider.sort=latency. p95 por nearest rank (com n=10 equivale ao máximo). Não inclui STT/TTS.

| Modelo | n | p50 conteúdo | p95 conteúdo | Tokens de raciocínio |
|---|---:|---:|---:|---:|
| deepseek/deepseek-v4.1-flash | 10 | 0.620 s | 5.027 s | 0 (10/10 reportados) |
| qwen/qwen3.8-27b | 10 | 0.413 s | 1.361 s | 0 (10/10 reportados) |
| qwen/qwen3.8-flash | 10 | 1.127 s | 5.482 s | 0 (10/10 reportados) |
| google/gemini-3.1-flash-lite | 10 | 0.838 s | 1.259 s | 0 (10/10 reportados) |
| openai/gpt-oss-120b | 10 | 0.516 s | 1.701 s | 203 (10/10 reportados) |

Gemini: minimal, pois none não consta como suportado. GPT-OSS: low. Demais: none. Não houve teste separado de none no Gemini; os resultados antigos com none não comprovam que o provedor desativou raciocínio.

Modelo padrão preservado: Qwen provisório da etapa anterior. Nenhuma troca após este benchmark.

Piper: a comparação salva ocorreu junto à compilação do Whisper e chamadas LLM. Há contenção de CPU/memória; serve como diagnóstico preliminar, não como comparação conclusiva. Faber permanece selecionado.
