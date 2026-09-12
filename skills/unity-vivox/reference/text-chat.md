# Text chat

Text rides on any channel joined with `ChatCapability.TextOnly` or `TextAndAudio`, plus directed
messages that need no shared channel at all.

## Channel messages

```csharp
await VivoxService.Instance.SendChannelTextMessageAsync(channelName, message);

VivoxService.Instance.ChannelMessageReceived += OnChannelMessage;

void OnChannelMessage(VivoxMessage m) { /* m.SenderDisplayName, m.MessageText, … */ }
```

Your own sends come back through the same event with `FromSelf` set, so a chat log that appends
locally *and* on the event shows every message twice. Pick one — appending only on the event is
the honest choice, because it shows the message when it actually reached the service.

## Directed messages

```csharp
await VivoxService.Instance.SendDirectTextMessageAsync(playerId, message);

VivoxService.Instance.DirectedMessageReceived += OnDirectedMessage;
```

The method is `SendDirect…`; the event is `Directed…`. That asymmetry costs everyone one
compile error or one silent handler, and no amount of consistency-guessing fixes it. The first
argument is the recipient's `PlayerId` from Authentication — a display name here fails without
telling you the address was wrong.

## `VivoxMessage`

| Field | Notes |
|---|---|
| `ChannelName` | The channel it arrived on — **`null`** for a directed message, which is the cheapest way to tell the two apart in one handler |
| `SenderDisplayName` | As the sender set it at login. Not unique, not validated |
| `SenderPlayerId` | Stable identity; this is what a reply or a block list keys on |
| `MessageText` | The body |
| `ReceivedTime` | `DateTime` of receipt |
| `Language` | The sender's language tag, when set |
| `FromSelf` | `true` on your own channel messages, which come back through `ChannelMessageReceived`. History returns your own sent messages too, so confirm the value there against the installed package before branching on it — `ChannelName` already separates directed from channel |
| `MessageId` | Server-assigned. Without it you cannot edit or delete |

## History

Two calls: one for a channel's log, one for a whisper thread. Both are requests, so both are
awaited — the result is a `Task<IReadOnlyCollection<VivoxMessage>>`, and dropping the `await`
hands you a `Task` that a `foreach` will not compile against. Read the return shape off the
installed package before writing against it.

```csharp
var recent = await VivoxService.Instance.GetChannelTextMessageHistoryAsync(
    channelName, requestSize: 10);

var whispers = await VivoxService.Instance.GetDirectTextMessageHistoryAsync(
    playerId, requestSize: 10);
```

`requestSize` defaults to 10, and a third `ChatHistoryQueryOptions` argument narrows the window.
Both return **newest first**, which is the opposite of the order a chat log renders in — reverse
before you bind it, or the conversation reads backwards. The documented retention is 7 days, 30
with text evidence management enabled — back-end configuration, so confirm it for your project
before designing storage around it. Either way history is a convenience for a returning player
and not a store for anything the game needs to keep.

## Editing and deleting

Only the original sender may change their own message.

| | Edit | Delete | Everyone is told by |
|---|---|---|---|
| Channel | `EditChannelTextMessageAsync(channelName, messageId, newText)` | `DeleteChannelTextMessageAsync(channelName, messageId)` | `ChannelMessageEdited`, `ChannelMessageDeleted` |
| Directed | `EditDirectTextMessageAsync(messageId, newText)` | `DeleteDirectTextMessageAsync(messageId)` | `DirectedMessageEdited`, `DirectedMessageDeleted` |

Every notification carries the updated `VivoxMessage`, so a log that keeps `MessageId` on each
row can patch in place. A log that does not keep it can only append, and a deletion will appear
to do nothing.

## Rate limiting

The service throttles per player. A send button that stays enabled invites a player to hold it
down and get themselves throttled, so disable it until the send completes and surface a
try-again-shortly hint on a rate-limit failure. Automatic retry loops make the throttle worse and
are the reason a chat box sometimes stays dead for a minute after one impatient burst.
