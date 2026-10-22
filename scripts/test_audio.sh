#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"

if [[ ! -f "$project_root/.env" ]]; then
  echo "Arquivo .env ausente; execute scripts/bootstrap_pi.sh." >&2
  exit 2
fi

set -a
source "$project_root/.env"
set +a

: "${AUDIO_CAPTURE_DEVICE:?Defina AUDIO_CAPTURE_DEVICE no .env}"
: "${AUDIO_PLAYBACK_DEVICE:?Defina AUDIO_PLAYBACK_DEVICE no .env}"
mkdir -p "$project_root/runtime"
test_wav="$project_root/runtime/audio-test.wav"

echo "Gravando 5 segundos..."
arecord -q -D "$AUDIO_CAPTURE_DEVICE" -f S16_LE -r 16000 -c 1 -d 5 "$test_wav"
echo "Reproduzindo a gravação..."
aplay -q -D "$AUDIO_PLAYBACK_DEVICE" "$test_wav"
echo "Teste de áudio concluído."
