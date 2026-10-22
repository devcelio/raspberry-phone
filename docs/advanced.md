# Configurações avançadas

## Transcrição local com Whisper

No `.env`, defina `STT_BACKEND=whisper`. A captura usa `RECORD_SECONDS` e
cada pergunta é iniciada pelo botão ou ENTER. O LLM continua usando OpenRouter.
Para manter Whisper carregado, execute `bash scripts/start_whisper_server.sh`
em outro terminal e defina `WHISPER_SERVER_URL=http://localhost:8081/inference`.
Sem essa variável, usa-se `whisper-cli` a cada pergunta.

## Deepgram Voice Agent (experimental)

Instale `.venv/bin/python -m pip install '.[agent]'` e configure:

```dotenv
CONVERSATION_BACKEND=deepgram-agent
DEEPGRAM_API_KEY=sua-chave
OPENROUTER_API_KEY=sua-chave
```

Nesse modo, Deepgram gerencia a transcrição e a voz Cartesia, e chama o modelo
OpenRouter. Cada acionamento abre uma sessão limitada por `AGENT_SESSION_SECONDS`;
o fluxo é half-duplex, sem interrupção da resposta. As duas contas têm cobrança.
`AGENT_VOICE_MODEL` e `AGENT_VOICE_ID` selecionam a voz de catálogo.

`scripts/test_voice_agent.py` faz uma chamada paga sem alterar o histórico.
`scripts/configure_openrouter_preset.py NOME` salva um preset na conta OpenRouter;
um nome existente cria outra versão. Use `OPENROUTER_MODEL=modelo@preset/NOME`.
O preset controla raciocínio, roteamento e tokens nesse modo; o parâmetro local
`OPENROUTER_REASONING_EFFORT` só controla chamadas diretas do projeto.

## Deploy por SSH (opcional)

Com autenticação por chave já configurada, execute no computador de origem:

```bash
PI_HOST=usuario@raspberrypi.local PI_DIR=/home/usuario/raspberry-phone bash scripts/deploy.sh
```

Substitua usuário, host e pasta. O script exige esses dois valores explicitamente,
copia o projeto por rsync e preserva `.env`, modelos e histórico existentes no Pi.
Instale `rsync` nas duas máquinas. Depois execute o bootstrap no Raspberry.

## Operação e diagnóstico

- `bash scripts/diagnose_pi.sh`: verifica sistema, hardware, disco e áudio.
- `bash scripts/headless_pi.sh --plan`: mostra mudanças para operar sem desktop.
- `bash scripts/performance_pi.sh --plan`: mostra ajustes de Wi-Fi e CPU.
- Os dois últimos só alteram o sistema com `sudo bash SCRIPT --apply` e salvam
  um script de reversão em `/var/backups/`.
- `reports/` guarda benchmarks históricos; `measurements/` contém o protocolo
  de medição acústica. Chegada de áudio à aplicação não comprova latência audível.

## Dados e rede

O histórico fica em `runtime/conversation.json`, e o estado em `runtime/state.json`.
No fluxo Deepgram, áudio é enviado à Deepgram; transcrição e contexto vão ao
OpenRouter. No Whisper, transcrição e síntese são locais, mas o LLM usa internet.
Use a opção de limpar conversa na interface para apagar o histórico.

O servidor controla microfone e reprodução e não possui autenticação própria.
Mantenha `WEB_HOST=localhost` para acesso na própria máquina ou configure um
endereço de uma rede confiável/VPN para abrir o painel em outro aparelho.

## Controle de sessão pela API

Os comandos usam `POST` com `Content-Type: application/json` e retornam o estado
atual (202) ou conflito (409). Payloads inválidos retornam 400.

- `/api/session/mode`: `{"mode":"continuous"}` ou `{"mode":"push-to-talk"}`, somente parado.
- `/api/session/start`: `{}`, inicia conversa contínua.
- `/api/session/stop`: `{}`, encerra conversa contínua; para uma sessão manual, inclua `capture_id`.
- `/api/ptt/press`: `{"capture_id":"identificador-unico"}`, inicia a captura manual.
- `/api/ptt/release`: mesmo identificador, finaliza a transcrição e responde.
- `/api/ptt/cancel`: mesmo identificador, descarta captura e cancela resposta.

O cliente deve enviar release/cancel mesmo se a soltura ocorrer antes da resposta
a press; comandos com identificador antigo são rejeitados. `/api/turn` e o ENTER
do terminal continuam iniciando uma pergunta única quando nenhuma sessão está ativa.
O SSE publica `session_supported`, `mode`, `session_active`, `capture_id`,
`listening`, `input_transcript` e `response_status`, além dos campos anteriores.
Respostas interrompidas ficam sinalizadas no histórico; o contexto do modelo inclui
a pergunta e uma indicação de interrupção, sem pressupor que todo o texto foi ouvido.

Validação física: no headset, iniciar uma sessão e fazer dez perguntas; interromper
respostas curtas e longas; aguardar em silêncio; testar segurar/soltar e cancelar;
interromper a rede, verificar o erro e reiniciar explicitamente após reconectar.
Os testes automatizados simulam esses fluxos; não comprovam a qualidade acústica.
