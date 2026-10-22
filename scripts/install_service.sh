#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$project_root" != "$HOME/raspberry-phone" ]]; then
  echo 'Instale o projeto em ~/raspberry-phone antes de instalar este serviço.' >&2
  exit 2
fi
mkdir -p "$HOME/.config/systemd/user"
install -m 644 "$project_root/systemd/raspberry-phone.service" "$HOME/.config/systemd/user/raspberry-phone.service"
systemctl --user daemon-reload
systemctl --user enable raspberry-phone.service
systemctl --user restart raspberry-phone.service
if [[ "$(loginctl show-user "$USER" -p Linger --value)" != yes ]]; then
  echo "Para iniciar sem login, execute: sudo loginctl enable-linger $USER"
fi
