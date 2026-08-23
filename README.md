# Secure Messaging

Application-neutral secure coordination and artifact-reference substrate.

This public repository is intended to contain only reconstructable implementation, public protocol/schema documentation, synthetic tests, and build/package logic. Private threat-model evidence, provider experiments, and release qualification belong in `mark-e-deyoung/secure-messaging-private`.

## MVP

The first proof uses Matrix as an end-to-end encrypted transport while keeping the application contract transport-neutral. Bulk data is not placed in Matrix events; messages may carry opaque, integrity-protected artifact references.

The protocol contract is language-neutral JSON Schema plus canonical test vectors. A Python implementation is used as the fast reference/helper implementation, while a dependency-light `.NET 8` contracts/client facade proves direct consumption from portable .NET applications.

The Windows consumer model is an **on-demand self-contained helper process**, not a Python runtime dependency or permanent daemon. The consumer launches the helper, exchanges one newline-delimited JSON request/response over stdio, and the helper owns Matrix E2EE/device state and its durable outbox. This implementation boundary can later move to Rust without changing consuming applications.

## Security posture

- no reusable credentials are embedded in binaries or source;
- Matrix device/crypto state is persistent per endpoint;
- E2EE rooms are required by the Matrix adapter;
- application envelope sender is bound to the authenticated Matrix sender;
- transport is treated as at-least-once-capable;
- duplicate suppression and idempotency are explicit;
- ACK/NACK are protocol messages, not read receipts;
- large/sensitive payloads are referenced as artifacts rather than embedded;
- SHA-256 verifies retrieved artifacts;
- application-specific data classification, consent, and payload meaning remain outside this project.

## Development

Python reference tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src
```

.NET 8 consumer conformance:

```bash
dotnet run --project tests-dotnet/SecureMessaging.Conformance/SecureMessaging.Conformance.csproj --configuration Release
```

Matrix integration is optional for the deterministic core:

```bash
pip install '.[matrix]'
```

Live Matrix proof additionally requires two endpoint-scoped Matrix identities/devices, an invite-restricted encrypted room, and runtime credentials supplied to the helper. Credential enrollment/protected persistence is a separate live-proof gate; credentials are never committed to this repository.
