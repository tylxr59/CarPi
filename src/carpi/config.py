"""Strict, side effect free TOML configuration."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

MAC = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z")


@dataclass(frozen=True)
class Config:
    vehicle_name: str = "Subaru Crosstrek"
    bluetooth_mac: str = ""
    log_level: str = "info"
    packet_capture: bool = False
    width: int = 0
    height: int = 0
    fps: int = 30
    codec: str = "h264"
    store_wifi_credentials: bool = False
    log_payloads: bool = False


def _table(root: dict, key: str, allowed: set[str]) -> dict:
    value = root.get(key, {})
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"invalid [{key}] table or unknown key")
    return value


def load(path: Path | None) -> Config:
    if path is None:
        return Config()
    with path.open("rb") as file:
        root = tomllib.load(file)
    if set(root) - {"vehicle", "logging", "video", "privacy"}:
        raise ValueError("unknown configuration table")
    vehicle = _table(root, "vehicle", {"name", "bluetooth_mac"})
    logging = _table(root, "logging", {"level", "packet_capture"})
    video = _table(root, "video", {"width", "height", "fps", "codec"})
    privacy = _table(root, "privacy", {"store_wifi_credentials", "log_payloads"})
    config = Config(
        vehicle.get("name", "Subaru Crosstrek"),
        vehicle.get("bluetooth_mac", ""),
        logging.get("level", "info"),
        logging.get("packet_capture", False),
        video.get("width", 0),
        video.get("height", 0),
        video.get("fps", 30),
        video.get("codec", "h264"),
        privacy.get("store_wifi_credentials", False),
        privacy.get("log_payloads", False),
    )
    if not isinstance(config.vehicle_name, str) or not isinstance(config.bluetooth_mac, str):
        raise ValueError("vehicle name/MAC must be strings")
    if config.bluetooth_mac and not MAC.fullmatch(config.bluetooth_mac):
        raise ValueError("invalid Bluetooth MAC")
    if config.log_level not in {"debug", "info", "warning"} or config.codec != "h264":
        raise ValueError("unsupported log level or codec")
    if any(type(v) is not int for v in (config.width, config.height, config.fps)):
        raise ValueError("video dimensions and FPS must be integers")
    if min(config.width, config.height) < 0 or not 1 <= config.fps <= 120:
        raise ValueError("invalid video dimensions or FPS")
    if (config.width == 0) != (config.height == 0):
        raise ValueError("both dimensions must be zero or both nonzero")
    if any(
        type(v) is not bool
        for v in (config.packet_capture, config.store_wifi_credentials, config.log_payloads)
    ):
        raise ValueError("privacy and capture options must be booleans")
    return config
