import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from raspberry_phone.agent import VoiceAgentAssistant, agent_settings
from raspberry_phone.assistant import AssistantError
from raspberry_phone.config import AppConfig
from raspberry_phone.conversation import ConversationHistory, ConversationStore
from raspberry_phone.state import StateStore


def config(tmp_path):
    return AppConfig.from_mapping({
        "OPENROUTER_API_KEY": "test-router-secret", "DEEPGRAM_API_KEY": "test-deep-secret",
        "AUDIO_CAPTURE_DEVICE": "capture", "AUDIO_PLAYBACK_DEVICE": "playback",
        "CONVERSATION_BACKEND": "deepgram-agent", "OPENROUTER_MODEL": "deepseek/example",
    }, root=tmp_path)


def test_settings_route_model_and_history_to_openrouter(tmp_path):
    history = ConversationHistory()
    history.add_turn("Oi", "Olá")
    settings = agent_settings(config(tmp_path), history)
    think = settings["agent"]["think"]
    assert think["provider"]["model"] == "deepseek/example"
    assert think["endpoint"]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert settings["agent"]["context"]["messages"][0] == {"type":"History", "role":"user", "content":"Oi"}
    assert settings["audio"]["output"]["container"] == "none"


@pytest.mark.parametrize("fail", [False, True])
def test_agent_streams_and_persists_turn_without_exposing_secrets(tmp_path, monkeypatch, fail):
    store = ConversationStore(tmp_path / "conversation.json")
    state = StateStore(tmp_path / "state.json", turns_provider=store.turns)
    history = ConversationHistory()
    assistant = VoiceAgentAssistant(config(tmp_path), history, store, state)

    class Socket:
        closed = False
        async def __aenter__(self): return self
        async def __aexit__(self, *_): self.closed = True
        async def send_raw(self, _): pass
        async def send_keep_alive(self): pass
        async def recv(self): return SimpleNamespace(type="SettingsApplied")
        async def __aiter__(self):
            yield SimpleNamespace(type="ConversationText", role="user", content="Por quê?")
            yield SimpleNamespace(type="ConversationText", role="assistant", content="Porque sim.")
            yield b"\x00\x00" * 2400
            await asyncio.sleep(.01)
            assert state.snapshot()["status"] == "speaking"
            if fail:
                raise RuntimeError("Authorization: test-router-secret")
            yield SimpleNamespace(type="AgentAudioDone")

    socket = Socket()
    monkeypatch.setitem(sys.modules, "deepgram", SimpleNamespace(
        AsyncDeepgramClient=lambda **_: SimpleNamespace(agent=SimpleNamespace(v1=SimpleNamespace(connect=lambda:socket)))
    ))
    if fail:
        with pytest.raises(AssistantError, match="Falha na conexão"):
            asyncio.run(assistant.run_session(test_text="Por quê?",play_audio=False))
        assert not history.messages()
        assert store.turns()[0]["status"] == "error"
        assert "test-router-secret" not in state.path.read_text()
    else:
        result = asyncio.run(assistant.run_session(test_text="Por quê?",play_audio=False))
        assert result.answer == "Porque sim."
        assert store.turns()[0]["status"] == "complete"
        assert state.snapshot()["status"] == "ready"
        assert "transcript_to_audio" in result.timings_seconds
    assert socket.closed

@pytest.mark.parametrize('scenario', ['cancel', 'silence', 'response_timeout', 'capture_error'])
def test_agent_releases_fake_microphone_and_socket(tmp_path, monkeypatch, scenario):
    import asyncio
    real_wait = asyncio.wait_for
    real_sleep = asyncio.sleep
    async def short_wait(awaitable, timeout):
        return await real_wait(awaitable, .03 if timeout == 6 else timeout)
    async def short_sleep(delay):
        await real_sleep(.03 if delay == 10 else delay)
    monkeypatch.setattr(asyncio, 'wait_for', short_wait)
    monkeypatch.setattr(asyncio, 'sleep', short_sleep)
    class Process:
        returncode = None
        def __init__(self): self.stdout = self
        async def read(self, n):
            if scenario == 'capture_error': return b''
            await real_sleep(.001)
            return b'pcm'
        async def wait(self): return self.returncode
        def terminate(self): self.returncode = -15
        def kill(self): self.returncode = -9
    process = Process()
    async def spawn(*a, **kw): return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    class Socket:
        closed = False
        async def __aenter__(self): return self
        async def __aexit__(self, *a): self.closed = True
        async def send_raw(self, _): pass
        async def send_media(self, _): pass
        async def send_keep_alive(self): pass
        async def recv(self): return SimpleNamespace(type='SettingsApplied')
        async def __aiter__(self):
            if scenario == 'response_timeout':
                yield SimpleNamespace(type='ConversationText', role='user', content='Oi')
            await asyncio.Future()
    socket = Socket()
    monkeypatch.setitem(sys.modules, 'deepgram', SimpleNamespace(AsyncDeepgramClient=lambda **k: SimpleNamespace(agent=SimpleNamespace(v1=SimpleNamespace(connect=lambda: socket)))))
    store = ConversationStore(tmp_path/'c.json')
    assistant = VoiceAgentAssistant(config(tmp_path), ConversationHistory(), store, StateStore(tmp_path/'s.json', turns_provider=store.turns))
    async def run():
        task = asyncio.create_task(assistant.run_session(play_audio=False))
        if scenario == 'cancel':
            await real_sleep(.01)
            task.cancel()
        await task
    with pytest.raises(asyncio.CancelledError if scenario == 'cancel' else AssistantError):
        asyncio.run(run())
    assert process.returncode == -15
    if scenario != 'capture_error': assert socket.closed
    assert store.turns()[0]['status'] == 'error'
