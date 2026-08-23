from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .envelope import Envelope


@dataclass(frozen=True)
class OutboxItem:
    envelope: Envelope
    attempts: int
    next_attempt_at: float
    last_error: str | None


class DurableOutbox:
    """SQLite-backed outbound queue resilient to restarts and transient failures."""

    def __init__(self, path: str | Path) -> None:
        self._db = sqlite3.connect(str(path))
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                message_id TEXT PRIMARY KEY,
                envelope_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL,
                last_error TEXT,
                state TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )
        self._db.commit()

    def enqueue(self, envelope: Envelope, *, now: float | None = None) -> bool:
        envelope.validate()
        now = time.time() if now is None else now
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO outbox(message_id, envelope_json, next_attempt_at) VALUES (?, ?, ?)",
                    (envelope.message_id, json.dumps(envelope.to_dict(), sort_keys=True), now),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def due(self, *, now: float | None = None, limit: int = 100) -> list[OutboxItem]:
        now = time.time() if now is None else now
        rows = self._db.execute(
            """
            SELECT envelope_json, attempts, next_attempt_at, last_error
            FROM outbox
            WHERE state='pending' AND next_attempt_at <= ?
            ORDER BY next_attempt_at, message_id
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()
        return [
            OutboxItem(Envelope.from_dict(json.loads(raw)), int(attempts), float(next_at), error)
            for raw, attempts, next_at, error in rows
        ]

    def defer(
        self,
        message_id: str,
        *,
        error: str,
        now: float | None = None,
        retry_after_seconds: float | None = None,
        base_seconds: float = 1.0,
        cap_seconds: float = 300.0,
    ) -> float:
        now = time.time() if now is None else now
        row = self._db.execute(
            "SELECT attempts FROM outbox WHERE message_id=? AND state='pending'", (message_id,)
        ).fetchone()
        if row is None:
            raise KeyError(message_id)
        new_attempts = int(row[0]) + 1
        exponential = min(cap_seconds, base_seconds * (2 ** (new_attempts - 1)))
        delay = max(exponential, retry_after_seconds or 0.0)
        next_at = now + delay
        with self._db:
            self._db.execute(
                "UPDATE outbox SET attempts=?, next_attempt_at=?, last_error=? WHERE message_id=?",
                (new_attempts, next_at, error, message_id),
            )
        return next_at

    def complete(self, message_id: str) -> None:
        with self._db:
            self._db.execute("UPDATE outbox SET state='sent' WHERE message_id=?", (message_id,))

    def pending_count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()
        return int(row[0])

    def close(self) -> None:
        self._db.close()
