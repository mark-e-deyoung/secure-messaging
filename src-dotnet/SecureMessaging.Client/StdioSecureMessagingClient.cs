using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using SemperSupra.SecureMessaging.Contracts;

namespace SemperSupra.SecureMessaging.Client;

public sealed class StdioSecureMessagingClient(string helperPath) : ISecureMessagingClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<SendResult> SendAsync(MessageEnvelope envelope, CancellationToken cancellationToken = default)
    {
        envelope.Validate();
        if (string.IsNullOrWhiteSpace(helperPath))
            throw new InvalidOperationException("Secure Messaging helper path is required.");

        var request = new StdioRequest
        {
            Operation = "send",
            RequestId = Guid.NewGuid().ToString("N"),
            Envelope = envelope
        };

        var startInfo = new ProcessStartInfo
        {
            FileName = helperPath,
            Arguments = "--stdio-once",
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = startInfo };
        if (!process.Start())
            throw new InvalidOperationException("Secure Messaging helper could not be started.");

        var serialized = JsonSerializer.Serialize(request, JsonOptions);
        await process.StandardInput.WriteLineAsync(serialized.AsMemory(), cancellationToken);
        await process.StandardInput.FlushAsync(cancellationToken);
        process.StandardInput.Close();

        var responseLine = await process.StandardOutput.ReadLineAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);

        if (process.ExitCode != 0 || string.IsNullOrWhiteSpace(responseLine))
            return new SendResult(false, envelope.MessageId, "helper_failed");

        var response = JsonSerializer.Deserialize<StdioResponse>(responseLine, JsonOptions)
            ?? throw new InvalidOperationException("Secure Messaging helper returned an invalid response.");

        if (!string.Equals(response.RequestId, request.RequestId, StringComparison.Ordinal))
            throw new InvalidOperationException("Secure Messaging helper response request_id mismatch.");

        return new SendResult(response.Accepted, response.MessageId ?? envelope.MessageId, response.ErrorCode);
    }

    private sealed record StdioRequest
    {
        [JsonPropertyName("op")]
        public required string Operation { get; init; }

        [JsonPropertyName("request_id")]
        public required string RequestId { get; init; }

        [JsonPropertyName("envelope")]
        public required MessageEnvelope Envelope { get; init; }
    }

    private sealed record StdioResponse
    {
        [JsonPropertyName("request_id")]
        public required string RequestId { get; init; }

        [JsonPropertyName("accepted")]
        public bool Accepted { get; init; }

        [JsonPropertyName("message_id")]
        public string? MessageId { get; init; }

        [JsonPropertyName("error_code")]
        public string? ErrorCode { get; init; }
    }
}
