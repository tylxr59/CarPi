"""Reversible, development-only Pi 4 ConfigFS NCM gadget (W1)."""

from __future__ import annotations

import os
import re
import secrets
import struct
import time
from dataclasses import dataclass
from pathlib import Path

GADGET_NAME = "carpi"
DEV_VID = 0x1D6B  # Linux Foundation composite gadget example ID, for local testing only
DEV_PID = 0x0104


@dataclass(frozen=True)
class ControlRequest:
    request_type: int
    request: int
    value: int
    index: int
    length: int

    @classmethod
    def parse(cls, data: bytes) -> ControlRequest:
        if len(data) != 8:
            raise ValueError("USB SETUP packet must be exactly eight bytes")
        return cls(*struct.unpack("<BBHHH", data))

    def summary(self) -> str:
        return (
            f"bmRequestType=0x{self.request_type:02x} bRequest=0x{self.request:02x} "
            f"wValue=0x{self.value:04x} wIndex=0x{self.index:04x} wLength={self.length}"
        )


@dataclass(frozen=True)
class GadgetPlan:
    vendor: int = DEV_VID
    product: int = DEV_PID
    manufacturer: str = "carpi development"
    name: str = "carpi NCM test gadget"
    configuration: str = "NCM development"

    def validate(self) -> None:
        if (self.vendor, self.product) != (DEV_VID, DEV_PID):
            raise ValueError("only the non-Apple development identity is supported")
        if self.name != "carpi NCM test gadget" or self.manufacturer != "carpi development":
            raise ValueError(
                "development gadget identity must remain recognizable for safe teardown"
            )
        for value in (self.manufacturer, self.name, self.configuration):
            if not value or len(value.encode()) > 126 or any(ord(c) < 32 for c in value):
                raise ValueError("invalid USB string")


def descriptors(data: bytes) -> list[dict[str, int]]:
    """Parse a raw descriptor sequence without trusting peer-provided lengths."""
    found = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 2 or data[offset] < 2 or offset + data[offset] > len(data):
            raise ValueError("malformed USB descriptor length")
        found.append({"offset": offset, "length": data[offset], "type": data[offset + 1]})
        offset += data[offset]
    return found


def local_mac() -> str:
    value = bytearray(secrets.token_bytes(6))
    value[0] = (value[0] | 2) & 0xFE
    return ":".join(f"{x:02x}" for x in value)


class UsbGadget:
    def __init__(
        self, sys_root: Path = Path("/sys"), model_file: Path = Path("/proc/device-tree/model")
    ):
        self.sys = sys_root
        self.model_file = model_file
        self.base = sys_root / "kernel/config/usb_gadget"
        self.gadget = self.base / GADGET_NAME
        self.udc_dir = sys_root / "class/udc"

    def model(self) -> str:
        try:
            return self.model_file.read_bytes().rstrip(b"\0").decode(errors="replace")
        except OSError:
            return "unknown"

    def udcs(self) -> list[Path]:
        return sorted(self.udc_dir.iterdir()) if self.udc_dir.is_dir() else []

    def _read(self, path: Path) -> str:
        try:
            return path.read_text().strip()
        except OSError:
            return "unavailable"

    def doctor(self) -> dict[str, str]:
        udcs = self.udcs()
        controller = ", ".join(
            f"{p.name} ({self._read(p / 'device/driver/module/uevent')[:80]})" for p in udcs
        )
        return {
            "model": self.model(),
            "UDC": ", ".join(p.name for p in udcs) or "absent",
            "controller": controller or "unknown",
            "dwc2": "present" if (self.sys / "bus/platform/drivers/dwc2").exists() else "absent",
            "ConfigFS": "mounted" if self.base.is_dir() else "absent/not mounted",
            "FunctionFS": self._kernel_feature("USB_F_FS"),
            "NCM": self._kernel_feature("USB_CONFIGFS_NCM"),
            "usbmon": "present"
            if (self.sys / "kernel/debug/usb/usbmon").exists()
            else "absent/not mounted",
            "USB role": ", ".join(
                self._read(p) for p in (self.sys / "class/usb_role").glob("*/role")
            )
            or "unknown",
            "active gadget": self._read(self.gadget / "UDC") if self.gadget.exists() else "none",
            "power": "cannot be determined from software; confirm separate power before setup",
        }

    def _kernel_feature(self, name: str) -> str:
        for candidate in (Path("/proc/config.gz"), Path(f"/boot/config-{os.uname().release}")):
            try:
                if candidate.suffix == ".gz":
                    import gzip

                    content = gzip.open(candidate, "rt").read()
                else:
                    content = candidate.read_text()
                match = re.search(rf"^CONFIG_{name}=([ym])$", content, re.MULTILINE)
                return match.group(1) if match else "not configured"
            except OSError:
                pass
        return "unknown (kernel config unavailable)"

    def _write(self, path: Path, value: str) -> None:
        path.write_text(value)

    def _rmdir(self, path: Path) -> None:
        path.rmdir()

    def setup(self, *, power_confirmed: bool = False, plan: GadgetPlan | None = None) -> None:
        plan = plan or GadgetPlan()
        plan.validate()
        if "Raspberry Pi 4" not in self.model():
            raise RuntimeError("USB setup requires confirmed Raspberry Pi 4 hardware")
        if not power_confirmed:
            raise RuntimeError("confirm independent Pi power with --separate-power")
        if not self.base.is_dir():
            raise RuntimeError("ConfigFS USB gadget unavailable; mount configfs/load libcomposite")
        udcs = self.udcs()
        if len(udcs) != 1:
            raise RuntimeError(f"expected one OTG UDC, found {len(udcs)}; check dwc2/USB role")
        udc = udcs[0]
        if "dwc2" not in udc.name.lower() and "fe980000.usb" not in udc.name.lower():
            raise RuntimeError(f"UDC {udc.name} is not the expected Pi 4 USB-C controller")
        if self.gadget.exists():
            raise RuntimeError("carpi gadget already exists; use status or teardown")
        for existing in self.base.iterdir():
            try:
                active = (existing / "UDC").read_text().strip()
            except OSError:
                active = ""
            if active == udc.name:
                raise RuntimeError(f"UDC already bound by {existing.name}")
        try:
            self.gadget.mkdir()
            for name, value in {
                "idVendor": f"0x{plan.vendor:04x}",
                "idProduct": f"0x{plan.product:04x}",
                "bcdDevice": "0x0100",
                "bcdUSB": "0x0200",
                "bDeviceClass": "0x00",
            }.items():
                self._write(self.gadget / name, value)
            strings = self.gadget / "strings/0x409"
            strings.parent.mkdir(exist_ok=True)
            strings.mkdir()
            self._write(strings / "manufacturer", plan.manufacturer)
            self._write(strings / "product", plan.name)
            function = self.gadget / "functions/ncm.usb0"
            function.parent.mkdir(exist_ok=True)
            try:
                function.mkdir()
            except OSError as error:
                raise RuntimeError("NCM gadget function unavailable in this kernel") from error
            device_mac = local_mac()
            host_mac = local_mac()
            while host_mac == device_mac:
                host_mac = local_mac()
            self._write(function / "dev_addr", device_mac)
            self._write(function / "host_addr", host_mac)
            config = self.gadget / "configs/c.1"
            config.parent.mkdir(exist_ok=True)
            config.mkdir()
            self._write(config / "bmAttributes", "0xc0")  # self-powered
            self._write(config / "MaxPower", "2")
            config_strings = config / "strings/0x409"
            config_strings.parent.mkdir(exist_ok=True)
            config_strings.mkdir()
            self._write(config_strings / "configuration", plan.configuration)
            (config / "ncm.usb0").symlink_to(function)
            self._write(self.gadget / "UDC", udc.name)  # bind last
        except Exception:
            try:
                self.teardown(force_owned=True)
            except OSError:
                pass
            raise

    def teardown(self, *, force_owned: bool = False) -> None:
        if not self.gadget.exists():
            return
        if not force_owned:
            try:
                identity = (
                    int(self._read(self.gadget / "idVendor"), 0),
                    int(self._read(self.gadget / "idProduct"), 0),
                    self._read(self.gadget / "strings/0x409/product"),
                )
            except ValueError as error:
                raise RuntimeError("refusing to remove unrecognized carpi gadget") from error
            if identity != (DEV_VID, DEV_PID, "carpi NCM test gadget"):
                raise RuntimeError("refusing to remove unrecognized carpi gadget")
        udc = self.gadget / "UDC"
        if udc.exists():
            self._write(udc, "")
        link = self.gadget / "configs/c.1/ncm.usb0"
        if link.is_symlink():
            link.unlink()
        for relative in (
            "configs/c.1/strings/0x409",
            "configs/c.1",
            "functions/ncm.usb0",
            "strings/0x409",
        ):
            path = self.gadget / relative
            if path.exists():
                self._rmdir(path)
        self._rmdir(self.gadget)

    def status(self) -> dict[str, str]:
        if not self.gadget.exists():
            return {"gadget": "absent"}
        keys = ("idVendor", "idProduct", "bcdUSB", "bDeviceClass", "UDC")
        result = {key: self._read(self.gadget / key) for key in keys}
        for key in ("manufacturer", "product", "serialnumber"):
            result[f"string.{key}"] = self._read(self.gadget / "strings/0x409" / key)
        if result["string.serialnumber"] not in ("", "unavailable"):
            result["string.serialnumber"] = "[REDACTED]"
        for key in ("bmAttributes", "MaxPower"):
            result[f"config.{key}"] = self._read(self.gadget / "configs/c.1" / key)
        function = self.gadget / "functions/ncm.usb0"
        result.update(
            {
                f"ncm.{key}": self._read(function / key)
                for key in ("ifname", "dev_addr", "host_addr")
            }
        )
        udc_name = result["UDC"]
        if udc_name and udc_name != "unavailable":
            result["UDC state"] = self._read(self.udc_dir / udc_name / "state")
        result["interfaces"] = (
            "NCM control + NCM data (kernel-assigned; confirm exact descriptors with host lsusb -v)"
        )
        return result

    def net_status(self) -> dict[str, str]:
        function = self.gadget / "functions/ncm.usb0"
        if not function.exists():
            return {"NCM": "inactive"}
        name = self._read(function / "ifname")
        if name == "unavailable" or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", name):
            return {"NCM": "function exists; network interface unavailable"}
        net = self.sys / "class/net" / name
        return {
            "interface": name,
            "carrier": self._read(net / "carrier"),
            "MAC": self._read(net / "address"),
            "NCM": self._read(self.udc_dir / self._read(self.gadget / "UDC") / "state"),
        }

    def trace(self) -> None:
        print("[usb] watching UDC and NCM state; Ctrl+C to stop", flush=True)
        print(
            "[usb] SETUP contents require host-side usbmon capture or a future EP0-capable gadget",
            flush=True,
        )
        previous: dict[str, str] = {}
        while True:
            status = self.status()
            network = self.net_status()
            current = {
                "UDC": status.get("UDC", "absent"),
                "UDC state": status.get("UDC state", "not attached"),
                "NCM": network.get("NCM", "inactive"),
                "carrier": network.get("carrier", "unknown"),
            }
            for key, value in current.items():
                if previous.get(key) != value:
                    print(f"[usb] {key}: {value}", flush=True)
                    if key == "UDC state" and value == "configured":
                        print(
                            "[usb] host selected a configuration "
                            "(number unavailable in ConfigFS status)",
                            flush=True,
                        )
                    if key == "UDC state" and value == "not attached" and previous:
                        print("[usb] disconnected", flush=True)
            previous = current
            time.sleep(0.25)
