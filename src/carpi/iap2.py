"""Bounded iAP2 link framing and small control-message subset.

Wire layout follows independently documented observations in docs/protocol-notes.md.
This is a research probe, not a complete reliable iAP2 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from struct import pack, unpack

MARKER = bytes.fromhex("ff550200ee10")
SOP = bytes.fromhex("ff5a")
SYN = 0x80
ACK = 0x40
EAK = 0x20
RST = 0x10
MAX_PACKET = 4096
MAX_CSM = 4096


class ProtocolError(ValueError):
    """Malformed or unsupported peer input."""


def checksum(data: bytes) -> int:
    return (-sum(data)) & 0xFF


@dataclass(frozen=True)
class Packet:
    control: int
    seq: int
    ack: int
    session: int
    payload: bytes = b""

    def encode(self) -> bytes:
        length = 9 + (len(self.payload) + 1 if self.payload else 0)
        if length > MAX_PACKET:
            raise ProtocolError("link packet exceeds local size limit")
        header = SOP + pack(">HBBBB", length, self.control, self.seq, self.ack, self.session)
        result = header + bytes([checksum(header)])
        if self.payload:
            result += self.payload + bytes([checksum(self.payload)])
        return result

    @classmethod
    def decode(cls, data: bytes) -> Packet:
        if len(data) < 9 or data[:2] != SOP:
            raise ProtocolError("invalid link header")
        length, control, seq, ack, session = unpack(">HBBBB", data[2:8])
        if length < 9 or length > MAX_PACKET or length != len(data):
            raise ProtocolError("invalid link length")
        if sum(data[:9]) & 0xFF:
            raise ProtocolError("bad header checksum")
        payload = b""
        if length > 9:
            if length < 11 or sum(data[9:]) & 0xFF:
                raise ProtocolError("bad payload checksum")
            payload = data[9:-1]
        return cls(control, seq, ack, session, payload)


class PacketStream:
    """Incremental framing; no resync after a malformed packet."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[Packet]:
        self.buffer.extend(chunk)
        if len(self.buffer) > MAX_PACKET * 2:
            raise ProtocolError("link input buffer exceeded")
        packets = []
        while len(self.buffer) >= 9:
            if self.buffer[:2] != SOP:
                raise ProtocolError("unexpected bytes before link header")
            length = int.from_bytes(self.buffer[2:4], "big")
            if length < 9 or length > MAX_PACKET:
                raise ProtocolError("invalid link length")
            if len(self.buffer) < length:
                break
            packets.append(Packet.decode(bytes(self.buffer[:length])))
            del self.buffer[:length]
        return packets


@dataclass(frozen=True)
class Session:
    identifier: int
    kind: int
    version: int


@dataclass(frozen=True)
class LinkParameters:
    max_outstanding: int
    max_packet: int
    retransmit_ms: int
    ack_ms: int
    max_retries: int
    max_cumulative_ack: int
    sessions: tuple[Session, ...]

    def encode(self) -> bytes:
        if not 11 <= self.max_packet <= MAX_PACKET:
            raise ProtocolError("unsupported maximum packet size")
        head = pack(
            ">BBHHHBB",
            1,
            self.max_outstanding,
            self.max_packet,
            self.retransmit_ms,
            self.ack_ms,
            self.max_retries,
            self.max_cumulative_ack,
        )
        return head + b"".join(bytes((s.identifier, s.kind, s.version)) for s in self.sessions)

    @classmethod
    def decode(cls, payload: bytes) -> LinkParameters:
        if len(payload) < 13 or (len(payload) - 10) % 3:
            raise ProtocolError("invalid SYN parameters length")
        version, outstanding, max_packet, retransmit, ack_ms, retries, cumulative = unpack(
            ">BBHHHBB", payload[:10]
        )
        if version != 1 or not 11 <= max_packet <= 65535 or not outstanding or not cumulative:
            raise ProtocolError("unsupported SYN parameters")
        sessions = tuple(Session(*payload[i : i + 3]) for i in range(10, len(payload), 3))
        if len({s.identifier for s in sessions}) != len(sessions):
            raise ProtocolError("duplicate session identifier")
        return cls(outstanding, max_packet, retransmit, ack_ms, retries, cumulative, sessions)

    def control_session(self) -> int:
        matches = [s.identifier for s in self.sessions if s.kind == 0]
        if len(matches) != 1:
            raise ProtocolError("expected exactly one control session")
        return matches[0]


LOCAL_PARAMETERS = LinkParameters(8, MAX_PACKET, 2000, 500, 3, 1, (Session(1, 0, 1),))


@dataclass(frozen=True)
class TLV:
    identifier: int
    value: bytes


def parse_tlvs(data: bytes) -> tuple[TLV, ...]:
    result = []
    while data:
        if len(data) < 4:
            raise ProtocolError("truncated TLV header")
        length, identifier = unpack(">HH", data[:4])
        if length < 4 or length > len(data):
            raise ProtocolError("invalid TLV length")
        result.append(TLV(identifier, data[4:length]))
        data = data[length:]
    return tuple(result)


@dataclass(frozen=True)
class Message:
    identifier: int
    parameters: tuple[TLV, ...]

    def encode(self) -> bytes:
        body = b"".join(
            pack(">HH", len(p.value) + 4, p.identifier) + p.value for p in self.parameters
        )
        length = len(body) + 6
        if length > MAX_CSM:
            raise ProtocolError("control message exceeds local size limit")
        return pack(">HHH", 0x4040, length, self.identifier) + body

    @classmethod
    def decode(cls, data: bytes) -> Message:
        if len(data) < 6 or len(data) > MAX_CSM:
            raise ProtocolError("invalid control message length")
        marker, length, identifier = unpack(">HHH", data[:6])
        if marker != 0x4040 or length != len(data):
            raise ProtocolError("invalid control message header")
        return cls(identifier, parse_tlvs(data[6:]))


class MessageStream:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[Message]:
        self.buffer.extend(chunk)
        if len(self.buffer) > MAX_CSM * 2:
            raise ProtocolError("control input buffer exceeded")
        messages = []
        while len(self.buffer) >= 6:
            if self.buffer[:2] != b"@@":
                raise ProtocolError("invalid control message marker")
            length = int.from_bytes(self.buffer[2:4], "big")
            if not 6 <= length <= MAX_CSM:
                raise ProtocolError("invalid control message length")
            if len(self.buffer) < length:
                break
            messages.append(Message.decode(bytes(self.buffer[:length])))
            del self.buffer[:length]
        return messages


def safe_text(value: bytes) -> str:
    """Decode small NUL-terminated peer strings without terminal control sequences."""
    if len(value) > 256:
        raise ProtocolError("peer string too long")
    decoded = value.rstrip(b"\x00").decode("utf-8", errors="replace")
    return "".join(c if c.isprintable() else "?" for c in decoded)


def summary(message: Message) -> dict[str, object]:
    """Only return allowlisted fields; never return credential or auth bytes."""
    result: dict[str, object] = {
        "id": f"0x{message.identifier:04x}",
        "parameters": [f"0x{p.identifier:04x}" for p in message.parameters],
    }
    fields = {p.identifier: p.value for p in message.parameters}
    if message.identifier == 0x1D01:
        result["name"] = safe_text(fields[0]) if 0 in fields else "(missing)"
        result["model"] = safe_text(fields[1]) if 1 in fields else "(missing)"
        result["manufacturer"] = safe_text(fields[2]) if 2 in fields else "(missing)"
    elif message.identifier == 0x5703:
        result["ssid"] = safe_text(fields[1]) if 1 in fields else "(missing)"
        result["password"] = "[REDACTED]" if 2 in fields else "(absent)"
        if len(fields.get(3, b"")) == 1:
            result["security_type"] = fields[3][0]
        if len(fields.get(4, b"")) == 1:
            result["channel"] = fields[4][0]
    elif message.identifier in (0xAA01, 0xAA03):
        result["credential_bytes"] = len(fields.get(0, b""))
    return result
