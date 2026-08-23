using SemperSupra.SecureMessaging.Contracts;

namespace SemperSupra.SecureMessaging.Client;

public interface ISecureMessagingClient
{
    Task<SendResult> SendAsync(MessageEnvelope envelope, CancellationToken cancellationToken = default);
}

public sealed record SendResult(bool Accepted, string MessageId, string? ErrorCode = null);
