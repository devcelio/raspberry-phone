#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
architecture="$(uname -m)"
memory_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
minimum_disk_kb="${MINIMUM_DISK_KB:-2097152}"
hardware_model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
fi

printf 'Sistema:\n'
hostnamectl 2>/dev/null || true
printf 'arquitetura=%s\n' "$architecture"
printf 'hardware=%s\n' "${hardware_model:-desconhecido}"
printf 'sistema_operacional=%s\n' "${PRETTY_NAME:-desconhecido}"
free -h
df -h / "${HOME}"

case "$architecture" in
  aarch64|arm64) ;;
  *)
    echo "Erro: o MVP exige um sistema operacional ARM de 64 bits." >&2
    exit 2
    ;;
esac

if [[ "$hardware_model" != *"Raspberry Pi 5"* && "$hardware_model" != *"Raspberry Pi Zero 2 W"* ]]; then
  echo "Erro: o hardware detectado não é um Raspberry Pi 5 ou Zero 2 W." >&2
  exit 2
fi

case "${ID:-}" in
  debian|raspbian) ;;
  *)
    echo "Erro: o MVP exige Raspberry Pi OS baseado em Debian." >&2
    exit 2
    ;;
esac

if (( memory_kb < 350000 )); then
  echo "Erro: menos de 350 MB de RAM detectados." >&2
  exit 2
fi

available_disk_kb="$(df -Pk "$project_root" | awk 'NR == 2 {print $4}')"
if [[ -z "$available_disk_kb" ]] || (( available_disk_kb < minimum_disk_kb )); then
  echo "Erro: são necessários pelo menos 2 GB livres no volume do projeto." >&2
  exit 2
fi

printf '\nUSB:\n'
lsusb
printf '\nCaptura ALSA:\n'
arecord -l
printf '\nReprodução ALSA:\n'
aplay -l

audio_config="${PHONE_AUDIO_CONFIG:-$("$script_dir/detect_audio_device.sh")}"
printf '\nDispositivo bidirecional detectado:\n'
printf '%s\n' "$audio_config"
