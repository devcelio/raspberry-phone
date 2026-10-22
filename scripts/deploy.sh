#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
pi_host="${PI_HOST:?Defina PI_HOST como usuario@host-do-raspberry}"
pi_dir="${PI_DIR:?Defina PI_DIR como o caminho absoluto do projeto no Raspberry}"

# Os valores também entram em um comando remoto; aceite só destinos simples.
if [[ ! "$pi_host" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.@-]*$ || ! "$pi_dir" =~ ^/[a-zA-Z0-9_./-]+$ ]]; then
  echo 'PI_HOST ou PI_DIR inválido: use um host SSH e caminho absoluto sem espaços.' >&2
  exit 2
fi

ssh -o BatchMode=yes "$pi_host" "mkdir -p '$pi_dir'"
rsync -az \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.deps/' \
  --exclude '.env' \
  --include '.env.example' \
  --exclude '.env.*' \
  --exclude '.venv-manim/' \
  --exclude 'media/' \
  --exclude '*.docx' \
  --exclude '.mypy_cache/' \
  --exclude 'models/' \
  --exclude 'runtime/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  "$project_root/" "$pi_host:$pi_dir/"

echo "Projeto enviado para $pi_host:$pi_dir"
