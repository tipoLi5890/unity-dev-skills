# Voice channels

## Three channel types

| Type | Join with | For |
|---|---|---|
| Non-positional (group) | `JoinGroupChannelAsync` | Party, team, lobby, guild — everyone hears everyone at equal volume |
| Echo | `JoinEchoChannelAsync` | Your own audio comes back to you. A microphone test, not a game feature |
| Positional (3D) | `JoinPositionalChannelAsync` | Proximity voice attenuated by distance and direction |

```csharp
Task JoinGroupChannelAsync(
    string channelName,
    ChatCapability chatCapability,
    ChannelOptions channelOptions = null);

Task JoinEchoChannelAsync(
    string channelName,
    ChatCapability chatCapability,
    ChannelOptions channelOptions = null);

Task JoinPositionalChannelAsync(
    string channelName,
    ChatCapability chatCapability,
    Channel3DProperties positionalChannelProperties,
    ChannelOptions channelOptions = null);
```

The returned `Task` completes when the join request has been sent. The join itself lands on
`ChannelJoined(string channelName)`. Bind that first, then call, and do the roster and transmit
work inside the handler — this is the one rule that separates a working integration from a
silent one.

## `ChatCapability`

`TextOnly`, `AudioOnly`, `TextAndAudio`. It is decided at join time and cannot be widened
afterwards; a lobby that might later want voice joins as `TextAndAudio` from the start, with the
input device muted, rather than leaving and rejoining.

## `ChannelOptions`

Optional, and the usual reason to pass it is to make this channel the active transmission target
as part of the join. Leave it `null` to join without touching where your voice currently goes —
which is what you want when a player is in a team channel and steps into a proximity one.

## Positional channels

`Channel3DProperties` decides how distance turns into attenuation:

| Field | Meaning |
|---|---|
| `AudibleDistance` | Past this, a participant cannot be heard at all |
| `ConversationalDistance` | Inside this, a participant is at full volume |
| `AudioFadeIntensityByDistance` | How steeply the level drops between those two radii |
| `AudioFadeModel` | `InverseByDistance`, `LinearByDistance`, `ExponentialByDistance` |

```csharp
var props = new Channel3DProperties(
    audibleDistance: 50,
    conversationalDistance: 5,
    audioFadeIntensityByDistance: 1.0f,
    audioFadeModel: AudioFadeModel.InverseByDistance);

await VivoxService.Instance.JoinPositionalChannelAsync(
    "world-proximity", ChatCapability.AudioOnly, props);
```

Positions do not update themselves. Push them from whatever represents the listener — usually
the player camera — with

```csharp
VivoxService.Instance.Set3DPosition(speakerObject, channelName);
```

called on a regular cadence rather than blindly every frame; the network cost is per update, and
a player who has not moved does not need one. A proximity channel above 200 participants is the
enterprise Large 3D Channels setting, not something a client flag turns on.

## Ceilings

**10 non-positional channels per user. 200 participants per channel.** Both surface as
`20502 VxXmppServerErrorServiceUnavailable`, an error whose text names neither limit — so a
feature that opens a channel per squad, per raid or per zone should leave the previous one
explicitly rather than letting them accumulate until the eleventh join fails on one unlucky
player.

## Leaving

```csharp
await VivoxService.Instance.LeaveChannelAsync(channelName);
await VivoxService.Instance.LeaveAllChannelsAsync();
```

Each exit fires `ChannelLeft(string channelName)` — one per channel, so a `LeaveAllChannelsAsync`
produces several. Leave on the transition, not in `OnApplicationQuit`; the latter is not
reliably reached on mobile.

## Microphone access

Joining an `AudioOnly` or `TextAndAudio` channel needs the microphone before the join, not after.

- **Android** — request `android.permission.RECORD_AUDIO` at runtime through
  `UnityEngine.Android.Permission.RequestUserPermission(Permission.Microphone)`. The constant
  reads back as exactly that string. The manifest entry is necessary and not sufficient.
- **iOS** — set the microphone usage description in Player Settings; it is exposed to build
  scripts as `PlayerSettings.iOS.microphoneUsageDescription`, so CI can assert it is non-empty
  before a submission.
- **Desktop** — the OS prompts on first capture; nothing to write.
- **Web** — capture is only granted inside a user gesture, so the first audio-capable join has
  to hang off a button press.

## Muting

| Goal | Call | Reach |
|---|---|---|
| Stop sending my voice anywhere | `VivoxService.Instance.MuteInputDevice()` / `UnmuteInputDevice()`, read `IsInputDeviceMuted` | Local capture. Also the push-to-talk primitive |
| Stop hearing one player | `participant.MutePlayerLocally()` / `UnmutePlayerLocally()` on the `VivoxParticipant` | This client only; the other player is not told, others still hear them |
| Silence a player for everyone | Privileged, server-minted token | Moderation — see `reference/init-and-login.md` |

A UI that offers "mute" without saying which of the three it means will be reported as a bug by
whichever player assumed the other meaning.
