# Secure Messaging

Application-neutral secure coordination and artifact-delivery substrate.

This public repository is the sanitized/reconstructable implementation surface while development/control material remains in `mark-e-deyoung/secure-messaging-private`.

## Responsibility boundary

Secure Messaging owns **messaging and delivery concerns**. Consumer applications own **application semantics and authorization decisions**.

### Secure Messaging owns

- transport/protocol integration, including Matrix where selected;
- sender/device/service identity and recipient/channel addressing;
- room/channel creation and lifecycle mechanics;
- end-to-end message and attachment protection;
- recipient/device trust state exposed through the API;
- secure artifact upload/download;
- retries, resumability, deduplication, idempotency and correlation;
- delivery/read receipts when the transport supports them;
- attachment size/chunking handling;
- transport-level metadata minimization;
- delivery-policy capability discovery and enforcement;
- generic CLI/library/service interfaces usable by multiple applications.

### Consumer applications own

- what the payload means;
- whether it may be collected or sent;
- informed consent;
- application-specific sensitivity/exposure classification;
- payload construction and minimization;
- domain-specific retention requirements;
- application-specific audit context.

Secure Messaging must not need to understand AU/ABAC/SPARK, student records, diagnostic schemas, provider APIs, or other consumer-domain details.

> **Applications decide what may be sent and why. Secure Messaging decides how to deliver the opaque payload securely and report the delivery outcome.**

## Consumer contract

Consumers submit opaque messages/artifacts with a generic delivery request containing only transport-relevant metadata such as recipient/channel reference, delivery-policy reference, content type/name, correlation ID and optional expiry/retention hints.

See `docs/CONSUMER_INTEGRATION_CONTRACT.md`.

## Development model

Substantive implementation should arrive through reviewable branches and pull requests. Private architecture/threat-model/evidence/qualification work belongs in `mark-e-deyoung/secure-messaging-private`; sanitized implementation, generic tests, public CI and release artifacts belong here.
