#!/usr/bin/env bash
set -euo pipefail
usage() { echo "Usage: $0 {bluetooth|network IFACE|usb USBMON_IFACE} [OUTPUT_DIR]" >&2; exit 2; }
[[ $# -ge 1 && $# -le 3 ]] || usage
MODE=$1
case "$MODE" in
  bluetooth) [[ $# -le 2 ]] || usage; OUT=${2:-captures} ;;
  network|usb) [[ $# -ge 2 ]] || usage; IFACE=$2; OUT=${3:-captures} ;;
  *) usage ;;
esac
if [[ $EUID -ne 0 ]]; then echo "Run with sudo; captures require elevated access" >&2; exit 1; fi
umask 077
mkdir -p -- "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
echo "Captures can contain identifiers, credentials and location-related data. Review before sharing."
echo "Capture stays local. Press Ctrl+C to stop."
case "$MODE" in
  bluetooth)
    command -v btmon >/dev/null || { echo "btmon missing (bluez)" >&2; exit 1; }
    exec btmon -w "$OUT/carpi-bt-$STAMP.snoop"
    ;;
  network)
    command -v tcpdump >/dev/null || { echo "tcpdump missing" >&2; exit 1; }
    exec tcpdump -i "$IFACE" -s 0 -w "$OUT/carpi-net-$STAMP.pcap"
    ;;
  usb)
    command -v tcpdump >/dev/null || { echo "tcpdump missing" >&2; exit 1; }
    [[ $IFACE == usbmon[0-9]* ]] || { echo "Expected usbmon interface name" >&2; exit 1; }
    exec tcpdump -i "$IFACE" -s 0 -w "$OUT/carpi-usb-$STAMP.pcap"
    ;;
esac
