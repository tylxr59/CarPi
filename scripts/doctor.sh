#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
"$SCRIPT_DIR/check-host.sh"
"$SCRIPT_DIR/check-bluetooth.sh"
"$SCRIPT_DIR/check-wifi.sh"
"$SCRIPT_DIR/check-usb-gadget.sh"
echo "== Video =="
if command -v ffmpeg >/dev/null; then
  ffmpeg -version | head -n 1
  ffmpeg -hide_banner -encoders 2>/dev/null | awk '/h264|H264/ {print "Encoder: " $2}'
else
  echo "FFmpeg: missing"
fi
echo "== Service / project =="
if command -v systemctl >/dev/null; then
  echo "carpi.service: $(systemctl is-active carpi.service 2>/dev/null || true)"
  echo "enabled: $(systemctl is-enabled carpi.service 2>/dev/null || true)"
fi
if command -v carpi >/dev/null; then carpi --version; fi
ROOT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
if [[ -f $ROOT_DIR/src/carpi/__main__.py ]] && command -v python3 >/dev/null; then
  PYTHONPATH="$ROOT_DIR/src" python3 -m carpi --version
fi
if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Commit: $(git -C "$ROOT_DIR" rev-parse --short HEAD)"
  if [[ -n $(git -C "$ROOT_DIR" status --porcelain) ]]; then echo "Working tree: modified"; fi
fi
echo "No Wi-Fi passwords, Bluetooth keys, or raw packet payloads included."
