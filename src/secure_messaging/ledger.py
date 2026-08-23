from __future__ import annotations

import sqlite3
from pathlib import Path

from .envelope import Envelope


class DeliveryLedger:
    """Durable duplicate/idempotency suppression without exactly-once claims."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._db = sqlite3.connect(str(path))
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS deliveries (
                message_id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE,
                message_type TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'claimed',
                claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._db.commit()

    def claim(self, envelope: Envelope) -> bool:
        envelope.validate()
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO deliveries(message_id, idempotency_key, message_type) VALUES (?, ?, ?)",
                    (envelope.message_id, envelope.idempotency_key, envelope.message_type),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def set_state(self, message_id: str, state: str) -> None:
        with self._db:
            self._db.execute("UPDATE deliveries SET state=? WHERE message_id=?", (state, message_id))

    def state(self, message_id: str) -> str | None:
        row = self._db.execute("SELECT state FROM deliveries WHERE message_id=?", (message_id,)).fetchone()
        return None if row is None else str(row[0])

    def close(self) -> None:
        self._db.close()
