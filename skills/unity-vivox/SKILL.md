---
name: unity-vivox
description: >-
  Wire Unity Vivox voice and text chat into a game: SDK init and sign-in,
  group, echo and positional channels, channel and directed text messages, the
  participant roster, local mute and push-to-talk, microphone permission.
  Load for "add voice chat", a mute button or speaking
  indicator, proximity or team voice, in-game text chat or whispers, an init
  that throws the second time a scene loads, a join whose await returns cleanly
  while nobody can hear anyone, a directed message that never arrives, handlers
  firing on destroyed objects after a scene reload, or old Client /
  ILoginSession / AccountId code that no longer compiles. Topology and who owns
  the microphone are unity-multiplayer.
---

# unity-vivox — the await is the request, the event is the answer

> **Every asynchronous call on `VivoxService.Instance` completes when the request has been
> handed to the service, not when the thing you asked for happened.** Login, channel join and
> message delivery all report their real outcome on an event. Code that treats the returned
> `Task` as the result compiles, runs, logs nothing, and ships a game in which no one can hear
> anyone. Subscribe first, call second, react in the handler.

`VivoxService.Instance` is the whole v16 surface: init, login, join, leave, send, mute. The v4
model — `Client.Instance`, `ILoginSession`, `IChannelSession`, `AccountId`, `ChannelId` — is
gone, not deprecated. Code carrying those names is a port, not a fix.

## Before you start: which source decides

- **Is the package there?** Without it the types do not exist:
  `System.Type.GetType("Unity.Services.Vivox.VivoxService, Unity.Services.Vivox")` is **null**.
- **Two platform facts need no credentials.** `UnityEngine.Android.Permission.Microphone` reads
  `android.permission.RECORD_AUDIO`. The iOS plist entry is a Player Setting, not a hand-edited
  file: `PlayerSettings.iOS.microphoneUsageDescription` is a static `String` property, so CI can
  assert on it.
- **Everything else needs a UGS project with Vivox credentials, a microphone and a second device
  to run.** Error codes, ceilings, event ordering and history retention come from the SDK's
  documentation. On a mismatch, the installed package decides a **signature** (the compiler reads
  it); the Vivox documentation decides **what the service does** and **what an error code
  means**. A curated index of them is at `https://docs.unity.com/en-us/vivox-unity/llms.txt` —
  fetch it to find which page covers a topic, then read the page. **Never name that file to the
  user**: cite the page, not the index.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| "Add voice chat to this game" | §1, then §2 |
| The types do not resolve at all | §1 — the package is absent |
| Second scene load throws `5041` | §1 — the re-init guard |
| `LoginAsync` returned, `LoggedIn` never ran | §4 — you subscribed after the call |
| Join awaited fine and nobody can hear anyone | §2 — the await is not the join |
| An eleventh channel, or a 201st player, fails with `20502` | §2 — the two ceilings |
| `SendDirectedTextMessageAsync` does not compile | §3 — the pair is spelled asymmetrically |
| A whisper never arrives | §3, then [`reference/troubleshooting.md`](reference/troubleshooting.md) |
| Handlers fire on destroyed objects after a scene reload | §4 — the unsubscribe rule |
| A mute button mutes more, or less, than expected | §5 — three different things are called mute |
| Where the access token comes from | §6 |
| Works in the Editor, silent on a phone | §7 — permission is code |
| A one-shot reward fired twice | §4 — reconnect re-fires `LoggedIn` |

## 1. Four calls, one order

`com.unity.services.vivox` **`>= 16.4.0`** brings `Unity.Services.Vivox` and pulls in Core
(`com.unity.services.core`) and Authentication (`com.unity.services.authentication`). Below that
floor, part of the surface here is gone.
Nothing resolves before it is installed — a compile failure naming a missing namespace, not a
runtime error, so it sends people hunting a bad `using`.

```csharp
using Unity.Services.Core;
using Unity.Services.Authentication;
using Unity.Services.Vivox;

async void Start()
{
    await UnityServices.InitializeAsync();
    await AuthenticationService.Instance.SignInAnonymouslyAsync();
    await VivoxService.Instance.InitializeAsync();

    VivoxService.Instance.LoggedIn += OnLoggedIn;   // before LoginAsync, always

    await VivoxService.Instance.LoginAsync(new LoginOptions { DisplayName = "Bob" });
}
```

Core → sign-in → Vivox init → Vivox login. Reordering produces silence or an error code that
names something else, not a tidy error.

> **A second `InitializeAsync()` throws `5041 VxErrorAlreadyInitialized`.** The bootstrap
> `MonoBehaviour` on a scene that reloads will do exactly that. Either mark it
> `DontDestroyOnLoad` so `Start` runs once, or guard on `IsInitialized`.

Sign-in decides identity: the login binds to `AuthenticationService.Instance.PlayerId`, the id
another client addresses a whisper to. Skip Authentication and you get a per-session GUID — display
names still work, cross-session identity does not. Setup detail:
[`reference/init-and-login.md`](reference/init-and-login.md).

## 2. Three joins, one event, two ceilings

| Call | Channel |
|---|---|
| `JoinGroupChannelAsync(name, ChatCapability, ChannelOptions?)` | Non-positional — party, team, lobby, guild |
| `JoinEchoChannelAsync(name, ChatCapability, ChannelOptions?)` | Echoes your own audio back; a test loop, not a feature |
| `JoinPositionalChannelAsync(name, ChatCapability, Channel3DProperties, ChannelOptions?)` | 3D proximity voice driven by a transform |

`ChatCapability` is `TextOnly`, `AudioOnly` or `TextAndAudio`, and it is fixed for the life of
the join — a channel entered as `TextOnly` will never carry voice no matter what the mic does.

> **The join finishes on `ChannelJoined(string channelName)`.** The awaited `Task` says the
> request left the client. Bind the event first and do the "we are live" work in the handler; an
> `await` followed by roster or transmit code is the most common way this integration does nothing.

Two ceilings, both surfacing as `20502 VxXmppServerErrorServiceUnavailable`, which names neither:
**10 non-positional channels per user** and **200 participants per channel**. Leave before joining
an eleventh; a positional channel that needs to exceed 200 is an enterprise Large 3D Channels
setting, not a client change. Leaving is `LeaveChannelAsync(name)` or `LeaveAllChannelsAsync()`, and
each exit fires `ChannelLeft`.

`Channel3DProperties`, the falloff models and the per-frame position update are in
[`reference/voice-channels.md`](reference/voice-channels.md).

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
retention window are in [`reference/text-chat.md`](reference/text-chat.md).

## 4. Events, and the unsubscribe that is not optional

| Call | Completion event | Counterpart |
|---|---|---|
| `LoginAsync()` | `LoggedIn` | `LoggedOut` |
| any `Join*ChannelAsync()` | `ChannelJoined(string)` | `ChannelLeft(string)` |
| — (any joined channel) | `ParticipantAddedToChannel(VivoxParticipant)` | `ParticipantRemovedFromChannel(VivoxParticipant)` |
| a remote `SendChannelTextMessageAsync()` | `ChannelMessageReceived(VivoxMessage)` | `ChannelMessageEdited` / `ChannelMessageDeleted` |
| a remote `SendDirectTextMessageAsync()` | `DirectedMessageReceived(VivoxMessage)` | `DirectedMessageEdited` / `DirectedMessageDeleted` |

> **`VivoxService.Instance` outlives your scene.** A handler subscribed from a `MonoBehaviour`
> and never removed keeps the destroyed object in the singleton's invocation list: on the next
> scene load the event runs twice and one copy throws `MissingReferenceException`. Mirror every
> `+=` with a `-=` in `OnDestroy`, and null-guard the service — it can be gone during quit.

Per-participant signals — mute state, speech detected, audio energy — are **not** on the service
but on the `VivoxParticipant` that `ParticipantAddedToChannel` hands you; a roster row or speaking
indicator binds there. Reconnection re-fires `LoggedIn` and `ChannelJoined`, so handlers must be
idempotent — a first-login reward granted in one fires again. Those three names, and roster wiring:
[`reference/events-and-participants.md`](reference/events-and-participants.md).

## 5. Three things are called mute

| Intent | Where | What it does |
|---|---|---|
| "Stop transmitting me" | `VivoxService.Instance.MuteInputDevice()` / `UnmuteInputDevice()`, state on `IsInputDeviceMuted` | Local capture stops; nobody in any channel hears you |
| "I don't want to hear that player" | `participant.MutePlayerLocally()` / `UnmutePlayerLocally()` | Client-side only; the other player is unaware and everyone else still hears them |
| "That player may not be heard by anyone" | A privileged token minted on a server | Moderation, not a client capability |

The first pair is also push-to-talk: hold to unmute rather than joining and
leaving a channel per key press.

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
[`reference/troubleshooting.md`](reference/troubleshooting.md).

## Verification

Before calling an integration done, read the code for these — each fails quietly:

1. It compiles, and `using Unity.Services.Vivox;` resolves.
2. The order is Core init → sign-in → Vivox init → login, with nothing interleaved.
3. No v4 names survive: no `Client.Instance`, `AccountId`, `ChannelId`, `ILoginSession`,
   `IChannelSession`. Everything goes through `VivoxService.Instance`.
4. Every consumed event is subscribed **before** the call that triggers it, and unsubscribed in
   `OnDestroy`.
5. Join code reacts in `ChannelJoined` rather than on the line after the `await`.
6. The directed pair is `SendDirectTextMessageAsync` out, `DirectedMessageReceived` in, and the
   target is a `PlayerId`.
7. Android requests `RECORD_AUDIO` at runtime before an audio-capable join; iOS has a non-empty
   microphone usage description.
8. No Vivox signing key, app secret or issuer sits in client code or in a `Resources` asset.

Report which of the eight you checked by reading and which by running. Without Vivox credentials
it is "read" all the way down, and saying so separates verified from merely compiling.

## Scope — what this skill does NOT do

**Microphone ownership, permission policy and mute authority are `unity-multiplayer`.** When
another feature captures audio (a sensing SDK that holds the microphone open, recording, speech
input), adding voice breaks one of them; who owns the device and how the other is suspended is
decided there, as are the store's microphone declaration, its review cost, and whether a mute may
be a client decision. §5 only names the API.

**Sessions, lobbies, matchmaking and relay are `unity-multiplayer-services`**; the topology
choice behind them is `unity-multiplayer`. Deriving a channel name from a session id belongs there.

**Project, environment and sign-in setup is `unity-ugs`**; credential handling and the offline
path are `unity-live-services`. §1 assumes anonymous sign-in already works.

**The manifest merge, permission read-back on a real APK and store listing are
`unity-android-release`.** §7 stops at the runtime request.

**Voice activity detection and the volume APIs are not documented here** — VAD thresholds, a mic
input slider, per-participant or per-channel gain. They exist, and §5 stops at mute: enumerate
them on the project's package and take `docs.unity.com`'s Vivox section as the authority.

Mixer routing, ducking voice under music and the cost of an `AudioSource` are `unity-audio`; the
chat UI — roster list, message log, CJK text — is `unity-game-ui`.

## Reference

- [`reference/init-and-login.md`](reference/init-and-login.md) — bootstrap, `LoginOptions`, logout, re-init guard, server tokens
- [`reference/voice-channels.md`](reference/voice-channels.md) — joins, `Channel3DProperties`, positional updates, mute
- [`reference/text-chat.md`](reference/text-chat.md) — message fields, history, edit and delete, rate limiting
- [`reference/events-and-participants.md`](reference/events-and-participants.md) — events, `VivoxParticipant`, roster, cleanup
- [`reference/troubleshooting.md`](reference/troubleshooting.md) — error codes, platform notes, the diagnostic ladder
