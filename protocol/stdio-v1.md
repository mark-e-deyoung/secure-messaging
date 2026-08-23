# Local helper protocol v1

The first AU-compatible integration boundary is newline-delimited JSON over stdin/stdout. The consuming application starts the helper on demand with `--stdio-once`, writes exactly one request line, reads exactly one response line, and the helper exits.

This is deliberately not a network API and not a background daemon.

## Send request

```json
{"op":"send","request_id":"...","envelope":{}}
```

`envelope` MUST validate against `message-envelope-v1.schema.json`.

## Response

```json
{"request_id":"...","accepted":true,"message_id":"...","error_code":null}
```

`accepted=true` means the helper durably accepted responsibility for delivery according to its local outbox semantics. It does not mean the remote application processed the message. Remote processing is represented by an explicit protocol ACK event.

The helper MUST return stable machine-readable error codes and MUST NOT expose raw credentials, Matrix event bodies, provider error bodies, or local secret-store paths in the response.

## State ownership

The helper owns Matrix endpoint credentials, device/crypto state, delivery ledger, and durable outbox in its own per-user state directory. The application does not receive those credentials.

## Packaging

A consumer may bundle a verified self-contained helper executable and invoke it by absolute path. The helper is not required to be registered or installed as a Windows service.
