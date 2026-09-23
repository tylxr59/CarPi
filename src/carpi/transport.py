"""Byte-stream boundary shared by Bluetooth and a future USB mux endpoint."""

from __future__ import annotations

import os
import select
import socket
import time
from typing import Protocol


class Iap2Transport(Protocol):
    def settimeout(self, timeout: float) -> None: ...

    def recv(self, size: int) -> bytes: ...

    def sendall(self, data: bytes) -> None: ...


class SocketTransport:
    """Preserve the existing RFCOMM socket behavior behind a named boundary."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock

    def settimeout(self, timeout: float) -> None:
        self.sock.settimeout(timeout)

    def recv(self, size: int) -> bytes:
        return self.sock.recv(size)

    def sendall(self, data: bytes) -> None:
        self.sock.sendall(data)


class EndpointTransport:
    """Stream adapter for a future FunctionFS/mux byte endpoint.

    This only supplies partial-I/O handling. It does not implement Apple mux framing.
    """

    def __init__(self, rx_fd: int, tx_fd: int) -> None:
        self.rx_fd = rx_fd
        self.tx_fd = tx_fd
        self.timeout = 20.0

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def recv(self, size: int) -> bytes:
        if not select.select([self.rx_fd], [], [], self.timeout)[0]:
            raise TimeoutError("USB endpoint read timed out")
        return os.read(self.rx_fd, size)

    def sendall(self, data: bytes) -> None:
        view = memoryview(data)
        deadline = time.monotonic() + self.timeout
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.tx_fd], [], remaining)[1]:
                raise TimeoutError("USB endpoint write timed out")
            written = os.write(self.tx_fd, view)
            if written <= 0:
                raise ConnectionError("USB endpoint disconnected during write")
            view = view[written:]
