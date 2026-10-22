import asyncio
import json
import sys
from types import SimpleNamespace
import pytest
from raspberry_phone.live_stt import DeepgramSpeechInput
from raspberry_phone.stt import TranscriptionError

@pytest.mark.parametrize('scenario',['pause','silence','server','cancel','timeout'])
def test_live_input_cleanup_preroll_and_utterance_boundary(monkeypatch,scenario):
 order=[]
 class Process:
  returncode=None
  def __init__(self): self.stdout=self
  async def read(self,n):
   if 'frame' not in order:
    order.append('frame'); return b'first syllable'
   await asyncio.Future()
  async def wait(self): return self.returncode
  def terminate(self): self.returncode=-15
  def kill(self): self.returncode=-9
 process=Process()
 async def spawn(*a,**kw): order.append('mic'); return process
 monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
 class Socket:
  async def __aenter__(self):
   await asyncio.sleep(.001); order.append('socket'); return self
  async def __aexit__(self,*a): order.append('closed')
  async def send(self,data): order.append(data)
  async def __aiter__(self):
   await asyncio.sleep(.01)
   if scenario=='server': yield json.dumps(dict(type='Error')); return
   if scenario in {'silence','timeout','cancel'}: await asyncio.Future()
   for text,final in [('Quero arroz',True),('com ovo',True)]:
    yield json.dumps(dict(type='Results',channel={'alternatives':[{'transcript':text}]},is_final=final,speech_final=True))
   yield json.dumps(dict(type='UtteranceEnd'))
 monkeypatch.setitem(sys.modules,'websockets.asyncio.client',SimpleNamespace(connect=lambda *a,**k:Socket()))
 stt=DeepgramSpeechInput(api_key='secret',device='fake',max_seconds=-4.95 if scenario=='timeout' else 1,no_speech_seconds=.02)
 partial=[]
 async def run():
  task=asyncio.create_task(stt._listen(partial.append,lambda:order.append('ready')))
  if scenario=='cancel':
   await asyncio.sleep(.015); task.cancel()
  return await task
 if scenario=='pause':
  assert asyncio.run(run())=='Quero arroz com ovo'
  assert partial==['Quero arroz','Quero arroz com ovo']
  assert order.index('mic') < order.index('frame') < order.index('socket')
  assert b'first syllable' in order
 else:
  with pytest.raises(asyncio.CancelledError if scenario=='cancel' else TranscriptionError): asyncio.run(run())
 assert process.returncode==-15
 assert 'closed' in order
