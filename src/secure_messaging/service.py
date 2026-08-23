from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .envelope import Envelope
from .ledger import DeliveryLedger


@dataclass(frozen=True)
class DeliveryDecision:
    accepted: bool
    reason: str


class SecureMessenger:
    """Application-neutral receive gate for freshness, targeting and duplicate suppression."""

    def __init__(self, ledger: DeliveryLedger, *, local_principal: str | None = None) -> None:
        self.ledger = ledger
        self.local_principal = local_principal

    async def dispatch(
        self,
        envelope: Envelope,
        handler: Callable[[Envelope], Awaitable[None]],
        *,
        now: datetime | None = None,
    ) -> DeliveryDecision:
        envelope.validate()
        now = now or datetime.now(timezone.utc)
        if envelope.is_expired(now):
            return DeliveryDecision(False, "expired")
        if self.local_principal is not None and envelope.target != self.local_principal:
            return DeliveryDecision(False, "wrong_target")
        if not self.ledger.claim(envelope):
            return DeliveryDecision(False, "duplicate")
        try:
            await handler(envelope)
        except Exception:
            self.ledger.set_state(envelope.message_id, "failed")
            raise
        self.ledger.set_state(envelope.message_id, "delivered")
        return DeliveryDecision(True, "delivered")
