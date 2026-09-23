"""Synthetic packets written for this project; no captured vehicle bytes."""

import unittest

from carpi.iap2 import (
    ACK,
    SYN,
    TLV,
    LinkParameters,
    Message,
    MessageStream,
    Packet,
    PacketStream,
    ProtocolError,
    Session,
    checksum,
    parse_tlvs,
    summary,
)


class FramingTests(unittest.TestCase):
    def test_checksum(self):
        self.assertEqual(sum(b"abc" + bytes([checksum(b"abc")])) & 255, 0)

    def test_packet_roundtrip_and_fragmentation(self):
        original = Packet(SYN | ACK, 254, 7, 1, b"hello")
        wire = original.encode()
        stream = PacketStream()
        self.assertEqual(stream.feed(wire[:4]), [])
        self.assertEqual(
            stream.feed(wire[4:] + Packet(ACK, 2, 254, 0).encode()),
            [original, Packet(ACK, 2, 254, 0)],
        )

    def test_bad_header_and_payload_checksums(self):
        wire = bytearray(Packet(ACK, 1, 0, 1, b"hi").encode())
        wire[8] ^= 1
        with self.assertRaisesRegex(ProtocolError, "header checksum"):
            Packet.decode(bytes(wire))
        wire[8] ^= 1
        wire[-1] ^= 1
        with self.assertRaisesRegex(ProtocolError, "payload checksum"):
            Packet.decode(bytes(wire))

    def test_lengths_and_truncation(self):
        wire = Packet(ACK, 1, 0, 1, b"hi").encode()
        with self.assertRaises(ProtocolError):
            Packet.decode(wire[:-1])
        stream = PacketStream()
        self.assertEqual(stream.feed(wire[:-1]), [])
        self.assertEqual(stream.feed(wire[-1:]), [Packet(ACK, 1, 0, 1, b"hi")])
        with self.assertRaises(ProtocolError):
            PacketStream().feed(b"\xff\x5a\xff\xff" + b"\x00" * 5)

    def test_syn_parameters(self):
        params = LinkParameters(8, 4096, 2000, 500, 3, 1, (Session(1, 0, 1),))
        self.assertEqual(LinkParameters.decode(params.encode()), params)
        self.assertEqual(params.control_session(), 1)
        with self.assertRaises(ProtocolError):
            LinkParameters.decode(params.encode()[:-1])

    def test_tlv_and_csm(self):
        message = Message(0x1D01, (TLV(0, b"Test IVI\0"), TLV(24, b"\x01")))
        wire = message.encode()
        self.assertEqual(Message.decode(wire), message)
        stream = MessageStream()
        self.assertEqual(stream.feed(wire[:5]), [])
        self.assertEqual(stream.feed(wire[5:]), [message])
        self.assertEqual(summary(message)["name"], "Test IVI")
        with self.assertRaises(ProtocolError):
            parse_tlvs(b"\x00\x00\x00\x01")
        with self.assertRaises(ProtocolError):
            Message.decode(wire[:-1])

    def test_redaction(self):
        # 0x5703 uses TLV 1 for SSID and TLV 2 for passphrase.
        message = Message(0x5703, (TLV(1, b"car-test\0"), TLV(2, b"secret-value\0")))
        text = str(summary(message))
        self.assertIn("car-test", text)
        self.assertNotIn("secret-value", text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
