from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from .envelope import Envelope
from .transport import TransportError, TransportRateLimited

CONTENT_KEY = "org.sempersupra.secure-messaging.v1"


@dataclass(frozen=True)
class MatrixEndpointConfig:
    homeserver: str
    user_id: str
    device_id: str
    access_token: str
    room_id: str
    store_path: str
    pickle_key: str

    def validate(self) -> None:
        required = {
            "homeserver": self.homeserver,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "access_token": self.access_token,
            "room_id": self.room_id,
            "store_path": self.store_path,
            "pickle_key": self.pickle_key,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(f"missing Matrix endpoint configuration: {', '.join(missing)}")


class MatrixTransport:
    """Minimal Matrix E2EE adapter for the proof harness.

    The application envelope sender is cryptographically/transport bound to the
    authenticated Matrix event sender: forged logical sender fields are rejected.
    """

    def __init__(self, config: MatrixEndpointConfig) -> None:
        config.validate()
        self.config = config
        self._client = None
        self._incoming: asyncio.Queue[Envelope] = asyncio.Queue()

    async def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from nio import AsyncClient, AsyncClientConfig, MatrixRoom, RoomMessageText
        except ImportError as exc:
            raise RuntimeError("install the 'matrix' optional dependency") from exc

        Path(self.config.store_path).mkdir(parents=True, exist_ok=True)
        nio_config = AsyncClientConfig(
            store_sync_tokens=True,
            encryption_enabled=True,
            pickle_key=self.config.pickle_key,
            max_limit_exceeded=0,
        )
        client = AsyncClient(
            self.config.homeserver,
            self.config.user_id,
            device_id=self.config.device_id,
            store_path=self.config.store_path,
            config=nio_config,
        )
        client.restore_login(self.config.user_id, self.config.device_id, self.config.access_token)

        async def callback(room: MatrixRoom, event: RoomMessageText) -> None:
            if room.room_id != self.config.room_id:
                return
            source = getattr(event, "source", {}) or {}
            content = source.get("content", {}) if isinstance(source, dict) else {}
            raw = content.get(CONTENT_KEY)
            if not isinstance(raw, dict):
                return
            try:
                envelope = Envelope.from_dict(raw)
            except (KeyError, TypeError, ValueError):
                return
            matrix_sender = str(getattr(event, "sender", ""))
            if not matrix_sender or envelope.sender != matrix_sender:
                return
            await self._incoming.put(envelope)

        client.add_event_callback(callback, RoomMessageText)
        await client.sync(timeout=30000, full_state=True)
        room = client.rooms.get(self.config.room_id)
        if room is None or not room.encrypted:
            await client.close()
            raise TransportError("configured Matrix room is not an encrypted joined room")
        self._client = client
        return client

    async def send(self, envelope: Envelope) -> str:
        envelope.validate()
        if envelope.sender != self.config.user_id:
            raise TransportError("envelope sender does not match authenticated Matrix user")
        client = await self._ensure_client()
        response = await client.room_send(
            self.config.room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": f"Secure Messaging: {envelope.message_type}",
                CONTENT_KEY: envelope.to_dict(),
            },
            tx_id=envelope.message_id,
            ignore_unverified_devices=False,
        )
        event_id = getattr(response, "event_id", None)
        if event_id:
            return str(event_id)
        retry_after_ms = getattr(response, "retry_after_ms", None)
        if retry_after_ms is not None:
            raise TransportRateLimited(
                "Matrix homeserver rate limited send",
                retry_after_seconds=float(retry_after_ms) / 1000.0,
            )
        raise TransportError(f"Matrix send failed: {type(response).__name__}")

    async def receive(self) -> AsyncIterator[Envelope]:
        client = await self._ensure_client()
        sync_task = asyncio.create_task(client.sync_forever(timeout=30000, full_state=True))
        try:
            while True:
                yield await self._incoming.get()
        finally:
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass
            await client.close()
            self._client = None
