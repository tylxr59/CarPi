#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DRY_RUN=0
DEV=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --dev) DEV=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [[ ! -r /etc/os-release ]]; then echo "Missing /etc/os-release" >&2; exit 1; fi
# shellcheck source=/dev/null
. /etc/os-release
if [[ ${ID:-} != raspbian && ${ID:-} != debian && ${ID_LIKE:-} != *debian* ]]; then
  echo "Requires Raspberry Pi OS or Debian; found ${PRETTY_NAME:-unknown}" >&2; exit 1
fi
if [[ $(uname -m) != aarch64 ]]; then echo "Requires ARM64/aarch64" >&2; exit 1; fi
MODEL=$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)
if [[ $MODEL != *"Raspberry Pi 4"* ]]; then
  echo "Warning: hardware does not identify as Raspberry Pi 4: ${MODEL:-unknown}" >&2
fi
if [[ $EUID -ne 0 && $DRY_RUN -eq 0 ]]; then echo "Run with sudo" >&2; exit 1; fi
if [[ -f /usr/local/bin/carpi ]] && ! grep -q '^# Installed by carpi$' /usr/local/bin/carpi; then
  echo "Refusing to replace unrelated /usr/local/bin/carpi" >&2; exit 1
fi
if [[ -f /etc/systemd/system/carpi.service ]] && ! grep -q '^# Installed by carpi$' /etc/systemd/system/carpi.service; then
  echo "Refusing to replace unrelated carpi.service" >&2; exit 1
fi

run() {
  if [[ $DRY_RUN -eq 1 ]]; then printf '[dry-run]'; printf ' %q' "$@"; printf '\n';
  else "$@"; fi
}
backup_if_different() {
  local source=$1 target=$2
  if [[ -f $target ]] && ! cmp -s "$source" "$target"; then
    run cp -a -- "$target" "${target}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  fi
}

packages=(python3 bluez ffmpeg tcpdump usbutils rfkill)
if [[ $DEV -eq 1 ]]; then packages+=(shellcheck python3-pytest); fi
run apt-get update
run apt-get install -y "${packages[@]}"
run install -d -m 0755 /usr/local/lib/carpi/carpi /etc/carpi /var/lib/carpi
for source in "$ROOT_DIR"/src/carpi/*.py; do
  run install -m 0644 "$source" "/usr/local/lib/carpi/carpi/$(basename "$source")"
done
if [[ ! -e /etc/carpi/carpi.toml ]]; then
  run install -m 0640 "$ROOT_DIR/config/carpi.example.toml" /etc/carpi/carpi.toml
fi
WRAPPER=$(mktemp)
trap 'rm -f "$WRAPPER"' EXIT
cat >"$WRAPPER" <<'EOF'
#!/bin/sh
# Installed by carpi
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/usr/local/lib/carpi exec /usr/bin/python3 -m carpi "$@"
EOF
backup_if_different "$WRAPPER" /usr/local/bin/carpi
run install -m 0755 "$WRAPPER" /usr/local/bin/carpi
backup_if_different "$ROOT_DIR/systemd/carpi.service" /etc/systemd/system/carpi.service
run install -m 0644 "$ROOT_DIR/systemd/carpi.service" /etc/systemd/system/carpi.service
run systemctl daemon-reload
echo "Installed carpi. Bluetooth uses root privileges via sudo; no setcap or BlueZ changes needed."
echo "Service installed but not enabled or started. Next: scripts/doctor.sh; sudo carpi probe --target MAC"
echo "No pairing, network changes, USB gadget setup, or credential storage performed."
