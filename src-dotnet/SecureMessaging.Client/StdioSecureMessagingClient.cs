using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using SemperSupra.SecureMessaging.Contracts;

namespace SemperSupra.SecureMessaging.Client;

public sealed class StdioSecureMessagingClient(string helperPath, TimeSpan? helperTimeout = null) : ISecureMessagingClient
{
    private const int MaxResponseChars = 64 * 1024;
    private static readonly TimeSpan DefaultHelperTimeout = TimeSpan.FromSeconds(30);
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<SendResult> SendAsync(MessageEnvelope envelope, CancellationToken cancellationToken = default)
    {
        envelope.Validate();
        if (string.IsNullOrWhiteSpace(helperPath))
            throw new InvalidOperationException("Secure Messaging helper path is required.");
        if (!Path.IsPathFullyQualified(helperPath))
            throw new InvalidOperationException("Secure Messaging helper path must be absolute.");
        if (!File.Exists(helperPath))
            return new SendResult(false, envelope.MessageId, "helper_not_found");

        var timeout = helperTimeout ?? DefaultHelperTimeout;
        if (timeout <= TimeSpan.Zero || timeout == Timeout.InfiniteTimeSpan)
            throw new InvalidOperationException("Secure Messaging helper timeout must be finite and positive.");

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
            CreateNoWindow = true,
            WorkingDirectory = Path.GetDirectoryName(helperPath) ?? Environment.CurrentDirectory
        };

        using var process = new Process { StartInfo = startInfo };
        try
        {
            if (!process.Start())
                return new SendResult(false, envelope.MessageId, "helper_failed");
        }
        catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            return new SendResult(false, envelope.MessageId, "helper_failed");
        }

        using var timeoutCts = new CancellationTokenSource(timeout);
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutCts.Token);
        var token = linkedCts.Token;
        var stderrDrain = DrainAsync(process.StandardError);

        try
        {
            var serialized = JsonSerializer.Serialize(request, JsonOptions);
            await process.StandardInput.WriteLineAsync(serialized.AsMemory(), token);
            await process.StandardInput.FlushAsync(token);
            process.StandardInput.Close();

            var responseLine = await ReadBoundedLineAsync(process.StandardOutput, MaxResponseChars, token);
            await process.WaitForExitAsync(token);

            if (process.ExitCode != 0 || string.IsNullOrWhiteSpace(responseLine))
                return new SendResult(false, envelope.MessageId, "helper_failed");

            StdioResponse? response;
            try
            {
                response = JsonSerializer.Deserialize<StdioResponse>(responseLine, JsonOptions);
            }
            catch (JsonException)
            {
                return new SendResult(false, envelope.MessageId, "helper_invalid_response");
            }

            if (response is null || string.IsNullOrWhiteSpace(response.RequestId))
                return new SendResult(false, envelope.MessageId, "helper_invalid_response");
            if (!string.Equals(response.RequestId, request.RequestId, StringComparison.Ordinal))
                return new SendResult(false, envelope.MessageId, "helper_response_mismatch");

            return new SendResult(response.Accepted, response.MessageId ?? envelope.MessageId, response.ErrorCode);
        }
        catch (InvalidDataException)
        {
            TryKill(process);
            return new SendResult(false, envelope.MessageId, "helper_response_too_large");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested && timeoutCts.IsCancellationRequested)
        {
            TryKill(process);
            await WaitForExitAfterKillAsync(process);
            return new SendResult(false, envelope.MessageId, "helper_timeout");
        }
        catch (OperationCanceledException)
        {
            TryKill(process);
            await WaitForExitAfterKillAsync(process);
            throw;
        }
        finally
        {
            if (!process.HasExited)
            {
                TryKill(process);
                await WaitForExitAfterKillAsync(process);
            }
            await ObserveDrainAsync(stderrDrain);
        }
    }

    private static async Task<string?> ReadBoundedLineAsync(StreamReader reader, int maxChars, CancellationToken cancellationToken)
    {
        var builder = new StringBuilder(Math.Min(maxChars, 1024));
        var one = new char[1];
        while (true)
        {
            var read = await reader.ReadAsync(one.AsMemory(0, 1), cancellationToken);
            if (read == 0)
                return builder.Length == 0 ? null : builder.ToString();
            if (one[0] == '\n')
            {
                if (builder.Length > 0 && builder[^1] == '\r')
                    builder.Length--;
                return builder.ToString();
            }
            builder.Append(one[0]);
            if (builder.Length > maxChars)
                throw new InvalidDataException("Secure Messaging helper response exceeded the local IPC limit.");
        }
    }

    private static async Task DrainAsync(StreamReader reader)
    {
        var buffer = new char[4096];
        while (await reader.ReadAsync(buffer.AsMemory(), CancellationToken.None) > 0)
        {
            // Intentionally discard provider/helper diagnostics. They must not cross the app IPC boundary.
        }
    }

    private static async Task ObserveDrainAsync(Task drainTask)
    {
        try
        {
            await drainTask;
        }
        catch (IOException)
        {
            // Process teardown can close the redirected pipe while a read is outstanding.
        }
        catch (ObjectDisposedException)
        {
            // Process teardown closed the stream; diagnostics remain intentionally discarded.
        }
    }

    private static void TryKill(Process process)
    {
        try
        {
            if (!process.HasExited)
                process.Kill(entireProcessTree: true);
        }
        catch (InvalidOperationException)
        {
            // Process already exited.
        }
    }

    private static async Task WaitForExitAfterKillAsync(Process process)
    {
        try
        {
            if (!process.HasExited)
                await process.WaitForExitAsync(CancellationToken.None);
        }
        catch (InvalidOperationException)
        {
            // Process was never started or already disposed; nothing remains to wait for.
        }
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
