using System.Text.Json;
using SemperSupra.SecureMessaging.Client;
using SemperSupra.SecureMessaging.Contracts;

var repoRoot = Directory.GetCurrentDirectory();
var vectorPath = Path.Combine(repoRoot, "test-vectors", "message-envelope-basic.json");
if (!File.Exists(vectorPath))
    throw new InvalidOperationException($"Missing canonical test vector: {vectorPath}");

var json = await File.ReadAllTextAsync(vectorPath);
var envelope = JsonSerializer.Deserialize<MessageEnvelope>(json)
    ?? throw new InvalidOperationException("Canonical envelope could not be deserialized.");

envelope.Validate();
if (envelope.MessageType != "example.available")
    throw new InvalidOperationException("message_type mismatch");
if (envelope.Sender != "@sender:example.org")
    throw new InvalidOperationException("sender mismatch");
if (envelope.Artifacts.Count != 0)
    throw new InvalidOperationException("artifact vector mismatch");

var roundTripJson = JsonSerializer.Serialize(envelope);
var roundTrip = JsonSerializer.Deserialize<MessageEnvelope>(roundTripJson)
    ?? throw new InvalidOperationException("Round-trip deserialize failed.");
roundTrip.Validate();
if (roundTrip.MessageId != envelope.MessageId)
    throw new InvalidOperationException("message_id changed during round trip");

var helperPath = Environment.GetEnvironmentVariable("SECURE_MESSAGING_HELPER_PATH");
if (string.IsNullOrWhiteSpace(helperPath))
{
    ISecureMessagingClient contractOnly = new StdioSecureMessagingClient("synthetic-helper-path");
    if (contractOnly is null)
        throw new InvalidOperationException("Client facade failed to construct.");
    Console.WriteLine("Secure Messaging .NET 8 contract conformance: PASS (helper launch not requested)");
    return;
}

if (!File.Exists(helperPath))
    throw new InvalidOperationException($"SECURE_MESSAGING_HELPER_PATH does not exist: {helperPath}");
if (!string.Equals(Environment.GetEnvironmentVariable("SECURE_MESSAGING_TEST_TRANSPORT"), "memory", StringComparison.Ordinal))
    throw new InvalidOperationException("Packaged helper conformance requires SECURE_MESSAGING_TEST_TRANSPORT=memory to remain offline.");

var smokeEnvelope = envelope with
{
    MessageId = Guid.NewGuid().ToString(),
    CreatedAt = DateTimeOffset.UtcNow,
    ExpiresAt = DateTimeOffset.UtcNow.AddMinutes(5),
    IdempotencyKey = "dotnet-package-smoke-" + Guid.NewGuid().ToString("N")
};

ISecureMessagingClient client = new StdioSecureMessagingClient(helperPath, TimeSpan.FromSeconds(20));
var result = await client.SendAsync(smokeEnvelope);
if (!result.Accepted)
    throw new InvalidOperationException($"Packaged helper did not accept the synthetic request: {result.ErrorCode}");
if (!string.Equals(result.MessageId, smokeEnvelope.MessageId, StringComparison.Ordinal))
    throw new InvalidOperationException("Packaged helper returned the wrong message_id.");
if (result.ErrorCode is not null)
    throw new InvalidOperationException($"Packaged helper returned unexpected error_code: {result.ErrorCode}");

Console.WriteLine("Secure Messaging .NET 8 packaged-helper conformance: PASS");
