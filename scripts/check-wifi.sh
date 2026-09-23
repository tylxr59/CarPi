#!/usr/bin/env bash
set -euo pipefail
echo "== Wi-Fi =="
if command -v iw >/dev/null; then
  iw dev | awk '/Interface / {print "Interface: " $2}'
else
  for path in /sys/class/net/*/wireless; do
    [[ -d $path ]] && echo "Interface: $(basename "$(dirname "$path")")"
  done
fi
if command -v rfkill >/dev/null; then rfkill list wifi || true; fi
