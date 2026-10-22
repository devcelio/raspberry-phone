# Raspberry Phone

Telefone com IA em português para Raspberry Pi 5 ou Zero 2 W, com painel web.
O microfone e o alto-falante são os do Raspberry, mesmo ao abrir o painel no celular.

```text
Headset USB → Deepgram (voz para texto) → OpenRouter (IA) → Piper (voz local)
```

## Você precisa de

- Raspberry Pi OS baseado em Debian, **64 bits**, Python 3.11+ e 2 GB livres.
- Headset USB com microfone e saída na mesma placa ALSA. Use headset:
  o projeto ainda não tem cancelamento de eco para viva-voz.
- Internet e chaves de [OpenRouter](https://openrouter.ai/) e
  [Deepgram](https://console.deepgram.com/). O uso das APIs pode gerar cobrança.

## Instalar no Raspberry

```bash
git clone https://github.com/devcelio/raspberry-phone.git ~/raspberry-phone
cd ~/raspberry-phone
bash scripts/bootstrap_pi.sh
nano .env
```

O bootstrap instala dependências, compila Whisper, baixa os modelos, cria o
ambiente Python e preenche os dispositivos de áudio quando há exatamente uma
placa compatível. Pode demorar, especialmente no Zero 2 W. Preserva um `.env` existente.

**O que você precisa mudar no `.env`:**

| Variável | Preencha com |
|---|---|
| `OPENROUTER_API_KEY` | Sua chave do OpenRouter |
| `DEEPGRAM_API_KEY` | Sua chave da Deepgram |
| `AUDIO_CAPTURE_DEVICE` / `AUDIO_PLAYBACK_DEVICE` | Já preenchidos pelo bootstrap; confira com `bash scripts/detect_audio_device.sh` |
| `WEB_HOST` | `localhost` para acesso local; para outro aparelho, o endereço do seu Raspberry em uma rede confiável/VPN |

O modelo é escolhido em `OPENROUTER_MODEL`; selecione um disponível na sua conta.
A personalidade e o tamanho das respostas ficam em `SYSTEM_PROMPT` e
`OPENROUTER_MAX_TOKENS`. Todas as opções estão em [`.env.example`](.env.example).
Guarde as chaves apenas no `.env`, ignorado pelo Git.

## Testar e usar

```bash
bash scripts/test_audio.sh
.venv/bin/python scripts/test_openrouter.py
.venv/bin/python scripts/test_tts.py
.venv/bin/python -m raspberry_phone --web-only
```

O teste de áudio grava cinco segundos e reproduz no headset. O teste OpenRouter
faz uma chamada à API. Abra `http://localhost:8080` no Raspberry; em outro aparelho,
use o endereço definido em `WEB_HOST`, na porta `8080`.

Clique em **Iniciar conversa**, fale e faça uma pausa. O telefone responde e
continua ouvindo; comece a falar para interromper a resposta. **Parar conversa**
encerra a sessão. Fechar a página mantém a sessão no Raspberry: pare pelo botão.
Você também pode selecionar **Segurar para falar**. Para usar pelo terminal,
execute sem `--web-only` e pressione ENTER para cada pergunta.

**Iniciar no boot** (projeto instalado em `~/raspberry-phone`):

```bash
bash scripts/install_service.sh
sudo loginctl enable-linger "$USER"
```

Consulte logs com `journalctl --user -u raspberry-phone -n 50 --no-pager` e
reinicie com `systemctl --user restart raspberry-phone`.

## Se algo falhar

- **Áudio:** conecte só um headset USB e confira captura no `alsamixer`.
- **401/403:** confira chave, permissões, modelo e créditos do provedor.
- **Painel inacessível:** confira `WEB_HOST`, porta e rede. O painel não tem login;
  permita acesso somente por rede confiável/VPN.
- **Sem Deepgram:** use `STT_BACKEND=whisper` e teste `bash scripts/test_stt.sh`.
  A transcrição será local; o OpenRouter ainda precisa de internet.

[Modos avançados, deploy e API](docs/advanced.md) ·
[Guia para desenvolver com IA](AGENTS.md) ·
[Animações Manim](animations/README.md)

## Desenvolvimento

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,streaming]'
make test
```

Os testes simulam áudio e provedores, sem chaves nem hardware real. Testes da
interface também precisam de Node.js. A validação acústica deve ser feita no Pi.
