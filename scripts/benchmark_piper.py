"""Compare loaded Piper voices without playing audio or making paid calls."""
import json
import time
from pathlib import Path
from raspberry_phone.tts import _load_piper_voice
rows=[]
for name in ('pt_BR-faber-medium','pt_BR-edresson-low'):
 start=time.monotonic()
 voice=_load_piper_voice(Path('models')/(name+'.onnx'))
 load=time.monotonic()-start
 for phase in ('cold','warm'):
  start=time.monotonic(); first=None; duration=0
  for c in voice.synthesize('Claro, posso ajudar com isso. Vamos começar pelo mais simples.'):
   if first is None: first=time.monotonic()-start
   duration+=len(c.audio_int16_bytes)/(c.sample_rate*c.sample_channels*2)
  rows.append(dict(voice=name,phase=phase,load_seconds=load,first_chunk_seconds=first,total_seconds=time.monotonic()-start,audio_seconds=duration))
print(json.dumps(rows,indent=2))
