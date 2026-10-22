#!/usr/bin/env bash
set -euo pipefail
mode="${1:---plan}"
if [[ "$mode" == --plan ]]; then
 echo 'Desativar powersave da conexão Wi-Fi ativa e selecionar governor performance.'
 echo 'Aplicar: sudo bash scripts/performance_pi.sh --apply; rollback será salvo em /var/backups.'
 exit 0
fi
[[ "$mode" == --apply && "$EUID" == 0 ]] || { echo 'Use --plan ou sudo --apply'; exit 2; }
backup="/var/backups/raspberry-phone-performance.$(date +%Y%m%d%H%M%S)"
mkdir -p "$backup"
restore="$backup/restore.sh"
printf '#!/usr/bin/env bash\nset -euo pipefail\n' > "$restore"
for path in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do
 [[ -f "$path" ]] || continue
 previous="$(cat "$path")"
 printf 'printf %%s %q > %q\n' "$previous" "$path" >> "$restore"
 echo performance > "$path"
done
iface="$(iw dev | awk '$1 == "Interface" {print $2; exit}')"
if [[ -n "$iface" ]]; then
 connection="$(nmcli -g GENERAL.CONNECTION device show "$iface")"
 previous="$(nmcli -g 802-11-wireless.powersave connection show "$connection")"
 previous="${previous%% *}"
 printf 'nmcli connection modify %q 802-11-wireless.powersave %q\n' "$connection" "$previous" >> "$restore"
 prior_power="$(iw dev "$iface" get power_save | awk '{print $3}')"
 printf 'iw dev %q set power_save %q\n' "$iface" "$prior_power" >> "$restore"
 nmcli connection modify "$connection" 802-11-wireless.powersave 2
 iw dev "$iface" set power_save off
fi
chmod 700 "$restore"
echo "Rollback: sudo bash $restore"
