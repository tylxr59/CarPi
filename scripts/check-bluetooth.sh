#!/usr/bin/env bash
set -euo pipefail
echo "== Bluetooth =="
if command -v bluetoothctl >/dev/null; then
  bluetoothctl --version | sed 's/^/BlueZ: /'
  bluetoothctl list | awk '/^Controller / {count++; print "Controller " count ": present (address/name redacted)"}' || true
else
  echo "bluetoothctl: missing (install bluez)"
fi
if command -v rfkill >/dev/null; then
  rfkill list bluetooth || true
else
  echo "rfkill: missing"
fi
if command -v lsmod >/dev/null; then
  lsmod | awk 'NR==1 || /^(bluetooth|btusb|hci_uart|rfcomm)[[:space:]]/'
fi
