# Consumer integration contract

## Purpose

Define the narrow application-neutral boundary between a consumer application and Secure Messaging.

Secure Messaging treats application payloads as opaque bytes plus generic transport metadata. It does not inspect or interpret domain semantics unless a future generic capability explicitly requires it.

## Consumer responsibilities

Before invoking Secure Messaging, the consumer must decide:

- the payload is authorized to be sent;
- the intended recipient/channel is correct;
- any required informed consent has been obtained;
- the application's sensitivity/exposure policy allows this transfer;
- the payload has been constructed according to the application's own collection/minimization rules;
- requested retention/expiry requirements are known.

## Secure Messaging responsibilities

Given an accepted request, Secure Messaging must:

- resolve the configured recipient/channel identity;
- determine whether the requested delivery policy can be satisfied;
- fail closed when required transport protections cannot be provided;
- protect message/attachment content according to the selected transport/security profile;
- avoid plaintext fallback when the requested policy forbids it;
- send idempotently where possible;
- provide a stable correlation/message identifier;
- expose delivery/failure state and useful generic reason codes;
- avoid requiring application-specific payload knowledge.

## Conceptual request

```text
SendArtifactRequest
  recipient_ref
  payload_path | payload_stream
  content_type
  display_name
  correlation_id
  delivery_policy
  expires_at? / retention_hint?
  opaque_consumer_metadata?   # bounded, non-secret transport correlation only
```

The exact wire/library schema is not yet frozen; this is the semantic contract.

## Conceptual delivery policies

The transport should expose capabilities rather than applications hard-coding Matrix-specific assumptions. A consumer may request properties such as:

```text
authenticated_recipient
end_to_end_content_protection
attachment_content_protection
no_plaintext_fallback
verified_recipient_required
explicit_user_send_action
receipt_required
expiry_requested
```

Secure Messaging maps these requirements to the active backend and reports whether they can be satisfied.

## Result

```text
SendArtifactResult
  correlation_id
  transport_message_id?
  state = accepted | sent | delivered | failed
  policy_satisfied = true | false
  generic_failure_code?
  receipt_timestamp?
```

No application-specific interpretation belongs in the result.

## Matrix adapter boundary

When Matrix is the backend, Secure Messaging owns:

- homeserver/account/session mechanics;
- rooms/channels and membership;
- Matrix IDs/device identities;
- E2EE state and device trust;
- encrypted attachment handling;
- retry/sync/receipt semantics.

Consumer applications should not directly manipulate Matrix rooms, device keys, access tokens, sync loops, attachment encryption, or Matrix-specific retry logic.

## Security rule

A consumer's request for a weaker transport must never implicitly broaden what the consumer application is authorized to package. Collection/consent remains an application decision; transport strength remains a Secure Messaging decision.

## First integration consumer

AU Companion (`SemperSupra/au-student-integrations-private` / public `SemperSupra/au-companion`) is an initial consumer for diagnostic-package delivery. Its P1/P2/P3 diagnostic semantics remain entirely in the AU project. Secure Messaging receives only an opaque artifact and a generic transport policy request.
