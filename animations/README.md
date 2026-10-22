# Animações Manim do telefone com IA

O pacote contém oito cenas independentes em formato vertical 9:16. A estética
segue o vídeo do MNIST: fundo preto, geometria branca, azul para informação e
ativação, vermelho apenas para espera/erro e tipografia monoespaçada.

## Cenas e posição sugerida

| Cena | Trecho do roteiro |
|---|---|
| `PipelineOverview` | “voz → texto → IA → voz” |
| `SpeechToText` | gravação e transcrição da pergunta |
| `OpenRouterHub` | explicação do OpenRouter e escolha do MiniMax |
| `StreamingComparison` | resposta inteira versus resposta em pedaços |
| `SentenceAudioQueue` | uma frase já começa a tocar enquanto a próxima chega |
| `TextToSpeech` | transformação da resposta em áudio |
| `LocalVsCloud` | processos locais no Raspberry e IA na nuvem |
| `FullSystemLoop` | demonstração completa e estados da interface |

## Instalação

No macOS com Homebrew:

```bash
brew install cairo pango pkg-config ffmpeg
python3 -m venv .venv-manim
.venv-manim/bin/python -m pip install -r animations/requirements.txt
```

## Renderização

Prévia leve de uma cena:

```bash
MANIM_PIXEL_WIDTH=270 MANIM_PIXEL_HEIGHT=480 \
  .venv-manim/bin/manim -ql animations/phone_scenes.py SpeechToText
```

Render final de todas as cenas:

```bash
./animations/render_all.sh
```

Para usar outro executável do Manim:

```bash
MANIM_BIN=/caminho/para/manim ./animations/render_all.sh -ql
```

Os MP4s são gerados dentro de `media/videos/phone_scenes/`.
