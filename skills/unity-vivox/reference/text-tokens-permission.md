# Text chat, access tokens, microphone permission

Moved out of SKILL.md §3, §6 and §7; same numbering. Message fields and history in depth: [`reference/text-chat.md`](text-chat.md).

## 3. Text: two pairs, one of them spelled asymmetrically

| | Send | Receive |
|---|---|---|
| Channel broadcast | `SendChannelTextMessageAsync(channelName, message)` | `ChannelMessageReceived` (`Action<VivoxMessage>`) |
| Directed, no channel needed | `SendDirectTextMessageAsync(playerId, message)` | `DirectedMessageReceived` (`Action<VivoxMessage>`) |

> **The send is `SendDirect…`, the event is `Directed…`.** Guessing consistency either way gives
> a compile error on the method or a handler that never runs. The recipient argument is the
> other player's `PlayerId`, never a display name.

`VivoxMessage` carries `ChannelName` (**null** on a directed message), `SenderDisplayName`,
`SenderPlayerId`, `MessageText`, `ReceivedTime`, `Language`, `FromSelf` and `MessageId`. Only
`MessageId` lets you edit or delete afterwards. Editing, deletion, history queries and the
retention window are in [`reference/text-chat.md`](text-chat.md).

## 6. Access tokens

With UGS Authentication in the chain, Vivox mints its own access tokens once sign-in completes.
There is no token code to write for the standard flow; a tutorial signing tokens in a client is
describing the other path.

That other path — server-minted Vivox Access Tokens — is for a non-UGS identity system, or for
privileged actions: kick, mute-all, transcription, join-muted, and channel-scoped entry rights.

> **The signing key never ships in the build.** Any player can read a client-side HMAC key out
> of the binary, and it grants exactly the moderation powers it was added for. Mint on a server
> you control and hand the client the finished token.

## 7. Permission is code, not a manifest line

**Android.** The manifest entry alone changes nothing at runtime on a modern API level. Request
before the first audio-capable join and wait for the answer:

```csharp
if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(
        UnityEngine.Android.Permission.Microphone))
    UnityEngine.Android.Permission.RequestUserPermission(
        UnityEngine.Android.Permission.Microphone);
```

`Permission.Microphone` reads back as `android.permission.RECORD_AUDIO`, the string the merged
manifest needs — one name, not two. `HasUserAuthorizedPermission`, `RequestUserPermission` and
`RequestUserPermissions` sit beside it on the same class. The request is fire-and-callback, not
awaitable: joining on the next line is a race that passes only where permission was granted.

**iOS.** `NSMicrophoneUsageDescription` comes from `PlayerSettings.iOS.microphoneUsageDescription`,
a plain `String` property, so CI can assert it is non-empty. Missing or empty, the OS kills the
app at the first audio-capable join — a crash on joining, not a denied prompt — and App Review
rejects it. The OS recording indicator stays lit while Vivox captures; that cannot be suppressed.

**Web and console.** Browsers grant capture only inside a user gesture, so the first
audio-capable join belongs on a button, not in `Start`. Console builds need NDA-gated packages
the public registry does not carry. Platform notes:
[`reference/troubleshooting.md`](troubleshooting.md).
