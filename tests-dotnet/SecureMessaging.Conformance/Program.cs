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

ISecureMessagingClient clientContract = new StdioSecureMessagingClient("synthetic-helper-path");
if (clientContract is null)
    throw new InvalidOperationException("Client facade failed to construct.");

Console.WriteLine("Secure Messaging .NET 8 conformance: PASS");
