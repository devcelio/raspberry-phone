#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
whisper_version="v1.8.1"
whisper_dir="$project_root/.deps/whisper.cpp"
model_dir="$project_root/models"

sudo apt-get update
sudo apt-get install -y \
  alsa-utils \
  build-essential \
  cmake \
  git \
  libopenblas-dev \
  python3-pip \
  python3-venv \
  rsync \
  usbutils

audio_config="$("$script_dir/detect_audio_device.sh")"
PHONE_AUDIO_CONFIG="$audio_config" "$script_dir/diagnose_pi.sh"
capture_device="$(printf '%s\n' "$audio_config" | sed -n 's/^AUDIO_CAPTURE_DEVICE=//p')"
playback_device="$(printf '%s\n' "$audio_config" | sed -n 's/^AUDIO_PLAYBACK_DEVICE=//p')"

mkdir -p "$project_root/.deps" "$model_dir" "$project_root/runtime"
if [[ ! -d "$whisper_dir/.git" ]]; then
  git clone --branch "$whisper_version" --depth 1 \
    https://github.com/ggml-org/whisper.cpp.git "$whisper_dir"
else
  git -C "$whisper_dir" fetch --depth 1 origin "refs/tags/$whisper_version:refs/tags/$whisper_version"
  git -C "$whisper_dir" checkout --detach "$whisper_version"
fi

cmake -S "$whisper_dir" -B "$whisper_dir/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_BLAS=ON \
  -DGGML_BLAS_VENDOR=OpenBLAS
cmake --build "$whisper_dir/build" --config Release -j "${BUILD_JOBS:-2}" --target whisper-cli whisper-server quantize

if [[ ! -f "$model_dir/ggml-tiny.bin" ]]; then
  "$whisper_dir/models/download-ggml-model.sh" tiny
  cp "$whisper_dir/models/ggml-tiny.bin" "$model_dir/ggml-tiny.bin"
fi

if [[ ! -x "$project_root/.venv/bin/python" ]]; then
  python3 -m venv "$project_root/.venv"
fi
"$project_root/.venv/bin/pip" install --upgrade pip setuptools wheel
"$project_root/.venv/bin/pip" install -e "$project_root[streaming]"

if [[ ! -f "$model_dir/pt_BR-faber-medium.onnx" ]]; then
  "$project_root/.venv/bin/python" -m piper.download_voices \
    pt_BR-faber-medium --data-dir "$model_dir"
fi

if [[ ! -f "$project_root/.env" ]]; then
  cp "$project_root/.env.example" "$project_root/.env"
  sed -i \
    "s|^AUDIO_CAPTURE_DEVICE=.*|AUDIO_CAPTURE_DEVICE=$capture_device|" \
    "$project_root/.env"
  sed -i \
    "s|^AUDIO_PLAYBACK_DEVICE=.*|AUDIO_PLAYBACK_DEVICE=$playback_device|" \
    "$project_root/.env"
fi
chmod 600 "$project_root/.env"

printf '\nBootstrap concluído.\n'
printf '1. Edite %s/.env e preencha OPENROUTER_API_KEY e DEEPGRAM_API_KEY (modo padrão).\n' "$project_root"
printf '2. Rode: %s/scripts/test_audio.sh\n' "$project_root"
printf '3. Rode: cd %s && .venv/bin/python -m raspberry_phone\n' "$project_root"
