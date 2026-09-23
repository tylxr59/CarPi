"""carpi command line."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from carpi import __version__, bluetooth
from carpi.config import MAC, load
from carpi.probe import Probe
from carpi.video import encode_demo, write_ppm


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="carpi")
    root.add_argument(
        "--config", type=Path, help="TOML file; default /etc/carpi/carpi.toml if present"
    )
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe", help="connect as phone/client over Bluetooth RFCOMM")
    probe.add_argument("--target", help="vehicle Bluetooth MAC")
    probe.add_argument("--channel", type=int, help="RFCOMM channel; otherwise inspect SDP")
    probe.add_argument("-v", action="count", default=0, dest="verbose")
    commands.add_parser(
        "discover", help="list BlueZ-known devices; pair separately with bluetoothctl"
    )
    commands.add_parser("daemon", help="idle service scaffold; never initiates vehicle contact")
    picture = commands.add_parser("frame", help="write local Hello World PPM image")
    picture.add_argument("--output", type=Path, required=True)
    video = commands.add_parser("video-demo", help="encode local H.264 sample; does not stream")
    video.add_argument("--output", type=Path, required=True)
    video.add_argument("--encoder", choices=["libx264", "h264_v4l2m2m"], default="libx264")
    video.add_argument("--seconds", type=int, default=3)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        default_config = Path("/etc/carpi/carpi.toml")
        config = load(args.config or (default_config if default_config.is_file() else None))
        if args.command == "daemon":
            print("[carpi] idle; run probe explicitly to contact a vehicle", flush=True)
            while True:
                time.sleep(3600)
        if args.command == "discover":
            for device in bluetooth.devices():
                print(device)
            return 0
        if args.command == "frame":
            write_ppm(args.output, config.width or 640, config.height or 360)
            print(f"[video] local frame written: {args.output}")
            return 0
        if args.command == "video-demo":
            encode_demo(
                args.output,
                config.width or 640,
                config.height or 360,
                config.fps,
                args.seconds,
                args.encoder,
            )
            print(f"[video] local H.264 stream written: {args.output}")
            return 0
        target = args.target or config.bluetooth_mac
        if not MAC.fullmatch(target):
            raise ValueError("probe requires --target MAC or [vehicle].bluetooth_mac")
        if args.channel is not None and not 1 <= args.channel <= 30:
            raise ValueError("RFCOMM channel must be 1..30")
        level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout)
        channel = args.channel or bluetooth.select_channel(bluetooth.sdp_channels(target))
        logging.info("[bt] connecting to %s channel %d", target, channel)
        with bluetooth.connect(target, channel) as sock:
            state = Probe(sock).run()
        print(
            f"[auth] stopped at {state.name.lower()}; no Wi-Fi handoff or CarPlay session claimed"
        )
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, ConnectionError) as error:
        print(f"[carpi] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
