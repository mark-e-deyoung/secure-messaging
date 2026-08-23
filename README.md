# Secure Messaging

Application-neutral secure coordination and artifact-reference substrate.

This public repository is intended to contain only reconstructable implementation, public protocol/schema documentation, synthetic tests, and build/package logic. Private threat-model evidence, provider experiments, and release qualification belong in `mark-e-deyoung/secure-messaging-private`.

## MVP

The first proof uses Matrix as an end-to-end encrypted transport while keeping the application contract transport-neutral. Bulk data is not placed in Matrix events; messages may carry opaque, integrity-protected artifact references.

The reference implementation is a Python proof harness chosen for iteration speed. It is not an architectural commitment to Python: transport and persistence boundaries are interfaces so a later Rust-native agent can replace it without changing envelope semantics.

## Security posture

- no reusable credentials are embedded in binaries or source;
- Matrix device/crypto state is persistent per endpoint;
- E2EE rooms are required by the Matrix adapter;
- transport is treated as at-least-once-capable;
- duplicate suppression and idempotency are explicit;
- ACK/NACK are protocol messages, not read receipts;
- large/sensitive payloads are referenced as artifacts rather than embedded;
- SHA-256 verifies retrieved artifacts.

## Development

```bash
python -m unittest discover -s tests -v
```

The pure-core tests require only Python 3.11+. Matrix integration is optional:

```bash
pip install '.[matrix]'
```

Live Matrix proof additionally requires two Matrix identities, an invite-restricted encrypted room, and endpoint-scoped credentials supplied at runtime.
