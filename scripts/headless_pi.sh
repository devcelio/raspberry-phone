#!/usr/bin/env bash
# Run on the Pi: sudo bash scripts/headless_pi.sh --apply
# With no arguments, only print the plan. DNS and Pi-hole stay untouched.
set -euo pipefail

mode="${1:---plan}"
case "$mode" in
  --plan|--apply) ;;
  *) echo "Usage: $0 [--plan|--apply]" >&2; exit 2 ;;
esac

cat <<'PLAN'
Configure console boot and stop the desktop now.
Disable desktop sharing, desktop audio servers, Bluetooth, mDNS and printing.
Block desktop-only background services from being activated again.
Keep SSH, Tailscale, Wi-Fi, ALSA/USB audio, DNS, Pi-hole and swap.
Save a root-only rollback script before changing each service.
No packages are removed and no reboot is required.
PLAN
[[ "$mode" == --apply ]] || exit 0

if [[ "$EUID" -ne 0 || -z "${SUDO_USER:-}" || "$SUDO_USER" == root ]]; then
  echo "Run with sudo from your normal Raspberry Pi user account." >&2
  exit 1
fi
if [[ ! -r /proc/device-tree/model ]] || ! grep -q 'Raspberry Pi' /proc/device-tree/model; then
  echo "This script must run on the Raspberry Pi." >&2
  exit 1
fi

task_user="$SUDO_USER"
task_uid=$(id -u "$task_user")
backup_dir=$(mktemp -d /var/backups/raspberry-phone-headless.XXXXXX)
rollback="$backup_dir/restore.sh"
printf '#!/usr/bin/env bash\nset -eu\n' > "$rollback"
chmod 700 "$rollback"
printf 'systemctl set-default %q\n' "$(systemctl get-default)" >> "$rollback"
free -k > "$backup_dir/memory-before.txt"
systemctl list-units --type=service --state=running --no-pager > "$backup_dir/services-before.txt"
echo "Rollback: sudo bash $rollback"

user_systemctl() {
  runuser -u "$task_user" -- env XDG_RUNTIME_DIR="/run/user/$task_uid" systemctl --user "$@"
}

change_unit() {
  local scope="$1" action="$2" unit="$3" loaded enabled
  local -a control restore
  if [[ "$scope" == user ]]; then
    control=(user_systemctl)
    restore=(runuser -u "$task_user" -- env "XDG_RUNTIME_DIR=/run/user/$task_uid" systemctl --user)
  else
    control=(systemctl)
    restore=(systemctl)
  fi
  loaded=$("${control[@]}" show --property=LoadState --value "$unit")
  [[ "$loaded" != not-found ]] || return 0
  enabled=$("${control[@]}" is-enabled "$unit" 2>/dev/null || true)
  [[ "$enabled" != masked && "$enabled" != masked-runtime ]] || return 0

  # Write the undo operation before attempting the corresponding change.
  if [[ "$action" == mask ]]; then
    printf '%q ' "${restore[@]}" unmask "$unit" >> "$rollback"
    printf '\n' >> "$rollback"
  fi
  case "$enabled" in
    enabled|enabled-runtime)
      printf '%q ' "${restore[@]}" enable >> "$rollback"
      [[ "$enabled" != enabled-runtime ]] || printf '%q ' --runtime >> "$rollback"
      printf '%q\n' "$unit" >> "$rollback"
      ;;
  esac
  "${control[@]}" "$action" --now "$unit"
}

# The phone uses ALSA directly; desktop audio daemons are unnecessary.
for unit in rpi-connect-signin.path rpi-connect-wayvnc.service rpi-connect.service \
  pipewire-pulse.socket pipewire.socket pipewire-pulse.service wireplumber.service \
  filter-chain.service pipewire.service mpris-proxy.service; do
  change_unit user mask "$unit"
done

systemctl set-default multi-user.target
change_unit system disable lightdm.service

# Closing LightDM can leave desktop D-Bus helpers in the user's SSH session.
for unit in xdg-desktop-portal.service xdg-document-portal.service \
  xdg-permission-store.service gvfs-afc-volume-monitor.service \
  gvfs-daemon.service gvfs-goa-volume-monitor.service \
  gvfs-gphoto2-volume-monitor.service gvfs-mtp-volume-monitor.service \
  gvfs-udisks2-volume-monitor.service; do
  if [[ "$(user_systemctl show --property=LoadState --value "$unit")" != not-found ]]; then
    user_systemctl stop "$unit"
  fi
done

for unit in bluetooth.service avahi-daemon.socket avahi-daemon.service \
  cups.path cups.socket cups.service; do
  change_unit system mask "$unit"
done
for unit in packagekit.service accounts-daemon.service udisks2.service; do
  change_unit system mask "$unit"
done

echo "Console configuration applied. Current memory:"
free -h
echo "Critical services:"
systemctl is-active ssh.service tailscaled.service NetworkManager.service
echo "Pi-hole (unchanged by this script):"
systemctl is-active pihole-FTL.service || true
echo "Default boot target: $(systemctl get-default)"
echo "Rollback: sudo bash $rollback"
echo "After rollback, reboot to restore the previous desktop sessions and services."
