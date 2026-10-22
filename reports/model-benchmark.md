# Comparação inicial — 21/10/2026

Origem: Raspberry Pi Zero 2 W, OpenRouter em streaming, três perguntas curtas
em português por modelo, intercaladas. Roteamento por latência, raciocínio `none`,
160 tokens de saída no máximo. Respostas e tempos brutos em `model-benchmark.json`.

| Modelo | Mediana até primeiro texto | Maior tempo observado |
| --- | ---: | ---: |
| Qwen 3.8 27B | 0,380 s | 0,994 s |
| DeepSeek V4.1 Flash | 0,724 s | 4,288 s |
| Gemini 3.1 Flash Lite | 0,820 s | 0,889 s |
| Qwen 3.8 Flash | 1,032 s | 1,581 s |

Escolha provisória: Qwen 3.8 27B. Todos retornaram texto utilizável em português.
A amostra não estabelece superioridade geral, confiabilidade ou percentis de
produção. Não inclui STT ou TTS; conexões frias e carga dos provedores afetam os
resultados. Não registramos o provedor efetivo, então esta medição compara o
roteamento disponível naquele momento, não somente os pesos de cada modelo.

Um teste adicional do híbrido com áudio sintético em português retornou transcrição,
resposta e áudio: 0,700 s entre transcrição final e primeiro áudio recebido. A sessão
levou 2,266 s para conectar/configurar. Não é uma medição do fim da fala ao som audível.
O teste identificou imperfeitamente o início da pergunta ("Tenho" virou "o");
o headset real ainda precisa ser avaliado pelo usuário.
