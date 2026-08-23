using System.Text.Json;
using System.Text.Json.Serialization;

namespace SemperSupra.SecureMessaging.Contracts;

public sealed record ArtifactLocation
{
    [JsonPropertyName("provider")]
    public required string Provider { get; init; }

    [JsonPropertyName("locator")]
    public required string Locator { get; init; }

    [JsonPropertyName("attributes")]
    public Dictionary<string, JsonElement> Attributes { get; init; } = new();
}

public sealed record ArtifactReference
{
    [JsonPropertyName("artifact_id")]
    public required string ArtifactId { get; init; }

    [JsonPropertyName("sha256")]
    public required string Sha256 { get; init; }

    [JsonPropertyName("size")]
    public long Size { get; init; }

    [JsonPropertyName("media_type")]
    public string? MediaType { get; init; }

    [JsonPropertyName("logical_name")]
    public string? LogicalName { get; init; }

    [JsonPropertyName("locations")]
    public IReadOnlyList<ArtifactLocation> Locations { get; init; } = Array.Empty<ArtifactLocation>();

    public void Validate()
    {
        if (Sha256.Length != 64 || Sha256.Any(c => !Uri.IsHexDigit(c)))
            throw new InvalidOperationException("sha256 must be a 64-character hexadecimal digest");
        if (!string.Equals(ArtifactId, $"sha256:{Sha256.ToLowerInvariant()}", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("artifact_id must match sha256");
        if (Size < 0)
            throw new InvalidOperationException("size must be non-negative");
        if (Locations.Any(l => string.IsNullOrWhiteSpace(l.Provider) || string.IsNullOrWhiteSpace(l.Locator)))
            throw new InvalidOperationException("artifact locations require provider and locator");
    }
}
