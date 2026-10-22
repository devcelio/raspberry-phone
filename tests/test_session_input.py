import asyncio
import json
import sys
import threading
from types import SimpleNamespace

import pytest

from raspberry_phone.live_stt import DeepgramSpeechInput
from raspberry_phone.stt import TranscriptionError


@pytest.mark.parametrize('scenario', ['continuous', 'manual', 'limit', 'disconnect', 'mic', 'stop'])
def test_session_input_boundaries_and_cleanup(monkeypatch, scenario):
    stop, release = threading.Event(), threading.Event()
    utterances, partials, sent, order = [], [], [], []
    class Process:
        returncode = None
        def __init__(self): self.stdout = self
        async def read(self, size):
            await asyncio.sleep(.002)
            if scenario == 'mic': return b''
            order.append('frame')
            return b'first syllable'
        async def wait(self): return self.returncode
        def terminate(self): self.returncode = -15
        def kill(self): self.returncode = -9
    process = Process()
    async def spawn(*args, **kwargs): return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    class Socket:
        async def __aenter__(self):
            await asyncio.sleep(.005)
            order.append('connected')
            return self
        async def __aexit__(self, *args): order.append('closed')
        async def send(self, data): sent.append(data)
        async def __aiter__(self):
            if scenario == 'stop':
                stop.set()
                await asyncio.Future()
            if scenario == 'disconnect':
                return
            # A long idle interval relative to the old no-speech timeout is normal.
            await asyncio.sleep(.02)
            for text in ['primeira frase', 'segunda frase']:
                yield json.dumps({'type': 'SpeechStarted'})
                yield json.dumps({'type': 'Results', 'channel': {'alternatives': [{'transcript': text}]}, 'is_final': True, 'speech_final': scenario != 'limit'})
                if scenario == 'limit':
                    while json.dumps({'type': 'Finalize'}) not in sent:
                        await asyncio.sleep(.01)
                    yield json.dumps({'type': 'Results', 'channel': {'alternatives': [{'transcript': ''}]}, 'is_final': True, 'from_finalize': True})
                    stop.set()
                    await asyncio.Future()
                if scenario == 'continuous':
                    assert utterances[-1] == text  # Respond at speech_final, before UtteranceEnd.
                    yield json.dumps({'type': 'Results', 'channel': {'alternatives': [{'transcript': 'começo seguinte'}]}, 'is_final': False})
                yield json.dumps({'type': 'UtteranceEnd'})
                if scenario == 'continuous':
                    assert partials[-1] == 'começo seguinte'  # A delayed boundary cannot erase new live speech.
            if scenario == 'manual':
                assert utterances == []  # Pauses must not release a held button.
                release.set()
                while json.dumps({'type': 'CloseStream'}) not in sent:
                    await asyncio.sleep(.005)
                yield json.dumps({'type': 'Metadata'})
            else:
                stop.set()
                await asyncio.Future()
    monkeypatch.setitem(sys.modules, 'websockets.asyncio.client', SimpleNamespace(connect=lambda *a, **k: Socket()))
    source = DeepgramSpeechInput(api_key='test', device='fake', max_seconds=.03 if scenario == 'limit' else 1, no_speech_seconds=.001)
    args = dict(stop=stop, release=release, manual=scenario == 'manual', on_ready=lambda: order.append('ready'),
                on_partial=partials.append, on_speech=lambda: order.append('speech'), on_utterance=utterances.append)
    if scenario in {'disconnect', 'mic'}:
        with pytest.raises(TranscriptionError): source.listen_session(**args)
    else:
        source.listen_session(**args)
    assert process.returncode == -15
    if scenario == 'continuous': assert utterances == ['primeira frase', 'segunda frase']
    if scenario == 'manual': assert utterances == ['primeira frase segunda frase']
    if scenario == 'limit': assert utterances == ['primeira frase']
    if scenario not in {'mic', 'stop', 'disconnect'}:
        assert order.index('frame') < order.index('connected')
        assert b'first syllable' in sent
