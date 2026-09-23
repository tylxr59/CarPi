#!/usr/bin/env bash
set -euo pipefail
DRY_RUN=0
if [[ ${1:-} == --dry-run ]]; then DRY_RUN=1; shift; fi
if [[ $# -ne 0 ]]; then echo "Usage: $0 [--dry-run]" >&2; exit 2; fi
if [[ $EUID -ne 0 && $DRY_RUN -eq 0 ]]; then echo "Run with sudo" >&2; exit 1; fi
run() {
  if [[ $DRY_RUN -eq 1 ]]; then printf '[dry-run]'; printf ' %q' "$@"; printf '\n';
  else "$@"; fi
}
if [[ -f /etc/systemd/system/carpi.service ]] && grep -q '^# Installed by carpi$' /etc/systemd/system/carpi.service; then
  run systemctl disable --now carpi.service
  run rm -f /etc/systemd/system/carpi.service
  run systemctl daemon-reload
fi
if [[ -f /usr/local/bin/carpi ]] && grep -q '^# Installed by carpi$' /usr/local/bin/carpi; then
  run rm -f /usr/local/bin/carpi
fi
if [[ -f /usr/local/lib/carpi/carpi/__init__.py ]]; then
  for name in __init__.py __main__.py bluetooth.py cli.py config.py iap2.py probe.py video.py; do
    if [[ -f /usr/local/lib/carpi/carpi/$name ]]; then
      run rm -f "/usr/local/lib/carpi/carpi/$name"
    fi
  done
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] rmdir /usr/local/lib/carpi/carpi and parent if empty"
  else
    rmdir /usr/local/lib/carpi/carpi /usr/local/lib/carpi 2>/dev/null || true
  fi
fi
echo "Removed project service and program. /etc/carpi, /var/lib/carpi, captures, logs and packages retained."
