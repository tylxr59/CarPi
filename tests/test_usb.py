import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from carpi.probe import Probe
from carpi.transport import EndpointTransport
from carpi.usb import ControlRequest, GadgetPlan, UsbGadget, descriptors


class FakeGadget(UsbGadget):
    def __init__(self, root: Path):
        sys_root = root / "sys"
        for relative in (
            "kernel/config/usb_gadget",
            "class/udc/fe980000.usb",
            "kernel/config/usb_gadget/carpi-do-not-touch",
        ):
            (sys_root / relative).mkdir(parents=True)
        model = root / "model"
        model.write_bytes(b"Raspberry Pi 4 Model B\0")
        super().__init__(sys_root, model)
        self.writes = []

    def _write(self, path: Path, value: str) -> None:
        self.writes.append((path, value))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def _rmdir(self, path: Path) -> None:
        # tmpfs fixture has regular files where ConfigFS exposes attributes.
        for child in path.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir() and not any(child.iterdir()):
                child.rmdir()
        path.rmdir()


class USBTests(unittest.TestCase):
    def test_descriptor_plan_and_parser(self):
        GadgetPlan().validate()
        with self.assertRaises(ValueError):
            GadgetPlan(vendor=0x05AC, product=0x12A8).validate()
        self.assertEqual(
            descriptors(b"\x02\x01\x03\x02\xff"),
            [
                {"offset": 0, "length": 2, "type": 1},
                {"offset": 2, "length": 3, "type": 2},
            ],
        )
        for malformed in (b"\0\x01", b"\x03\x01", b"\x01\x01"):
            with self.assertRaises(ValueError):
                descriptors(malformed)

    def test_setup_packet_rejects_malformed_and_summarizes_without_payload(self):
        with self.assertRaises(ValueError):
            ControlRequest.parse(b"\xc0\x52")
        request = ControlRequest.parse(b"\xc0\x52\x00\x00\x00\x00\x01\x00")
        self.assertIn("bRequest=0x52", request.summary())
        self.assertNotIn("secret", request.summary())

    def test_setup_bind_last_and_teardown_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gadget = FakeGadget(root)
            with self.assertRaises(RuntimeError):
                gadget.setup()
            gadget.setup(power_confirmed=True)
            self.assertEqual(gadget.writes[-1], (gadget.gadget / "UDC", "fe980000.usb"))
            self.assertEqual(gadget.status()["idVendor"], "0x1d6b")
            self.assertEqual(gadget.status()["config.bmAttributes"], "0xc0")
            self.assertEqual(gadget.status()["config.MaxPower"], "2")
            self.assertRegex(gadget.status()["ncm.dev_addr"], r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
            (gadget.gadget / "strings/0x409/serialnumber").write_text("private-serial")
            self.assertEqual(gadget.status()["string.serialnumber"], "[REDACTED]")
            self.assertIn("unavailable", gadget.net_status()["NCM"])
            self.assertTrue((gadget.gadget / "configs/c.1/ncm.usb0").is_symlink())
            with self.assertRaises(RuntimeError):
                gadget.setup(power_confirmed=True)
            gadget.teardown()
            gadget.teardown()
            self.assertFalse(gadget.gadget.exists())
            self.assertTrue((gadget.base / "carpi-do-not-touch").exists())

    def test_partial_write_and_disconnect(self):
        read_fd, write_fd = os.pipe()
        try:
            transport = EndpointTransport(read_fd, write_fd)
            transport.settimeout(0.1)
            os.write(write_fd, b"abc")
            self.assertEqual(transport.recv(2), b"ab")
            self.assertEqual(transport.recv(2), b"c")
            with patch("carpi.transport.os.write", side_effect=[1, 2]) as write:
                transport.sendall(b"abc")
                self.assertEqual(write.call_count, 2)
            with patch("carpi.transport.os.write", return_value=0):
                with self.assertRaises(ConnectionError):
                    transport.sendall(b"abc")
            os.close(write_fd)
            write_fd = -1
            self.assertEqual(transport.recv(2), b"")
        finally:
            os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)

    def test_disconnect_during_iap2_packet(self):
        read_fd, write_fd = os.pipe()
        try:
            transport = EndpointTransport(read_fd, read_fd)
            probe = Probe(transport, timeout=0.1, label="iap2-usb")
            os.write(write_fd, b"\xff\x5a\x00")
            os.close(write_fd)
            write_fd = -1
            with self.assertRaises(ConnectionError):
                probe.receive()
        finally:
            os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)

    def test_setup_failure_rolls_back_only_own_gadget(self):
        with tempfile.TemporaryDirectory() as directory:
            gadget = FakeGadget(Path(directory))
            original = gadget._write

            def fail_before_bind(path, value):
                if path.name == "MaxPower":
                    raise OSError("fixture failure")
                original(path, value)

            with patch.object(gadget, "_write", side_effect=fail_before_bind):
                with self.assertRaises(OSError):
                    gadget.setup(power_confirmed=True)
            self.assertFalse(gadget.gadget.exists())
            self.assertTrue((gadget.base / "carpi-do-not-touch").exists())

    def test_teardown_refuses_foreign_gadget(self):
        with tempfile.TemporaryDirectory() as directory:
            gadget = FakeGadget(Path(directory))
            gadget.gadget.mkdir()
            with self.assertRaises(RuntimeError):
                gadget.teardown()
            self.assertTrue(gadget.gadget.exists())


if __name__ == "__main__":
    unittest.main()
