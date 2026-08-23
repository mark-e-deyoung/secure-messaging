import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from secure_messaging.artifacts import ArtifactLocation, ArtifactReference
from secure_messaging.envelope import ACK_TYPE, Envelope
from secure_messaging.ledger import DeliveryLedger
from secure_messaging.matrix_transport import MatrixEndpointConfig, MatrixTransport
from secure_messaging.outbox import DurableOutbox
from secure_messaging.service import SecureMessenger
from secure_messaging.transport import TransportError


class EnvelopeTests(unittest.TestCase):
    def test_round_trip_and_ack(self):
        env = Envelope.new(
            message_type="example.event",
            sender="@a:example.org",
            target="@b:example.org",
            body={"answer": 42},
            requires_ack=True,
            idempotency_key="job-1",
        )
        observed = Envelope.from_dict(env.to_dict())
        self.assertEqual(env, observed)
        ack = env.ack(sender="@b:example.org", outcome="accepted")
        self.assertEqual(ACK_TYPE, ack.message_type)
        self.assertEqual(env.message_id, ack.causation_id)
        self.assertEqual(env.sender, ack.target)

    def test_expiry(self):
        env = Envelope.new(
            message_type="example.expiring",
            sender="a",
            target="b",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        self.assertTrue(env.is_expired())

    def test_rejects_unknown_fields(self):
        env = Envelope.new(message_type="x", sender="a", target="b").to_dict()
        env["unexpected"] = True
        with self.assertRaises(ValueError):
            Envelope.from_dict(env)

    def test_canonical_cross_language_vector(self):
        vector = Path(__file__).resolve().parents[1] / "test-vectors" / "message-envelope-basic.json"
        env = Envelope.from_dict(json.loads(vector.read_text(encoding="utf-8")))
        self.assertEqual("example.available", env.message_type)
        self.assertEqual("@sender:example.org", env.sender)


class LedgerTests(unittest.TestCase):
    def test_message_and_idempotency_duplicates(self):
        ledger = DeliveryLedger()
        first = Envelope.new(message_type="x", sender="a", target="b", idempotency_key="effect-1")
        duplicate_effect = Envelope.new(message_type="x", sender="a", target="b", idempotency_key="effect-1")
        self.assertTrue(ledger.claim(first))
        self.assertFalse(ledger.claim(first))
        self.assertFalse(ledger.claim(duplicate_effect))
        ledger.close()

    def test_dispatch_rejects_expired_duplicate_and_wrong_target(self):
        ledger = DeliveryLedger()
        messenger = SecureMessenger(ledger, local_principal="b")
        calls = []

        async def handler(env):
            calls.append(env.message_id)

        valid = Envelope.new(message_type="x", sender="a", target="b")
        wrong = Envelope.new(message_type="x", sender="a", target="c")
        expired = Envelope.new(
            message_type="x", sender="a", target="b",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )

        async def run():
            return (
                await messenger.dispatch(valid, handler),
                await messenger.dispatch(valid, handler),
                await messenger.dispatch(wrong, handler),
                await messenger.dispatch(expired, handler),
            )

        first, duplicate, wrong_target, old = asyncio.run(run())
        self.assertTrue(first.accepted)
        self.assertEqual("duplicate", duplicate.reason)
        self.assertEqual("wrong_target", wrong_target.reason)
        self.assertEqual("expired", old.reason)
        self.assertEqual([valid.message_id], calls)
        ledger.close()


class ArtifactTests(unittest.TestCase):
    def test_hash_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "blob.bin"
            path.write_bytes(b"diagnostic bytes" * 100)
            ref = ArtifactReference.from_file(
                path,
                media_type="application/octet-stream",
                locations=(ArtifactLocation("test", "memory://blob"),),
            )
            self.assertTrue(ref.verify_file(path))
            self.assertEqual(f"sha256:{ref.sha256_hex}", ref.artifact_id)
            path.write_bytes(b"modified")
            self.assertFalse(ref.verify_file(path))


class OutboxTests(unittest.TestCase):
    def test_persists_and_honors_retry_after(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "outbox.sqlite"
            env = Envelope.new(message_type="x", sender="a", target="b")
            first = DurableOutbox(db)
            self.assertTrue(first.enqueue(env, now=100.0))
            self.assertFalse(first.enqueue(env, now=100.0))
            self.assertEqual("pending", first.state(env.message_id))
            self.assertEqual(env.message_id, first.due(now=100.0)[0].envelope.message_id)
            next_at = first.defer(
                env.message_id,
                error="M_LIMIT_EXCEEDED",
                now=100.0,
                retry_after_seconds=12.0,
            )
            self.assertEqual(112.0, next_at)
            self.assertEqual([], first.due(now=111.999))
            first.close()

            second = DurableOutbox(db)
            due = second.due(now=112.0)
            self.assertEqual(1, len(due))
            self.assertEqual(1, due[0].attempts)
            second.complete(env.message_id)
            self.assertEqual("sent", second.state(env.message_id))
            second.close()


class MatrixBoundaryTests(unittest.TestCase):
    def test_outbound_sender_must_match_authenticated_user(self):
        config = MatrixEndpointConfig(
            homeserver="https://example.org",
            user_id="@a:example.org",
            device_id="DEVICE",
            access_token="test-token",
            room_id="!room:example.org",
            store_path="unused",
            pickle_key="test-pickle-key",
        )
        transport = MatrixTransport(config)
        forged = Envelope.new(message_type="x", sender="@b:example.org", target="@a:example.org")
        with self.assertRaises(TransportError):
            asyncio.run(transport.send(forged))


class HelperContractTests(unittest.TestCase):
    def test_stdio_once_accepts_and_completes_synthetic_send(self):
        with tempfile.TemporaryDirectory() as td:
            env = Envelope.new(message_type="example.synthetic", sender="sender", target="target")
            request = {"op": "send", "request_id": "req-1", "envelope": env.to_dict()}
            repo = Path(__file__).resolve().parents[1]
            child_env = os.environ.copy()
            child_env["PYTHONPATH"] = str(repo / "src")
            child_env["SECURE_MESSAGING_STATE_DIR"] = td
            child_env["SECURE_MESSAGING_TEST_TRANSPORT"] = "memory"
            result = subprocess.run(
                [sys.executable, "-m", "secure_messaging.cli", "--stdio-once"],
                input=json.dumps(request) + "\n",
                text=True,
                capture_output=True,
                cwd=repo,
                env=child_env,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual("req-1", response["request_id"])
            self.assertTrue(response["accepted"])
            self.assertEqual(env.message_id, response["message_id"])
            self.assertIsNone(response["error_code"])


if __name__ == "__main__":
    unittest.main()
