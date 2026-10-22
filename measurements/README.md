# Coleta acústica real no headset

A tabela final ainda depende desta coleta. Não substituir por chegada de PCM.
Use uma gravação externa contínua (celular ou microfone de referência), ouvindo
sua fala e o alto-falante do headset no mesmo arquivo. Evite realimentação no
microfone do telefone. Para cada modo, faça as mesmas dez perguntas do benchmark.
Use uma conversa nova para cada modo. Anote o final da última palavra da pergunta
e o início audível da voz do telefone, na mesma gravação, com precisão de 10 ms.
Inclua falhas e perguntas cortadas, não apenas turnos rápidos.

Preencha `acoustic.csv`: uma linha por pergunta/modo (30 linhas ao todo).
As colunas contêm segundos desde o início da gravação. `latency` é a diferença
entre os dois tempos; p50 é a mediana e p95 usa nearest rank.

Modo `local`: Whisper + OpenRouter + Piper (transcrição local, ainda depende da
internet para gerar respostas; não é conversa inteiramente offline).
Modo `deepgram`: Nova-3 + OpenRouter + Piper.
Modo `agent`: sessão experimental Deepgram com LLM externo.

Custo por hora de conversa depende da proporção de áudio transmitido e dos tokens.
Referência consultada em deepgram.com/pricing: Nova-3 monolíngue US$ 0,0048/min
(promocional) e Agent BYO LLM US$ 0,059/min. Para uma hora inteira faturada:
local = US$ 0 de STT/TTS + OpenRouter; deepgram = US$ 0,288 + OpenRouter;
agent = US$ 3,54 + OpenRouter. Eletricidade e hardware não incluídos.
O custo OpenRouter deve vir do campo usage.cost dos testes ou da atividade real.
