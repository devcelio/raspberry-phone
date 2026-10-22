#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bin=.deps/whisper.cpp/build/bin
if [[ ! -f models/ggml-tiny-q5_1.bin ]]; then
  "$bin/quantize" models/ggml-tiny.bin models/ggml-tiny-q5_1.bin q5_1
fi
exec "$bin/whisper-server" --host 127.0.0.1 --port 8081 -m models/ggml-tiny-q5_1.bin -l pt -bs 1 -bo 1 -ac 512 -t 2 -nc
