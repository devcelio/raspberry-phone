#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
quality="${1:--qh}"

if [[ "$quality" == "-ql" ]]; then
  export MANIM_PIXEL_WIDTH="${MANIM_PIXEL_WIDTH:-270}"
  export MANIM_PIXEL_HEIGHT="${MANIM_PIXEL_HEIGHT:-480}"
fi

manim_bin="${MANIM_BIN:-$project_root/.venv-manim/bin/manim}"

"$manim_bin" "$quality" \
  "$project_root/animations/phone_scenes.py" \
  PipelineOverview \
  SpeechToText \
  OpenRouterHub \
  StreamingComparison \
  SentenceAudioQueue \
  TextToSpeech \
  LocalVsCloud \
  FullSystemLoop
