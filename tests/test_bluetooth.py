"""Synthetic SDP service records, not copied from a vehicle."""

import unittest
from unittest.mock import MagicMock, patch

from carpi.bluetooth import (
    IAP_UUID,
    AdapterInfo,
    BluetoothSession,
    BlueZ,
    parse_sdp,
    select_channel,
)


class FakeBlueZ:
    def __init__(self, *, fail_register=False, fail_property=None, initial=(False, False, False)):
        self.fail_register = fail_register
        self.fail_property = fail_property
        self.values = dict(zip(("Powered", "Pairable", "Discoverable"), initial, strict=True))
        self.events = []

    def inspect(self):
        self.events.append("inspect")
        return AdapterInfo("/org/bluez/hci0", "AA:BB:CC:DD:EE:FF", *self.values.values(), ())

    def register_profile(self):
        self.events.append("register")
        if self.fail_register:
            raise RuntimeError("register denied")

    def unregister_profile(self):
        self.events.append("unregister")

    def set_property(self, name, value):
        self.events.append((name, value))
        if self.fail_property == name and value:
            raise RuntimeError("property denied")
        self.values[name] = value

    def close(self):
        self.events.append("close")


class LifecycleTests(unittest.TestCase):
    def test_bluez_register_uses_vendor_uuid_and_server_role(self):
        backend = BlueZ.__new__(BlueZ)
        backend.dbus = MagicMock()
        backend.dbus.ObjectPath.side_effect = lambda value: value
        backend.dbus.String.side_effect = lambda value: value
        backend.dbus.Boolean.side_effect = lambda value: value
        backend.bus = MagicMock()
        backend.loop = MagicMock()
        backend.manager = MagicMock()
        backend.profile = None
        backend.thread = None
        backend.registered = False
        backend.profile_manager_available = True
        with (
            patch("carpi.bluetooth._profile_class", return_value=lambda bus, path: MagicMock()),
            patch("carpi.bluetooth.threading.Thread") as thread,
        ):
            backend.register_profile()
            thread.return_value.start.assert_called_once()
            path, uuid, options = backend.manager.RegisterProfile.call_args.args
            self.assertEqual(uuid, IAP_UUID)
            self.assertEqual(options["Role"], "server")
            self.assertTrue(options["RequireAuthentication"])
            self.assertEqual(path, "/org/carpi/iap2")
            backend.unregister_profile()
            backend.manager.UnregisterProfile.assert_called_once_with(path)

    def test_bluez_registration_error_removes_exported_object(self):
        backend = BlueZ.__new__(BlueZ)
        backend.dbus = MagicMock()
        backend.dbus.ObjectPath.side_effect = lambda value: value
        backend.bus = MagicMock()
        backend.loop = MagicMock()
        backend.manager = MagicMock()
        backend.manager.RegisterProfile.side_effect = RuntimeError("denied")
        backend.profile = None
        backend.thread = None
        backend.registered = False
        backend.profile_manager_available = True
        profile = MagicMock()
        with (
            patch("carpi.bluetooth._profile_class", return_value=lambda bus, path: profile),
            patch("carpi.bluetooth.threading.Thread"),
        ):
            with self.assertRaisesRegex(RuntimeError, "denied"):
                backend.register_profile()
        profile.remove_from_connection.assert_called_once()
        backend.bus.close.assert_not_called()

    def test_register_unregister_and_restore(self):
        backend = FakeBlueZ(initial=(True, False, False))
        with BluetoothSession(backend):
            self.assertEqual(backend.values, dict(Powered=True, Pairable=True, Discoverable=True))
        self.assertEqual(backend.values, dict(Powered=True, Pairable=False, Discoverable=False))
        self.assertEqual(
            backend.events,
            [
                "inspect",
                "register",
                ("Pairable", True),
                ("Discoverable", True),
                "unregister",
                ("Discoverable", False),
                ("Pairable", False),
                "close",
            ],
        )

    def test_registration_failure_closes_without_state_change(self):
        backend = FakeBlueZ(fail_register=True)
        with self.assertRaisesRegex(RuntimeError, "register denied"):
            with BluetoothSession(backend):
                pass
        self.assertEqual(backend.values, dict(Powered=False, Pairable=False, Discoverable=False))
        self.assertEqual(
            backend.events,
            ["inspect", ("Powered", True), "register", "unregister", ("Powered", False), "close"],
        )

    def test_exception_and_ctrl_c_restore(self):
        for exception in (RuntimeError("probe failed"), KeyboardInterrupt()):
            backend = FakeBlueZ()
            with self.assertRaises(type(exception)):
                with BluetoothSession(backend):
                    raise exception
            self.assertEqual(
                backend.values, dict(Powered=False, Pairable=False, Discoverable=False)
            )
            self.assertIn("unregister", backend.events)
            self.assertEqual(backend.events[-1], "close")

    def test_partial_setup_restores_prior_values(self):
        backend = FakeBlueZ(fail_property="Discoverable")
        with self.assertRaisesRegex(RuntimeError, "property denied"):
            with BluetoothSession(backend):
                pass
        self.assertEqual(backend.values, dict(Powered=False, Pairable=False, Discoverable=False))
        self.assertIn(("Pairable", False), backend.events)


class SDPTests(unittest.TestCase):
    def test_select_named_iap_service(self):
        output = """Service RecHandle: 0x10001
Service Name: Handsfree
  Channel: 2
Service RecHandle: 0x10002
Service Name: Wireless iAP2
  Channel: 4
"""
        self.assertEqual(select_channel(parse_sdp(output)), 4)

    def test_select_uuid_service(self):
        output = """Service RecHandle: 0x10002
  UUID 128: 00000000-deca-fade-deca-deafdecacafe
  Channel: 3
"""
        self.assertEqual(select_channel(parse_sdp(output)), 3)

    def test_ambiguous_requires_override(self):
        with self.assertRaises(RuntimeError):
            select_channel([(2, "iAP"), (3, "iAP2")])


if __name__ == "__main__":
    unittest.main()
