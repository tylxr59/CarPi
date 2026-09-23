"""Phone-role iAP2 research probe with explicit unverified-auth opt-in."""

from __future__ import annotations

import logging
import secrets
import time
from enum import Enum, auto

from carpi.iap2 import (
    ACK,
    MARKER,
    RST,
    SYN,
    TLV,
    LinkParameters,
    Message,
    MessageStream,
    Packet,
    PacketStream,
    ProtocolError,
    summary,
)
from carpi.transport import Iap2Transport

LOG = logging.getLogger("carpi")


class State(Enum):
    CONNECTED = auto()
    MARKER = auto()
    NEGOTIATING = auto()
    NEGOTIATED = auto()
    IDENTIFYING = auto()
    IDENTIFIED = auto()
    AUTHENTICATING = auto()
    AUTH_UNVERIFIED = auto()
    AUTH_UNVERIFIED_ACCEPTED = auto()
    WIFI_OBSERVING = auto()
    WIFI_RECEIVED = auto()


class Authentication(Enum):
    NOT_REACHED = auto()
    VERIFIED = auto()  # Reserved for a future cryptographic verifier.
    UNVERIFIED_STOPPED = auto()
    UNVERIFIED_ACCEPTED = auto()
    FAILED = auto()


ALLOWED = {
    State.CONNECTED: {State.MARKER},
    State.MARKER: {State.NEGOTIATING},
    State.NEGOTIATING: {State.NEGOTIATED},
    State.NEGOTIATED: {State.IDENTIFYING},
    State.IDENTIFYING: {State.IDENTIFIED},
    State.IDENTIFIED: {State.AUTHENTICATING},
    State.AUTHENTICATING: {State.AUTH_UNVERIFIED},
    State.AUTH_UNVERIFIED: {State.AUTH_UNVERIFIED_ACCEPTED},
    State.AUTH_UNVERIFIED_ACCEPTED: {State.WIFI_OBSERVING},
    State.WIFI_OBSERVING: {State.WIFI_RECEIVED},
}


class Probe:
    def __init__(
        self,
        sock: Iap2Transport,
        timeout: float = 20,
        label: str = "bt",
        allow_unverified_accessory: bool = False,
    ) -> None:
        self.sock = sock
        self.sock.settimeout(timeout)
        self.timeout = timeout
        self.label = label
        self.allow_unverified_accessory = allow_unverified_accessory
        self.state = State.CONNECTED
        self.authentication = Authentication.NOT_REACHED
        self.wifi_received = False
        self.wifi_ssid: str | None = None
        self.frames = PacketStream()
        self.messages = MessageStream()
        self.pending: list[Packet] = []
        self.prefetched: list[Packet] = []
        self.pending_messages: list[Message] = []
        self.next_seq = 0
        self.peer_seq: int | None = None
        self.control_session: int | None = None
        self.our_syn_seq: int | None = None

    def transition(self, state: State) -> None:
        if state not in ALLOWED.get(self.state, set()):
            raise ProtocolError(f"invalid state transition {self.state.name} -> {state.name}")
        self.state = state
        LOG.info("[iap2] %s", state.name.lower())

    def send(
        self, control: int, payload: bytes = b"", session: int = 0, consume_seq: bool = False
    ) -> None:
        seq = self.next_seq
        packet = Packet(control, seq, self.peer_seq or 0, session, payload)
        self.sock.sendall(packet.encode())
        LOG.debug(
            "[iap2] tx control=0x%02x seq=%d ack=%d session=%d bytes=%d",
            control,
            seq,
            packet.ack,
            session,
            len(payload),
        )
        if consume_seq:
            self.next_seq = (seq + 1) & 0xFF

    def receive(self) -> Packet:
        deadline = time.monotonic() + self.timeout
        while True:
            if self.pending:
                packet = self.pending.pop(0)
                LOG.debug(
                    "[iap2] rx control=0x%02x seq=%d ack=%d session=%d bytes=%d",
                    packet.control,
                    packet.seq,
                    packet.ack,
                    packet.session,
                    len(packet.payload),
                )
                if packet.control & RST:
                    raise ProtocolError("peer reset iAP2 link")
                if packet.payload and not packet.control & SYN:
                    expected = packet.seq if self.peer_seq is None else (self.peer_seq + 1) & 0xFF
                    if packet.seq != expected:
                        raise ProtocolError(
                            f"out-of-order sequence: got {packet.seq}, expected {expected}"
                        )
                    self.peer_seq = packet.seq
                    self.send(ACK)
                return packet
            if time.monotonic() > deadline:
                raise TimeoutError(f"timed out in {self.state.name.lower()}")
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError(f"peer closed in {self.state.name.lower()}")
            self.pending.extend(self.frames.feed(chunk))

    def next_message(self) -> Message:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() <= deadline:
            if self.pending_messages:
                message = self.pending_messages.pop(0)
                if message.identifier == 0x5703:
                    self.observe_wifi(message)
                return message
            packet = self.prefetched.pop(0) if self.prefetched else self.receive()
            if (
                packet.payload
                and packet.session == self.control_session
                and not packet.control & SYN
            ):
                messages = self.messages.feed(packet.payload)
                if messages:
                    for message in messages:
                        LOG.info("[iap2] received %s", summary(message))
                    self.pending_messages.extend(messages)
        raise TimeoutError("timed out awaiting control message")

    def observe_wifi(self, message: Message) -> None:
        for identifier in (1, 2, 3, 4):
            if sum(p.identifier == identifier for p in message.parameters) > 1:
                raise ProtocolError(f"duplicate wireless configuration field {identifier}")
        ssids = [p.value for p in message.parameters if p.identifier == 1]
        if len(ssids) != 1 or not ssids[0]:
            raise ProtocolError("wireless configuration lacks one nonempty SSID")
        for field in (3, 4):
            if any(p.identifier == field and len(p.value) != 1 for p in message.parameters):
                raise ProtocolError(f"invalid wireless configuration field {field}")
        details = summary(message)
        self.wifi_ssid = str(details["ssid"])
        self.wifi_received = True
        LOG.info("[wifi] wireless CarPlay configuration received")
        LOG.info("[wifi] SSID: %s", self.wifi_ssid)
        LOG.info("[wifi] password: %s", details["password"])

    def expect(self, identifier: int) -> Message:
        for _ in range(8):
            message = self.next_message()
            if message.identifier == identifier:
                return message
            if message.identifier in (0x1D03, 0xAA04):
                raise ProtocolError(f"peer rejected stage with message 0x{message.identifier:04x}")
            if message.identifier != 0x5703:
                LOG.info("[iap2] interim message 0x%04x", message.identifier)
        raise ProtocolError(f"expected message 0x{identifier:04x}; too many interim messages")

    def send_message(self, identifier: int, parameters: tuple[TLV, ...] = ()) -> None:
        if self.control_session is None:
            raise ProtocolError("no control session negotiated")
        LOG.info("[iap2] sending 0x%04x", identifier)
        self.send(ACK, Message(identifier, parameters).encode(), self.control_session, True)

    def run(self) -> State:
        LOG.info("[iap2] starting link negotiation")
        self.transition(State.MARKER)
        self.sock.sendall(MARKER)
        marker = bytearray()
        while len(marker) < len(MARKER):
            chunk = self.sock.recv(len(MARKER) - len(marker))
            if not chunk:
                raise ConnectionError("peer closed before iAP2 marker")
            marker.extend(chunk)
        if bytes(marker) != MARKER:
            raise ProtocolError("iAP2 marker mismatch")
        self.transition(State.NEGOTIATING)
        for _ in range(8):
            packet = self.receive()
            if packet.control & SYN:
                peer = LinkParameters.decode(packet.payload)
                self.control_session = peer.control_session()
                self.peer_seq = packet.seq
                LOG.info(
                    "[iap2] peer max_packet=%d control_session=%d",
                    peer.max_packet,
                    self.control_session,
                )
                break
        else:
            raise ProtocolError("peer sent too many packets before SYN")
        self.our_syn_seq = self.next_seq
        self.send(
            SYN | ACK,
            LinkParameters(8, min(peer.max_packet, 4096), 2000, 500, 3, 1, peer.sessions).encode(),
            consume_seq=True,
        )
        for _ in range(4):
            packet = self.receive()
            if packet.payload and not packet.control & SYN:
                self.prefetched.append(packet)
            if packet.control & ACK and packet.ack == self.our_syn_seq:
                break
        else:
            raise ProtocolError("peer did not ACK our SYN")
        self.transition(State.NEGOTIATED)
        self.transition(State.IDENTIFYING)
        self.send_message(0x1D00)  # StartIdentification, empty body
        identification = self.expect(0x1D01)
        if not any(p.identifier == 0 and p.value for p in identification.parameters):
            raise ProtocolError("identification lacks accessory name")
        self.send_message(0x1D02)  # IdentificationAccepted, no credential claim
        self.transition(State.IDENTIFIED)
        self.transition(State.AUTHENTICATING)
        self.authentication = Authentication.FAILED
        self.send_message(0xAA00)  # RequestAuthenticationCertificate
        certificate = self.expect(0xAA01)
        if not any(p.identifier == 0 and p.value for p in certificate.parameters):
            raise ProtocolError("empty authentication certificate")
        self.send_message(0xAA02, (TLV(0, secrets.token_bytes(20)),))
        response = self.expect(0xAA03)
        if not any(p.identifier == 0 and p.value for p in response.parameters):
            raise ProtocolError("empty authentication response")
        self.transition(State.AUTH_UNVERIFIED)
        if not self.allow_unverified_accessory:
            self.authentication = Authentication.UNVERIFIED_STOPPED
            LOG.warning(
                "[auth] response received but NOT verified; stopping before AuthenticationSucceeded"
            )
            return self.state
        self.authentication = Authentication.UNVERIFIED_ACCEPTED
        LOG.warning("[WARNING] Accessory authentication has NOT been cryptographically verified.")
        LOG.warning(
            "[WARNING] Continuing because --allow-unverified-accessory was explicitly requested."
        )
        self.transition(State.AUTH_UNVERIFIED_ACCEPTED)
        self.send_message(0xAA05)  # AuthenticationSucceeded: research assertion only.
        self.transition(State.WIFI_OBSERVING)
        if not self.wifi_received:
            self.send_message(0x5702)  # RequestAccessoryWiFiConfigurationInformation.
            self.expect(0x5703)
        self.transition(State.WIFI_RECEIVED)
        return self.state
