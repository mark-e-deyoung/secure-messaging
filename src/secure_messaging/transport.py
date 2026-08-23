from __future__ import annotations

from typing import AsyncIterator, Protocol

from .envelope import Envelope


class TransportError(RuntimeError):
    pass


class TransportRateLimited(TransportError):
    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class Transport(Protocol):
    async def send(self, envelope: Envelope) -> str:
        """Send an envelope and return a transport-specific event identifier."""
        ...

    def receive(self) -> AsyncIterator[Envelope]:
        """Yield validated transport-decoded envelopes."""
        ...
