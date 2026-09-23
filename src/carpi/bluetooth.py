"""BlueZ discovery and Linux RFCOMM client transport."""

from __future__ import annotations

import logging
import re
import shutil
import socket
import subprocess
import threading
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

IAP_UUID = "00000000-deca-fade-deca-deafdecacafe"
PROFILE_PATH = "/org/carpi/iap2"
LOG = logging.getLogger("carpi")


def _dbus_modules() -> tuple[Any, Any, Any]:
    try:
        import dbus
        import dbus.service
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
    except ImportError as error:
        raise RuntimeError("install python3-dbus and python3-gi for BlueZ D-Bus") from error
    return dbus, DBusGMainLoop, GLib


def _profile_class(dbus: Any) -> type:
    class IapProfile(dbus.service.Object):
        @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
        def Release(self) -> None:
            LOG.warning("[bt] BlueZ released local iAP2 profile")

        @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
        def NewConnection(self, device: str, fd: Any, properties: Any) -> None:
            # The probe initiates its own RFCOMM socket; incoming streams are unsupported.
            LOG.warning("[bt] unsolicited incoming iAP2 connection; rejecting")
            raise dbus.DBusException(
                "incoming iAP2 transport is unsupported",
                name="org.bluez.Error.Rejected",
            )

        @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
        def RequestDisconnection(self, device: str) -> None:
            LOG.debug("[bt] BlueZ requested profile disconnection")

    return IapProfile


@dataclass(frozen=True)
class AdapterInfo:
    path: str
    address: str
    powered: bool
    pairable: bool
    discoverable: bool
    uuids: tuple[str, ...]


class BlueZ:
    """Own the D-Bus connection, adapter and exported Profile1 object."""

    def __init__(self) -> None:
        dbus, main_loop_type, glib = _dbus_modules()
        main_loop_type(set_as_default=True)
        self.dbus = dbus
        self.bus = dbus.SystemBus(private=True)
        self.loop = glib.MainLoop()
        self.thread: threading.Thread | None = None
        self.profile: Any = None
        self.registered = False
        self._closed = False
        try:
            manager = self.bus.get_object("org.bluez", "/org/bluez")
            self.manager = dbus.Interface(manager, "org.bluez.ProfileManager1")
            xml = dbus.Interface(manager, "org.freedesktop.DBus.Introspectable").Introspect()
            self.profile_manager_available = 'name="org.bluez.ProfileManager1"' in str(xml)
            objects = dbus.Interface(
                self.bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager"
            ).GetManagedObjects()
            paths = sorted(
                path for path, interfaces in objects.items() if "org.bluez.Adapter1" in interfaces
            )
            if not paths:
                raise RuntimeError("no BlueZ Bluetooth adapter found")
            self.path = str(paths[0])
            obj = self.bus.get_object("org.bluez", self.path)
            self.properties = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
            LOG.info("[bt] adapter %s found", self.path.rsplit("/", 1)[-1])
        except BaseException:
            self.bus.close()
            raise

    def inspect(self) -> AdapterInfo:
        values = self.properties.GetAll("org.bluez.Adapter1")
        return AdapterInfo(
            self.path,
            str(values.get("Address", "")),
            bool(values.get("Powered", False)),
            bool(values.get("Pairable", False)),
            bool(values.get("Discoverable", False)),
            tuple(str(uuid) for uuid in values.get("UUIDs", ())),
        )

    def set_property(self, name: str, value: bool) -> None:
        LOG.debug("[bt] D-Bus Set Adapter1.%s=%s on %s", name, value, self.path)
        self.properties.Set("org.bluez.Adapter1", name, self.dbus.Boolean(value))

    def register_profile(self) -> None:
        if self.registered:
            return
        if not self.profile_manager_available:
            raise RuntimeError("BlueZ ProfileManager1 is unavailable")
        LOG.info("[bt] registering local iAP2 profile")
        self.profile = _profile_class(self.dbus)(self.bus, PROFILE_PATH)
        self.thread = threading.Thread(target=self.loop.run, daemon=True, name="carpi-bluez")
        self.thread.start()
        try:
            options = {
                "Name": self.dbus.String("CarPi iAP2 research"),
                "Role": self.dbus.String("server"),
                "RequireAuthentication": self.dbus.Boolean(True),
                "RequireAuthorization": self.dbus.Boolean(False),
            }
            LOG.debug("[bt] D-Bus RegisterProfile path=%s uuid=%s", PROFILE_PATH, IAP_UUID)
            self.manager.RegisterProfile(self.dbus.ObjectPath(PROFILE_PATH), IAP_UUID, options)
            self.registered = True
            LOG.info("[bt] iAP2 profile registered")
        except BaseException:
            try:
                self.unregister_profile()
            except Exception as error:
                LOG.error("[bt] profile registration cleanup failed: %s", error)
            raise

    def unregister_profile(self) -> None:
        try:
            if self.registered:
                LOG.info("[bt] unregistering iAP2 profile")
                LOG.debug("[bt] D-Bus UnregisterProfile path=%s", PROFILE_PATH)
                self.manager.UnregisterProfile(self.dbus.ObjectPath(PROFILE_PATH))
        finally:
            self.registered = False
            if self.profile is not None:
                self.profile.remove_from_connection()
                self.profile = None

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        try:
            self.unregister_profile()
        finally:
            self.loop.quit()
            if self.thread is not None:
                self.thread.join(timeout=2)
                self.thread = None
            self.bus.close()


class BluetoothSession(AbstractContextManager["BluetoothSession"]):
    """Register the local service and restore only adapter values CarPi changed."""

    def __init__(self, backend: Any | None = None) -> None:
        self.backend = backend
        self.changes: list[tuple[str, bool]] = []

    def __enter__(self) -> BluetoothSession:
        if self.backend is None:
            self.backend = BlueZ()
        try:
            before = self.backend.inspect()
            if not before.powered:
                self.changes.append(("Powered", before.powered))
                self.backend.set_property("Powered", True)
            self.backend.register_profile()
            for name, previous in (
                ("Pairable", before.pairable),
                ("Discoverable", before.discoverable),
            ):
                if not previous:
                    self.changes.append((name, previous))
                    self.backend.set_property(name, True)
            return self
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        errors = []
        try:
            self.backend.unregister_profile()
        except Exception as error:
            errors.append(error)
            LOG.error("[bt] profile unregister failed: %s", error)
        for name, previous in reversed(self.changes):
            try:
                self.backend.set_property(name, previous)
            except Exception as error:
                errors.append(error)
                LOG.error("[bt] failed to restore %s: %s", name, error)
        self.changes.clear()
        try:
            self.backend.close()
        except Exception as error:
            errors.append(error)
            LOG.error("[bt] D-Bus close failed: %s", error)
        if not errors:
            LOG.info("[bt] adapter state restored")
        if errors and exc_type is None:
            raise RuntimeError(f"Bluetooth cleanup failed: {errors[0]}") from errors[0]

    def channel(self, target: str, override: int | None = None) -> int:
        if override is not None:
            return override
        LOG.info("[bt] searching for RFCOMM service")
        return select_channel(sdp_channels(target))

    def connect(self, target: str, channel: int) -> socket.socket:
        LOG.info("[bt] RFCOMM channel %d", channel)
        LOG.info("[bt] connecting")
        sock = connect(target, channel)
        LOG.info("[bt] connected")
        return sock


def doctor() -> dict[str, str]:
    """Inspect without registering a profile or changing the adapter."""
    result = {
        "BlueZ version": "unavailable",
        "Adapter": "unavailable",
        "ProfileManager1": "unavailable",
        "iAP2 registration": "not attempted (read-only doctor)",
        "rfkill": "unavailable",
    }
    if shutil.which("bluetoothctl"):
        process = subprocess.run(["bluetoothctl", "--version"], capture_output=True, text=True)
        result["BlueZ version"] = process.stdout.strip() or process.stderr.strip()
    if shutil.which("rfkill"):
        process = subprocess.run(["rfkill", "list", "bluetooth"], capture_output=True, text=True)
        result["rfkill"] = " ".join(process.stdout.split()) or process.stderr.strip()
    try:
        backend = BlueZ()
        try:
            info = backend.inspect()
            result.update(
                {
                    "Adapter": info.path,
                    "Adapter MAC": "[REDACTED]" if info.address else "unavailable",
                    "Powered": str(info.powered),
                    "Pairable": str(info.pairable),
                    "Discoverable": str(info.discoverable),
                    "Available UUIDs": ", ".join(info.uuids) or "(none)",
                    "Local iAP2 UUID": (
                        "present" if IAP_UUID in {uuid.lower() for uuid in info.uuids} else "absent"
                    ),
                    "ProfileManager1": "available"
                    if backend.profile_manager_available
                    else "missing",
                    "iAP2 registration": (
                        "API available; run probe to test registration"
                        if backend.profile_manager_available
                        else "unavailable"
                    ),
                }
            )
        finally:
            backend.close()
    except Exception as error:
        result["D-Bus diagnostic error"] = str(error)
    return result


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
