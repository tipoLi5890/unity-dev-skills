---
name: unity-multiplayer
description: >-
  Choosing and living with a multiplayer topology in Unity, plus in-game
  voice. Load when deciding between peer-to-peer, a listen server and
  dedicated servers, when adding lobbies, sessions, matchmaking or relay,
  when adding Vivox voice or text chat, or when voice chat and another
  microphone feature in the same project fight over the device's microphone.
  Owns the choice that is expensive to reverse, the state-ownership boundary
  between lobby and gameplay, reconnection as a first-class case, and the
  platform-level conflicts. Persistent player data is unity-live-services.
---

# unity-multiplayer — the decision, and what it costs later

> **Topology is the one decision here that is expensive to reverse.** It determines who is
> allowed to be believed, and that assumption ends up in every gameplay system. Changing it later
> is not a networking change; it is a rewrite of everything that trusted the client.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Deciding how players connect at all | §1 |
| A player cheated and it affected someone else | §1 — the topology gave them authority |
| Lobby says one thing, the game says another | §2 |
| A player lost signal and the session broke | §2 reconnection |
| Voice chat killed another microphone feature | §3 |
| Mute does not take effect immediately | §3 |
| It works in two editor windows and not on two phones | §4 |

**When to jump.** Two things are decided here and nowhere else: the topology, and who owns the
microphone. The calls that follow from them are next door — `unity-multiplayer-services` for the
Sessions API, matchmaking, relay and dedicated-server sessions, `unity-vivox` for channels, tokens
and the participant roster. Go there once §1's two questions have an answer, and come back before
shipping: the state-ownership boundary in §2 and the mic handover in §3 are invisible from inside
either API.

## 1. Choosing a topology

| Topology | Choose when | The cost you are accepting |
|---|---|---|
| **Peer-to-peer** | Small sessions, co-op, latency matters more than trust, no competitive stakes | No authority anywhere; every peer can lie; NAT traversal needs relay |
| **Listen server** (one player hosts) | Casual sessions, no dedicated hosting budget | The host has authority **and** an advantage; host migration is hard and is usually deferred until it hurts |
| **Dedicated servers** | Competitive, ranked, persistent worlds, anything with real money attached | Real hosting cost and real ops; you now run a fleet |

Two questions settle most cases:

1. **Does a cheating player harm anyone but themselves?** If yes, you need server authority — a
   listen server gives it to a player.
2. **Does the session outlive any one participant?** If yes, you need something that is not a
   participant.

Answer them before the first `NetworkBehaviour`. Retrofitting authority means revisiting every
system that assumed a local value was true.

## 2. Who owns which state

Draw this once, explicitly, and keep it near the code:

- **Session/lobby state** (who is in, ready flags, settings) — owned by the lobby service. Do not
  mirror it into gameplay state; two sources of truth diverge on reconnect.
- **Gameplay state** — owned by whatever the topology made authoritative.
- **Presentation state** (animation, VFX, local prediction) — always local, always disposable.

> **Reconnection is a first-class case, not an error path.** A player will lose signal in a
> tunnel. Decide what their character does while they are gone, and what they can rejoin into,
> before shipping.

Anything persistent — currency, unlocks, progression earned in a session — is
`unity-live-services`, and it is server-authoritative regardless of what topology the session
used.

## 3. Voice chat, and the microphone conflict

Voice is not just another service; it takes an exclusive-ish hold on hardware.

> **Two systems in one project cannot both own the microphone.** If the project also has a
> sensing SDK that holds the microphone open, a recording feature, or speech input, adding Vivox
> will break one of them — often silently, and often only on device. A native sensing SDK is the
> hardest case: it captures continuously for as long as it runs, and will not simply yield.

Decide up front which owns the mic and how the other is suspended. This has to be a real
handover — stop the other capture, wait for it to release, start voice, and reverse it on the way
out — not a hope that the platform arbitrates.

Also:

- **Microphone permission is requested at runtime** on Android and iOS, and the iOS usage string
  is reviewed by a person. Permission denied must degrade to text chat, not to a broken session.
  Ask before the join, not after: on Android nothing prompts on your behalf, so a join that runs
  first returns cleanly into a channel where the player is inaudible.
- **A voice permission appears in the merged manifest.** Read it off the artifact —
  `unity-android-release` → `reference/artifact-verification.md` — and it becomes a store
  declaration (`unity-monetization` §3 has the same shape for ad SDKs).
- **Mute must be authoritative and instant.** A mute implemented as "stop sending" that still
  routes audio somewhere is a safety problem, not a bug.
- Positional voice needs the listener updated every frame from the same transform the game uses.
  A second, drifting source of position is the usual cause of "voice comes from the wrong place".
- **The voice service is a singleton that outlives your scene.** Handlers subscribed from a
  behaviour that is later destroyed keep firing against the dead object on the next load — "voice
  worked until we reloaded the scene" is almost always a missing unsubscribe, mirrored one for one
  against where you subscribed.
- **Channel counts are capped, and the cap is a lobby-design constraint rather than an error to
  handle at runtime.** Vivox allows one user **10 non-positional channels** at a time and **200
  participants per channel**; a design that leaves every squad, party and guild channel permanently
  joined hits that ceiling on a live server, not in testing. Decide which channels a player is in
  at each moment and leave the others.

The voice SDK's documentation is the authority on those three — the permission order, the
unsubscribe, the channel limits; `unity-vivox` carries them with the error codes and the join and
leave calls.

## 4. Testing multiplayer honestly

- **Two builds on two devices, on different networks.** Two editor instances on one machine
  share a NAT and a clock and will not reproduce the failures that matter.
- **Test with induced latency and packet loss**, not only on a good connection.
- **Test the disconnect**: kill one client mid-session; kill the host; restore the network.
- Voice: verify on device with real hardware. The editor's microphone path is not the device's,
  and on device it is competing with whatever else wants the mic.

## Scope — what this skill does NOT do

The service APIs behind these decisions. `unity-multiplayer-services` owns the Sessions API,
matchmaking, relay and dedicated-server sessions; `unity-vivox` owns channels, text chat, tokens
and the participant roster. Netcode call-by-call APIs, persistent player data
(`unity-live-services`), and server fleet operations — a provider-agnostic backend discipline
rather than a Unity one — are also elsewhere.
