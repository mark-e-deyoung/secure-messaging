using System.Text.Json;

var mode = Environment.GetEnvironmentVariable("SECURE_MESSAGING_FAKE_HELPER_MODE") ?? "normal";
var pidFile = Environment.GetEnvironmentVariable("SECURE_MESSAGING_FAKE_PID_FILE");
if (!string.IsNullOrWhiteSpace(pidFile))
{
    Directory.CreateDirectory(Path.GetDirectoryName(pidFile) ?? Environment.CurrentDirectory);
    await File.WriteAllTextAsync(pidFile, Environment.ProcessId.ToString());
}

var line = await Console.In.ReadLineAsync();
if (line is null)
    return 2;

string requestId;
string messageId;
try
{
    using var document = JsonDocument.Parse(line);
    requestId = document.RootElement.GetProperty("request_id").GetString() ?? string.Empty;
    messageId = document.RootElement.GetProperty("envelope").GetProperty("message_id").GetString() ?? string.Empty;
}
catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException)
{
    return 3;
}

switch (mode)
{
    case "sleep":
        await Task.Delay(TimeSpan.FromSeconds(30));
        return 0;
    case "oversize":
        Console.WriteLine(new string('x', 70 * 1024));
        return 0;
    case "malformed":
        Console.WriteLine("{not-json");
        return 0;
    case "mismatch":
        WriteResponse("wrong-" + requestId, messageId);
        return 0;
    case "stderr-flood":
        for (var i = 0; i < 128; i++)
            await Console.Error.WriteAsync(new string('e', 4096));
        await Console.Error.FlushAsync();
        WriteResponse(requestId, messageId);
        return 0;
    case "normal":
        WriteResponse(requestId, messageId);
        return 0;
    default:
        return 4;
}

static void WriteResponse(string requestId, string messageId)
{
    Console.WriteLine(JsonSerializer.Serialize(new
    {
        request_id = requestId,
        accepted = true,
        message_id = messageId,
        error_code = (string?)null
    }));
}
