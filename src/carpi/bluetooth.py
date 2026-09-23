"""BlueZ discovery and Linux RFCOMM client transport."""

from __future__ import annotations

import re
import shutil
import socket
import subprocess

IAP_UUID = "00000000-deca-fade-deca-deafdecacafe"


def devices() -> list[str]:
    if not shutil.which("bluetoothctl"):
        raise RuntimeError("bluetoothctl missing (install bluez)")
    result = subprocess.run(
        ["bluetoothctl", "devices"], capture_output=True, text=True, timeout=15, check=True
    )
    return [
        line.removeprefix("Device ")
        for line in result.stdout.splitlines()
        if line.startswith("Device ")
    ]


def sdp_channels(mac: str) -> list[tuple[int, str]]:
    if not shutil.which("sdptool"):
        raise RuntimeError("sdptool missing (install bluez or pass --channel)")
    result = subprocess.run(
        ["sdptool", "browse", mac], capture_output=True, text=True, timeout=30, check=True
    )
    return parse_sdp(result.stdout)


def parse_sdp(output: str) -> list[tuple[int, str]]:
    channels: list[tuple[int, str]] = []
    for record in re.split(r"(?=Service RecHandle:)", output):
        name_match = re.search(r"^Service Name:\s*(.+)$", record, re.MULTILINE)
        service = name_match.group(1).strip() if name_match else ""
        if IAP_UUID in record.lower() and not service:
            service = "iAP2 UUID"
        for match in re.finditer(r"Channel:\s*(\d+)", record):
            channel = int(match.group(1))
            if 1 <= channel <= 30:
                channels.append((channel, service))
    return channels


def select_channel(channels: list[tuple[int, str]]) -> int:
    matches = [
        (channel, name)
        for channel, name in channels
        if "iap" in name.lower() or "ipod" in name.lower()
    ]
    if len(matches) == 1:
        return matches[0][0]
    raise RuntimeError(f"ambiguous iAP2 RFCOMM service: {channels}; pass --channel explicitly")


def connect(mac: str, channel: int, timeout: float = 15) -> socket.socket:
    if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(socket, "BTPROTO_RFCOMM"):
        raise RuntimeError("Python/kernel lacks Bluetooth RFCOMM socket support")
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(timeout)
    try:
        sock.connect((mac, channel))
    except Exception:
        sock.close()
        raise
    return sock
