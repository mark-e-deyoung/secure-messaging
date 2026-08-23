from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .envelope import Envelope


class MemoryTransport:
    """Deterministic test transport with optional duplicate injection."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue()
        self._counter = 0

    async def send(self, envelope: Envelope) -> str:
        envelope.validate()
        self._counter += 1
        await self._queue.put(envelope)
        return f"memory:{self._counter}"

    async def inject_duplicate(self, envelope: Envelope) -> None:
        await self._queue.put(envelope)

    async def receive_one(self, timeout: float = 1.0) -> Envelope:
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    async def receive(self) -> AsyncIterator[Envelope]:
        while True:
            yield await self._queue.get()
