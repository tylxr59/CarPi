"""Hardware-free state, config and renderer checks."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from carpi.config import Config, load
from carpi.iap2 import (
    ACK,
    MARKER,
    SYN,
    TLV,
    LinkParameters,
    Message,
    Packet,
    ProtocolError,
    Session,
)
from carpi.probe import Authentication, Probe, State
from carpi.transport import SocketTransport
from carpi.video import frame


class FakeSocket:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.sent = []

    def settimeout(self, _timeout):
        pass

    def recv(self, _size):
        return self.chunks.pop(0) if self.chunks else b""

    def sendall(self, payload):
        self.sent.append(payload)


class BasicTests(unittest.TestCase):
    def test_default_config_and_rejection(self):
        self.assertEqual(load(None), Config())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.toml"
            path.write_text("[privacy]\nstore_wifi_credentials = 'yes'\n")
            with self.assertRaises(ValueError):
                load(path)
            path.write_text("[vehicle]\nbluetooth_mac = 'AA:BB:CC:DD:EE:FF'\n")
            self.assertEqual(load(path).bluetooth_mac, "AA:BB:CC:DD:EE:FF")

    def test_state_machine(self):
        probe = Probe(FakeSocket())
        probe.transition(State.MARKER)
        probe.transition(State.NEGOTIATING)
        with self.assertRaises(ProtocolError):
            probe.transition(State.AUTH_UNVERIFIED)

    def test_sequence_ack_and_rejection(self):
        first = Packet(ACK, 255, 0, 1, b"a").encode()
        second = Packet(ACK, 0, 0, 1, b"b").encode()
        socket = FakeSocket((first + second,))
        probe = Probe(socket)
        self.assertEqual(probe.receive().payload, b"a")
        self.assertEqual(probe.receive().payload, b"b")
        self.assertEqual(probe.peer_seq, 0)
        self.assertEqual(len(socket.sent), 2)  # one acknowledgment per data packet
        bad = Probe(FakeSocket((first + Packet(ACK, 2, 0, 1, b"b").encode(),)))
        bad.receive()
        with self.assertRaisesRegex(ProtocolError, "out-of-order"):
            bad.receive()

    def test_synthetic_phone_probe_stops_before_auth_success(self):
        # Entire exchange is synthetic and documents the expected client-side order.
        params = LinkParameters(8, 4096, 2000, 500, 3, 1, (Session(1, 0, 1),))
        messages = (
            Message(0x1D01, (TLV(0, b"Test IVI\0"),)),
            Message(0xAA01, (TLV(0, b"certificate"),)),
            Message(0xAA03, (TLV(0, b"signature"),)),
        )
        chunks = [
            MARKER,
            Packet(SYN, 0, 0, 0, params.encode()).encode(),
            Packet(ACK, 0, 0, 0).encode(),
        ]
        chunks += [
            Packet(ACK, seq, 0, 1, msg.encode()).encode()
            for seq, msg in enumerate(messages, start=1)
        ]
        sock = FakeSocket(chunks)
        probe = Probe(SocketTransport(sock))
        self.assertEqual(probe.run(), State.AUTH_UNVERIFIED)
        self.assertEqual(probe.authentication, Authentication.UNVERIFIED_STOPPED)
        sent_ids = []
        for wire in sock.sent[1:]:
            packet = Packet.decode(wire)
            if packet.session == 1 and packet.payload:
                sent_ids.append(Message.decode(packet.payload).identifier)
        self.assertEqual(sent_ids, [0x1D00, 0x1D02, 0xAA00, 0xAA02])
        self.assertNotIn(0xAA05, sent_ids)

    def test_explicit_unverified_auth_requests_wifi_and_redacts_password(self):
        params = LinkParameters(8, 4096, 2000, 500, 3, 1, (Session(1, 0, 1),))
        messages = (
            Message(0x1D01, (TLV(0, b"Test IVI\0"),)),
            Message(0xAA01, (TLV(0, b"certificate"),)),
            Message(0xAA03, (TLV(0, b"signature"),)),
            Message(0x5703, (TLV(1, b"Subaru-Test\0"), TLV(2, b"secret-password\0"))),
        )
        chunks = [
            MARKER,
            Packet(SYN, 0, 0, 0, params.encode()).encode(),
            Packet(ACK, 0, 0, 0).encode(),
        ]
        chunks += [
            Packet(ACK, seq, 0, 1, msg.encode()).encode()
            for seq, msg in enumerate(messages, start=1)
        ]
        sock = FakeSocket(chunks)
        probe = Probe(SocketTransport(sock), allow_unverified_accessory=True)
        with self.assertLogs("carpi", level="INFO") as logs:
            self.assertEqual(probe.run(), State.WIFI_RECEIVED)
        self.assertEqual(probe.authentication, Authentication.UNVERIFIED_ACCEPTED)
        self.assertTrue(probe.wifi_received)
        self.assertEqual(probe.wifi_ssid, "Subaru-Test")
        self.assertNotIn("secret-password", "\n".join(logs.output))
        self.assertIn("[REDACTED]", "\n".join(logs.output))
        sent_ids = [
            Message.decode(Packet.decode(wire).payload).identifier
            for wire in sock.sent[1:]
            if Packet.decode(wire).payload and Packet.decode(wire).session == 1
        ]
        self.assertEqual(sent_ids[-2:], [0xAA05, 0x5702])

    def test_unverified_state_is_distinct_from_verified(self):
        probe = Probe(FakeSocket())
        self.assertFalse(probe.allow_unverified_accessory)
        self.assertEqual(probe.authentication, Authentication.NOT_REACHED)
        self.assertNotEqual(Authentication.UNVERIFIED_ACCEPTED, Authentication.VERIFIED)

    def test_wifi_configuration_requires_one_ssid(self):
        probe = Probe(FakeSocket())
        with self.assertRaisesRegex(ProtocolError, "SSID"):
            probe.observe_wifi(Message(0x5703, (TLV(2, b"secret"),)))
        with self.assertRaisesRegex(ProtocolError, "duplicate"):
            probe.observe_wifi(Message(0x5703, (TLV(1, b"one"), TLV(1, b"two"))))
        self.assertFalse(probe.wifi_received)

    def test_generated_frame_changes_with_counter(self):
        now = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC)
        first = frame(320, 240, 1, now)
        second = frame(320, 240, 2, now)
        self.assertEqual(len(first), 320 * 240 * 3)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
