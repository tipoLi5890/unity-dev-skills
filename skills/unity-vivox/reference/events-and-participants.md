# Events, participants and lifecycle

## Service events

All on `VivoxService.Instance`, all subscribed **before** the call that produces them.

| Event | Signature | Fires when |
|---|---|---|
| `LoggedIn` | `Action` | A login succeeds — including a reconnect |
| `LoggedOut` | `Action` | `LogoutAsync`, or the connection dropped |
| `ChannelJoined` | `Action<string>` | Any `Join*ChannelAsync` completes |
| `ChannelLeft` | `Action<string>` | A leave, a `LeaveAllChannelsAsync`, or a disconnect — once per channel |
| `ParticipantAddedToChannel` | `Action<VivoxParticipant>` | Anyone enters a channel you are in, yourself included |
| `ParticipantRemovedFromChannel` | `Action<VivoxParticipant>` | Anyone leaves |
| `ChannelMessageReceived` | `Action<VivoxMessage>` | A channel text message arrives |
| `ChannelMessageEdited` / `ChannelMessageDeleted` | `Action<VivoxMessage>` | A channel message changes |
| `DirectedMessageReceived` | `Action<VivoxMessage>` | A directed message arrives for you |
| `DirectedMessageEdited` / `DirectedMessageDeleted` | `Action<VivoxMessage>` | A directed message changes |

Note that you receive `ParticipantAddedToChannel` for yourself. A roster that assumes otherwise
either misses the local player or double-adds them, depending on which way it guessed.

## `VivoxParticipant`

One instance is one participation, not one person: the same player in two channels is two
objects, with independent mute state.

| Property | Use |
|---|---|
| `PlayerId` | Stable identity — the key for a roster dictionary, a block list, a directed reply |
| `DisplayName` | What they chose at login. Display only |
| `ChannelName` | Which channel this participation belongs to |
| `IsSelf` | The local player |
| `IsMuted` | Locally muted by this client |
| `AudioEnergy` | Continuous 0.0–1.0, meant for a VU meter |
| `SpeechDetected` | The service's judgement that the energy is speech rather than noise |

Drive a speaking indicator from `SpeechDetected` and a level meter from `AudioEnergy`. Using
`AudioEnergy` with a hand-picked threshold for the indicator is how a keyboard, a fan or a
breath ends up lighting somebody's icon.

## Per-participant events

`ParticipantMuteStateChanged`, `ParticipantSpeechDetected` and `ParticipantAudioEnergyChanged`
are on the participant object, not on the service. A roster row binds and unbinds with its own
lifetime:

```csharp
VivoxParticipant _participant;

public void Bind(VivoxParticipant p)
{
    _participant = p;
    p.ParticipantMuteStateChanged += Refresh;
    p.ParticipantSpeechDetected   += Refresh;
}

void OnDestroy()
{
    if (_participant == null) return;
    _participant.ParticipantMuteStateChanged -= Refresh;
    _participant.ParticipantSpeechDetected   -= Refresh;
}
```

`ParticipantAudioEnergyChanged` fires far more often than the other two. Bind it only on rows
that actually draw a meter, and do the drawing from the cached value in `Update` rather than
rebuilding UI inside the handler.

## Cleanup

`VivoxService.Instance` lives across scene loads. Every subscription made from a
`MonoBehaviour` keeps that object reachable from the service's invocation list after the scene
that owned it is gone, and the next load adds a second subscriber beside the first. What you see
is a handler running twice, one of the two throwing `MissingReferenceException` on a destroyed
component — reported as "voice stopped working after returning to the menu".

The discipline is dull and complete: subscribe in `Awake` or `Start`, unsubscribe the identical
list in `OnDestroy`, and null-guard `VivoxService.Instance` because during application quit it
may already be gone.

## Reconnection

A network blip reconnects on its own, re-firing `LoggedIn` and `ChannelJoined` for the channels
that were joined before it. Handlers must be safe to run more than once per session: rebuilding a
roster is fine, granting a first-login reward or logging a session-start analytics event is not.
Guard the one-shot work with state you own, not with the assumption that the event is one.
