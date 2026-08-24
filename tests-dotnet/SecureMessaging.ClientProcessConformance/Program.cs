using System.Diagnostics;
using System.Text.Json;
using SemperSupra.SecureMessaging.Client;
using SemperSupra.SecureMessaging.Contracts;

if (args.Length != 1)
    throw new InvalidOperationException("Pass the absolute synthetic helper executable path.");

var helperPath = Path.GetFullPath(args[0]);
if (!File.Exists(helperPath))
    throw new InvalidOperationException($"Synthetic helper not found: {helperPath}");

var body = JsonDocument.Parse("{\"kind\":\"synthetic-process-test\"}").RootElement.Clone();
MessageEnvelope NewEnvelope() => new()
{
    MessageId = Guid.NewGuid().ToString(),
    MessageType = "example.process-test",
    Sender = "@sender:example.test",
    Target = "@target:example.test",
    CreatedAt = DateTimeOffset.UtcNow,
    ExpiresAt = DateTimeOffset.UtcNow.AddMinutes(5),
    IdempotencyKey = Guid.NewGuid().ToString("N"),
    Body = body
};

async Task<SendResult> RunModeAsync(string mode, TimeSpan? timeout = null)
{
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_HELPER_MODE", mode);
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_PID_FILE", null);
    var client = new StdioSecureMessagingClient(helperPath, timeout ?? TimeSpan.FromSeconds(5));
    return await client.SendAsync(NewEnvelope());
}

var normal = await RunModeAsync("normal");
Require(normal.Accepted && normal.ErrorCode is null, "normal helper response failed");

var malformed = await RunModeAsync("malformed");
Require(!malformed.Accepted && malformed.ErrorCode == "helper_invalid_response", "malformed response did not fail closed");

var mismatch = await RunModeAsync("mismatch");
Require(!mismatch.Accepted && mismatch.ErrorCode == "helper_response_mismatch", "request_id mismatch did not fail closed");

var oversized = await RunModeAsync("oversize");
Require(!oversized.Accepted && oversized.ErrorCode == "helper_response_too_large", "oversized response did not fail closed");

var stderrFlood = await RunModeAsync("stderr-flood");
Require(stderrFlood.Accepted && stderrFlood.ErrorCode is null, "stderr drain deadlocked or changed the response");

var timeoutPidFile = Path.Combine(Path.GetTempPath(), "secure-messaging-timeout-" + Guid.NewGuid().ToString("N") + ".pid");
try
{
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_HELPER_MODE", "sleep");
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_PID_FILE", timeoutPidFile);
    var timeoutClient = new StdioSecureMessagingClient(helperPath, TimeSpan.FromMilliseconds(300));
    var timedOut = await timeoutClient.SendAsync(NewEnvelope());
    Require(!timedOut.Accepted && timedOut.ErrorCode == "helper_timeout", "hung helper did not return helper_timeout");
    await RequireProcessGoneAsync(timeoutPidFile);
}
finally
{
    File.Delete(timeoutPidFile);
}

var cancelPidFile = Path.Combine(Path.GetTempPath(), "secure-messaging-cancel-" + Guid.NewGuid().ToString("N") + ".pid");
try
{
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_HELPER_MODE", "sleep");
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_PID_FILE", cancelPidFile);
    var cancelClient = new StdioSecureMessagingClient(helperPath, TimeSpan.FromSeconds(5));
    using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(300));
    try
    {
        await cancelClient.SendAsync(NewEnvelope(), cancellation.Token);
        throw new InvalidOperationException("Caller cancellation was swallowed.");
    }
    catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
    {
        // Expected: caller cancellation remains caller-visible while the helper process is killed.
    }
    await RequireProcessGoneAsync(cancelPidFile);
}
finally
{
    File.Delete(cancelPidFile);
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_HELPER_MODE", null);
    Environment.SetEnvironmentVariable("SECURE_MESSAGING_FAKE_PID_FILE", null);
}

Console.WriteLine("Secure Messaging helper process conformance: PASS");

static void Require(bool condition, string message)
{
    if (!condition)
        throw new InvalidOperationException(message);
}

static async Task RequireProcessGoneAsync(string pidFile)
{
    for (var i = 0; i < 50 && !File.Exists(pidFile); i++)
        await Task.Delay(20);
    if (!File.Exists(pidFile))
        throw new InvalidOperationException("Synthetic helper did not record its PID.");

    var pid = int.Parse(await File.ReadAllTextAsync(pidFile));
    for (var i = 0; i < 50; i++)
    {
        try
        {
            using var process = Process.GetProcessById(pid);
            if (process.HasExited)
                return;
        }
        catch (ArgumentException)
        {
            return;
        }
        await Task.Delay(20);
    }
    throw new InvalidOperationException($"Helper process {pid} remained alive after timeout/cancellation.");
}
