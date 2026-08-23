using System.Text.Json;
using System.Text.Json.Serialization;

namespace SemperSupra.SecureMessaging.Contracts;

public sealed record MessageEnvelope
{
    public const string ProtocolV1 = "org.sempersupra.secure-messaging.v1";

    [JsonPropertyName("protocol")]
    public string Protocol { get; init; } = ProtocolV1;

    [JsonPropertyName("message_id")]
    public required string MessageId { get; init; }

    [JsonPropertyName("message_type")]
    public required string MessageType { get; init; }

    [JsonPropertyName("sender")]
    public required string Sender { get; init; }

    [JsonPropertyName("target")]
    public required string Target { get; init; }

    [JsonPropertyName("created_at")]
    public required DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("correlation_id")]
    public string? CorrelationId { get; init; }

    [JsonPropertyName("causation_id")]
    public string? CausationId { get; init; }

    [JsonPropertyName("expires_at")]
    public DateTimeOffset? ExpiresAt { get; init; }

    [JsonPropertyName("requires_ack")]
    public bool RequiresAck { get; init; }

    [JsonPropertyName("idempotency_key")]
    public string? IdempotencyKey { get; init; }

    [JsonPropertyName("body")]
    public JsonElement Body { get; init; }

    [JsonPropertyName("artifacts")]
    public IReadOnlyList<ArtifactReference> Artifacts { get; init; } = Array.Empty<ArtifactReference>();

    public void Validate()
    {
        if (!string.Equals(Protocol, ProtocolV1, StringComparison.Ordinal))
            throw new InvalidOperationException($"Unsupported protocol: {Protocol}");
        if (!Guid.TryParse(MessageId, out _))
            throw new InvalidOperationException("message_id must be a UUID");
        if (string.IsNullOrWhiteSpace(MessageType))
            throw new InvalidOperationException("message_type is required");
        if (string.IsNullOrWhiteSpace(Sender) || string.IsNullOrWhiteSpace(Target))
            throw new InvalidOperationException("sender and target are required");
        foreach (var artifact in Artifacts)
            artifact.Validate();
    }

    public bool IsExpired(DateTimeOffset? now = null) =>
        ExpiresAt is { } expires && expires <= (now ?? DateTimeOffset.UtcNow);
}
