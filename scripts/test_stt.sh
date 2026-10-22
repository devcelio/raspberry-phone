#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"

if [[ ! -f "$project_root/runtime/audio-test.wav" ]]; then
  echo "Gravação ausente; execute scripts/test_audio.sh primeiro." >&2
  exit 2
fi

"$project_root/.deps/whisper.cpp/build/bin/whisper-cli" \
  -m "$project_root/models/ggml-tiny.bin" \
  -f "$project_root/runtime/audio-test.wav" \
  -l pt -nt -np
