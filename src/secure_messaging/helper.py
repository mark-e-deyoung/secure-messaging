from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .envelope import Envelope
from .matrix_transport import MatrixEndpointConfig, MatrixTransport
from .memory import MemoryTransport
from .outbox import DurableOutbox
from .transport import TransportError, TransportRateLimited


def default_state_dir() -> Path:
    override = os.environ.get("SECURE_MESSAGING_STATE_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "SemperSupra" / "SecureMessaging"
    return Path.home() / ".local" / "state" / "semper-secure-messaging"


def _matrix_config_from_env(state_dir: Path) -> MatrixEndpointConfig | None:
    values = {
        "homeserver": os.environ.get("SECURE_MESSAGING_MATRIX_HOMESERVER"),
        "user_id": os.environ.get("SECURE_MESSAGING_MATRIX_USER_ID"),
        "device_id": os.environ.get("SECURE_MESSAGING_MATRIX_DEVICE_ID"),
        "access_token": os.environ.get("SECURE_MESSAGING_MATRIX_ACCESS_TOKEN"),
        "room_id": os.environ.get("SECURE_MESSAGING_MATRIX_ROOM_ID"),
        "pickle_key": os.environ.get("SECURE_MESSAGING_MATRIX_PICKLE_KEY"),
    }
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError("incomplete Matrix endpoint configuration")
    return MatrixEndpointConfig(
        homeserver=str(values["homeserver"]),
        user_id=str(values["user_id"]),
        device_id=str(values["device_id"]),
        access_token=str(values["access_token"]),
        room_id=str(values["room_id"]),
        store_path=str(state_dir / "matrix-store"),
        pickle_key=str(values["pickle_key"]),
    )


def _transport_from_environment(state_dir: Path):
    if os.environ.get("SECURE_MESSAGING_TEST_TRANSPORT") == "memory":
        return MemoryTransport()
    config = _matrix_config_from_env(state_dir)
    return None if config is None else MatrixTransport(config)


async def _flush_due(outbox: DurableOutbox, transport: Any) -> None:
    for item in outbox.due():
        try:
            await transport.send(item.envelope)
        except TransportRateLimited as exc:
            outbox.defer(
                item.envelope.message_id,
                error="rate_limited",
                retry_after_seconds=exc.retry_after_seconds,
            )
            break
        except TransportError:
            outbox.defer(item.envelope.message_id, error="transport_error")
        except Exception:
            # Do not propagate provider/transport details through the local IPC boundary.
            outbox.defer(item.envelope.message_id, error="transport_error")
        else:
            outbox.complete(item.envelope.message_id)


async def handle_stdio_request(request: dict[str, Any]) -> dict[str, Any]:
    request_id = str(request.get("request_id") or "")
    if not request_id:
        return {"request_id": "", "accepted": False, "message_id": None, "error_code": "invalid_request"}
    if request.get("op") != "send" or not isinstance(request.get("envelope"), dict):
        return {"request_id": request_id, "accepted": False, "message_id": None, "error_code": "unsupported_operation"}

    try:
        envelope = Envelope.from_dict(request["envelope"])
    except (KeyError, TypeError, ValueError):
        return {"request_id": request_id, "accepted": False, "message_id": None, "error_code": "invalid_envelope"}

    state_dir = default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    outbox = DurableOutbox(state_dir / "outbox.sqlite3")
    try:
        outbox.enqueue(envelope)
        try:
            transport = _transport_from_environment(state_dir)
        except ValueError:
            transport = None
            config_error = True
        else:
            config_error = False

        if transport is not None:
            await _flush_due(outbox, transport)

        state = outbox.state(envelope.message_id)
        if state == "sent":
            error_code = None
        elif config_error:
            error_code = "queued_configuration_incomplete"
        elif transport is None:
            error_code = "queued_transport_unconfigured"
        else:
            error_code = "queued_retry"
        return {
            "request_id": request_id,
            "accepted": state in {"pending", "sent"},
            "message_id": envelope.message_id,
            "error_code": error_code,
        }
    finally:
        outbox.close()
