import csv, math, statistics
from collections import defaultdict
from pathlib import Path
rows=defaultdict(list)
for r in csv.DictReader(Path('measurements/acoustic.csv').open()):
 if r['error']: continue
 rows[r['mode']].append(float(r['first_audible_seconds'])-float(r['end_of_speech_seconds']))
for mode,values in rows.items():
 values.sort()
 if any(x<0 for x in values): raise ValueError('Tempos inválidos')
 print(mode,len(values),'p50',statistics.median(values),'p95',values[math.ceil(.95*len(values))-1])
