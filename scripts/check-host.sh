#!/usr/bin/env bash
set -euo pipefail
echo "== Host =="
if [[ -r /etc/os-release ]]; then
  # shellcheck source=/dev/null
  . /etc/os-release
  echo "OS: ${PRETTY_NAME:-unknown}"
fi
echo "Kernel: $(uname -srmo)"
if [[ -r /proc/device-tree/model ]]; then
  echo "Pi model: $(tr -d '\0' </proc/device-tree/model)"
else
  echo "Pi model: unavailable (not running on a Pi?)"
fi
if [[ -r /proc/meminfo ]]; then
  awk '/MemTotal:/ {printf "RAM: %.0f MiB\n", $2/1024}' /proc/meminfo
fi
echo "Architecture: $(uname -m)"
