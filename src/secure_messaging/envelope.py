from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

PROTOCOL_V1 = "org.sempersupra.secure-messaging.v1"
ACK_TYPE = "org.sempersupra.secure-messaging.ack"
_ALLOWED_KEYS = {
    "protocol", "message_id", "message_type", "sender", "target", "created_at",
    "correlation_id", "causation_id", "expires_at", "requires_ack",
    "idempotency_key", "body", "artifacts",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("datetime must include timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Envelope:
    protocol: str
    message_id: str
    message_type: str
    sender: str
    target: str
    created_at: datetime
    body: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None
    expires_at: datetime | None = None
    requires_ack: bool = False
    idempotency_key: str | None = None
    artifacts: tuple[dict[str, Any], ...] = ()

    @classmethod
    def new(
        cls,
        *,
        message_type: str,
        sender: str,
        target: str,
        body: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        expires_at: datetime | None = None,
        requires_ack: bool = False,
        idempotency_key: str | None = None,
        artifacts: tuple[dict[str, Any], ...] = (),
    ) -> "Envelope":
        env = cls(
            protocol=PROTOCOL_V1,
            message_id=str(uuid4()),
            message_type=message_type,
            sender=sender,
            target=target,
            created_at=_utc_now(),
            body=body or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            expires_at=expires_at,
            requires_ack=requires_ack,
            idempotency_key=idempotency_key,
            artifacts=artifacts,
        )
        env.validate()
        return env

    def validate(self) -> None:
        if self.protocol != PROTOCOL_V1:
            raise ValueError(f"unsupported protocol: {self.protocol}")
        UUID(self.message_id)
        if not self.message_type.strip():
            raise ValueError("message_type is required")
        if not self.sender.strip() or not self.target.strip():
            raise ValueError("sender and target are required")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if not isinstance(self.body, dict):
            raise ValueError("body must be an object")
        if not all(isinstance(item, dict) for item in self.artifacts):
            raise ValueError("artifacts must contain objects")

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or _utc_now()
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return now.astimezone(timezone.utc) >= self.expires_at.astimezone(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "protocol": self.protocol,
            "message_id": self.message_id,
            "message_type": self.message_type,
            "sender": self.sender,
            "target": self.target,
            "created_at": _iso(self.created_at),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "expires_at": _iso(self.expires_at),
            "requires_ack": self.requires_ack,
            "idempotency_key": self.idempotency_key,
            "body": self.body,
            "artifacts": list(self.artifacts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Envelope":
        unknown = set(data) - _ALLOWED_KEYS
        if unknown:
            raise ValueError(f"unknown envelope fields: {', '.join(sorted(unknown))}")
        env = cls(
            protocol=str(data["protocol"]),
            message_id=str(data["message_id"]),
            message_type=str(data["message_type"]),
            sender=str(data["sender"]),
            target=str(data["target"]),
            created_at=_parse_iso(str(data["created_at"])) or _utc_now(),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            expires_at=_parse_iso(data.get("expires_at")),
            requires_ack=bool(data.get("requires_ack", False)),
            idempotency_key=data.get("idempotency_key"),
            body=dict(data.get("body") or {}),
            artifacts=tuple(data.get("artifacts") or ()),
        )
        env.validate()
        return env

    def ack(self, *, sender: str, outcome: str, detail: str | None = None) -> "Envelope":
        if outcome not in {"accepted", "rejected", "deferred", "completed", "failed"}:
            raise ValueError("invalid acknowledgement outcome")
        return Envelope.new(
            message_type=ACK_TYPE,
            sender=sender,
            target=self.sender,
            correlation_id=self.correlation_id or self.message_id,
            causation_id=self.message_id,
            body={"outcome": outcome, "detail": detail},
            requires_ack=False,
        )
