# Working on Raspberry Phone

Python package in `src/raspberry_phone/`, browser UI in its `web/` subdirectory.
Read `README.md` for setup; read `docs/advanced.md` when changing backends,
network access, deployment or session HTTP endpoints. Configuration lives in
`config.py`; `.env.example` is the template users copy.

## Find the right module

- `cli.py`: constructs dependencies, loads `.env`, starts CLI or web mode.
- `controller.py`, `session.py`, `session_input.py`: turn ownership, continuous
  sessions, push-to-talk and interruption. Keep capture IDs and cancellation coherent.
- `assistant.py`, `response.py`, `chunking.py`: transcript → streamed response → speech.
- `audio.py`, `stt.py`, `live_stt.py`, `llm.py`, `tts.py`, `agent.py`: hardware and
  provider adapters. Continuous mode uses Deepgram STT + OpenRouter + Piper.
- `conversation.py`, `state.py`, `storage.py`: history, live state and atomic writes.
- `web.py`, `web/`: HTTP/SSE endpoints and browser controls.
- `scripts/`, `systemd/`: Raspberry setup and operation. `animations/` is independent.

## Change and verify

Use Python 3.11+ and the existing standard-library/dataclass style. Keep provider
and hardware access behind the existing adapters so tests can use fakes.
When adding a setting, update `config.py`, `.env.example` and the relevant docs.
Keep user-facing UI copy in Brazilian Portuguese.

Run `make test` after changing behavior (requires `.venv` and pytest).
For a focused run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_config.py`.
Node.js runs the frontend tests through pytest. Shell changes also need
`bash -n scripts/*.sh`. Use fake providers for automated tests; hardware/audio
quality must be checked on the Raspberry and reported separately.

## Publication boundaries

Keep credentials in the ignored `.env`; use dummy credentials in fixtures.
Publish generic hosts and paths. Keep recordings, conversation history, models,
virtual environments and personal planning documents local. Review staged files
and scan for secrets before pushing. Historical benchmarks are observations,
not current model availability, pricing or guaranteed latency.
