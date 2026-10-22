#!/usr/bin/env bash
set -euo pipefail

for command_name in arecord aplay; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name não encontrado; instale alsa-utils" >&2
    exit 2
  fi
done

capture_endpoints="$(mktemp)"
playback_endpoints="$(mktemp)"
capture_cards="$(mktemp)"
playback_cards="$(mktemp)"
shared_cards="$(mktemp)"
trap 'rm -f "$capture_endpoints" "$playback_endpoints" "$capture_cards" "$playback_cards" "$shared_cards"' EXIT

(arecord -l 2>/dev/null || true) \
  | sed -nE 's/^card [0-9]+: ([^ ]+).*device ([0-9]+):.*/\1 \2/p' \
  | sort -u >"$capture_endpoints"
(aplay -l 2>/dev/null || true) \
  | sed -nE 's/^card [0-9]+: ([^ ]+).*device ([0-9]+):.*/\1 \2/p' \
  | sort -u >"$playback_endpoints"
cut -d ' ' -f 1 "$capture_endpoints" | sort -u >"$capture_cards"
cut -d ' ' -f 1 "$playback_endpoints" | sort -u >"$playback_cards"
comm -12 "$capture_cards" "$playback_cards" >"$shared_cards"

card_count="$(wc -l <"$shared_cards" | tr -d ' ')"
if [[ "$card_count" != "1" ]]; then
  echo "Esperava exatamente uma placa ALSA com captura e reprodução; encontrei $card_count." >&2
  echo "Endpoints de captura:" >&2
  sed -E 's/^([^ ]+) ([0-9]+)$/  - CARD=\1,DEV=\2/' "$capture_endpoints" >&2
  echo "Endpoints de reprodução:" >&2
  sed -E 's/^([^ ]+) ([0-9]+)$/  - CARD=\1,DEV=\2/' "$playback_endpoints" >&2
  exit 2
fi

phone_card="$(sed -n '1p' "$shared_cards")"
capture_devices="$(awk -v card="$phone_card" '$1 == card {print $2}' "$capture_endpoints")"
playback_devices="$(awk -v card="$phone_card" '$1 == card {print $2}' "$playback_endpoints")"
capture_count="$(printf '%s\n' "$capture_devices" | sed '/^$/d' | wc -l | tr -d ' ')"
playback_count="$(printf '%s\n' "$playback_devices" | sed '/^$/d' | wc -l | tr -d ' ')"

if [[ "$capture_count" != "1" || "$playback_count" != "1" ]]; then
  echo "A placa $phone_card precisa ter exatamente um endpoint de captura e um de reprodução." >&2
  echo "Captura: ${capture_devices:-nenhuma}; reprodução: ${playback_devices:-nenhuma}." >&2
  exit 2
fi

printf 'AUDIO_CAPTURE_DEVICE=plughw:CARD=%s,DEV=%s\n' "$phone_card" "$capture_devices"
printf 'AUDIO_PLAYBACK_DEVICE=plughw:CARD=%s,DEV=%s\n' "$phone_card" "$playback_devices"
