---
name: unity-multiplayer-services
description: >-
  Online play on Unity Multiplayer Services (com.unity.services.multiplayer)
  through its Sessions API: create and join, join codes, a browsable game
  list, quick join, ticket matchmaking, relay or direct connectivity, host
  migration, reconnect, dedicated-server sessions. Load for: "how do players
  get into a game together", a room / party / lobby list, matchmaking into a
  playable match, Netcode for GameObjects on a session's network, code
  reaching straight for Unity.Services.Lobbies / Matchmaker / Relay, a server
  build broken by Unity.Services.Multiplayer.Server, or a ticket that finds
  nothing because the queue was never deployed. Choosing the topology is
  unity-multiplayer.
---

# unity-multiplayer-services — one session API, and the layers under it you should not reach for

> **`MultiplayerService.Instance` and `ISession` cover the whole flow** — create, find, join,
> connect, reconnect, migrate the host, tear down. Lobby, Matchmaker and Relay are what that flow
> is *made of*, not three products to assemble by hand. Code that drops to one of those clients
> directly takes on a second lifecycle to keep in step with the session's, and the composed calls
> that were doing that work for it stop being usable.

Authoritative source when specifics differ from recall: the Multiplayer Services SDK pages on
[docs.unity.com](https://docs.unity.com/). There is a curated index of those pages at
`https://docs.unity.com/en-us/mps-sdk/llms.txt` — fetch it first when you need to know **what is
documented** and where it lives, then read the page it points at. This skill stays the authority on
**how** to apply the SDK; the index is the authority on what exists.

> **The index is a tool, not a citation.** Never put that filename in front of the user — not in a
> plan, a summary, or an explanation of where an answer came from. Cite the documentation page, or
> say "the Multiplayer Services documentation". A reader handed a machine-readable index file has
> been given a dead end dressed up as a source.

When both are unreachable, the copy of the package
resolved into the project decides — read the assemblies under `Library/PackageCache/` or open the
package in Package Manager. Do not invent a signature from either. Check type names, signatures,
defaults and limits against the resolved package; when
`PackageInfo.FindForAssetPath("Packages/com.unity.services.multiplayer/package.json")` returns
null there is none, and `Unity.Services.Multiplayer.MultiplayerService` will not resolve.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| "Which call gets two players into the same game?" | §1, then [`reference/session-api.md`](reference/session-api.md) |
| "Should this use Lobby, or Relay, or Matchmaker?" | §2 — settle the requirement first; all three are below one API |
| Players join, but nothing is networked | §3 — the network is a session option, not a second start call |
| Two gameplay netcode packages in `manifest.json` | §3 — pick one |
| Server build breaks on `Unity.Services.Multiplayer.Server` types | §5 |
| Ticket matchmaking returns nothing, no error worth reading | §4 — the queue/environment does not exist yet |
| Players drain out of a running dedicated match and never refill | §5 backfill |
| Filter and sort fields for a game browser | [`reference/session-api.md`](reference/session-api.md) |
| Reconnect after a phone loses signal | §1 `ReconnectToSessionAsync`, then `unity-multiplayer` §2 |
| The plan reads like a services brochure | §6 |
| Something genuinely cannot be done through the session API | [`reference/lower-level-clients.md`](reference/lower-level-clients.md) |

## 1. The surface you implement against

`MultiplayerService.Instance` (static), or `unityServices.GetMultiplayerService()` from
`UnityServicesExtensions` once Unity Gaming Services is initialised and the player is
authenticated. Everything else hangs off it.

| Job | Call |
|---|---|
| Host a new game | `CreateSessionAsync(SessionOptions)` → `IHostSession` |
| Join by id, create it if absent | `CreateOrJoinSessionAsync(id, SessionOptions)` |
| Join by id / by join code | `JoinSessionByIdAsync`, `JoinSessionByCodeAsync` |
| Come back after a drop | `ReconnectToSessionAsync(id, ReconnectSessionOptions)` |
| Auto-pick or create by filter | `MatchmakeSessionAsync(QuickJoinOptions, SessionOptions)` |
| Ticketed matchmaking | `MatchmakeSessionAsync(MatchmakerOptions, SessionOptions, CancellationToken)` |
| Browse open games | `QuerySessionsAsync(QuerySessionsOptions)` |
| What am I already in | `GetJoinedSessionIdsAsync()` |

`ISession` is the handle afterwards: players, properties, role, `Network`, `LeaveAsync`,
`ReconnectAsync`, `RefreshAsync`, `SaveCurrentPlayerDataAsync`. Cast it to `IHostSession` when
this peer hosts, `IServerSession` on a dedicated server. Every async call above throws
`SessionException`; catch that and read its session error type rather than the message string.

Full property tables, defaults, limits, filter and sort enums, the network model and the editor
components: [`reference/session-api.md`](reference/session-api.md).

## 2. Ground the recommendation before making one

> **Read the project first, then ask one question, then recommend.** The dimension that changes
> the answer — who runs the match, how players find each other, what happens when the host walks
> away — is usually already decided somewhere in the repo. Recommending before looking produces a
> plan that contradicts the manifest.

Order: what the user already said → what is in the project (`Packages/manifest.json`, existing
networking scripts, server build targets, deployment assets) → a short, high-level question, but
only for a dimension that would change the recommendation and is not visible in either.

The six dimensions and what each maps to internally are in
[`reference/requirement-dimensions.md`](reference/requirement-dimensions.md).

## 3. Networking is a session option, not a second system

The gameplay network comes up as part of create / join / matchmake / reconnect when the options
carry it. There is no separate "now start netcode" step on that path.

```csharp
var options = new SessionOptions { MaxPlayers = 4 }.WithRelayNetwork();
var session  = await MultiplayerService.Instance.CreateSessionAsync(options);
```

- `WithRelayNetwork()` — brokered connectivity, the default choice when players sit behind home
  routers. `WithDirectNetwork()` — a listen/publish address you control. `WithDistributedAuthorityNetwork()`,
  `WithNetworkHandler()` for a custom `INetworkHandler`, `WithHostMigration()`, `WithPlayerName()`.
- **Session metadata alone needs no gameplay netcode package.** Rooms, codes, lists and properties
  work on `com.unity.services.multiplayer` by itself. Add a netcode package only when a simulation
  has to be shared.
- **Exactly one gameplay stack.** Netcode for GameObjects is `com.unity.netcode.gameobjects`.
  Netcode for Entities is `com.unity.netcode`; `com.unity.netcode.entities` is **not a package
  id** — the registry returns 404 for it. Do not put both stacks in one project, and do not
  introduce a stack the project did not already choose.

## 4. What must exist in the cloud before the code runs

Initialisation and authentication are required for every path — `com.unity.services.core` and
`com.unity.services.authentication`. Past that, each workflow has its own cloud-side
prerequisite, and the usual "matchmaking silently finds nothing" is a queue that was never
deployed. The table is
[`reference/cloud-prerequisites.md`](reference/cloud-prerequisites.md).

## 5. Dedicated servers are a separate assembly

`Unity.Services.Multiplayer.Server` compiles only when `UNITY_SERVER` or `ENABLE_UCS_SERVER` is
defined. So any assembly of yours that touches it must be excluded from client builds the same
way — `#if UNITY_SERVER` around the references, or `defineConstraints: ["UNITY_SERVER"]` in the
`.asmdef`. Skip that and the client build fails on types it was never meant to see.

Entry point is `MultiplayerServerService.Instance` / `GetMultiplayerServerService()` with three
create methods returning `IServerSession` — the supported way in, since `GetSessionAsync` may be
`internal` in the resolved package; backfill (`WithBackfillingConfiguration`,
`StartBackfillingAsync`, `StopBackfillingAsync`) is what refills a running allocation.
[`reference/dedicated-server-sessions.md`](reference/dedicated-server-sessions.md).

## 6. Write plans in the player's language

> **The user answers questions about their game, not about the SDK.** "Should players see a list
> of open games, or only join with a code?" is answerable. "Do you want Lobby or Sessions?" makes
> them learn the vendor's product split to describe their own game.

Keep product names out of questions, plans and summaries unless the user brought them up — then
mirror their wording and do not enumerate the rest. Code, file edits and technical references use
the real type and namespace names, always. Before/after phrasings:
[`reference/player-language.md`](reference/player-language.md).

## 7. Testing

**Two builds, two devices, two networks.** Two editor instances share a NAT, a clock and a disk;
they will not reproduce the failures this package exists to handle. `com.unity.multiplayer.playmode`
gives local virtual players for a first pass, not a substitute for the second device. Sessions,
matchmaking and relay need a live UGS project to run at all.

## Scope — what this skill does NOT do

Choosing the topology at all — peer-to-peer versus a hosting player versus a fleet, who is allowed
to be believed, what a disconnect means for the match, and microphone conflicts — is
`unity-multiplayer`. That decision comes first; this skill is what you call once
it is made. Voice and text chat are `unity-vivox`. Anything that has to outlive the session —
currency, unlocks, progression, leaderboards — is `unity-ugs` for the API and `unity-live-services`
for the discipline around it. Netcode's own call-by-call surface (`NetworkBehaviour`, RPCs,
`NetworkVariable`) is not here either: this skill hands the netcode stack a live connection and
stops. Server fleet operations stay with whoever runs the fleet.

## Reference

- [`reference/session-api.md`](reference/session-api.md) — `IMultiplayerService` and `ISession` in
  full: signatures, options tables with defaults and limits, filter/sort enums, the session network
  model, host migration, errors, editor components.
- [`reference/requirement-dimensions.md`](reference/requirement-dimensions.md) — how to ground a
  recommendation, and the six dimensions that change it.
- [`reference/player-language.md`](reference/player-language.md) — questions and explanations, before and after.
- [`reference/dedicated-server-sessions.md`](reference/dedicated-server-sessions.md) — the server assembly, its build
  constraints, `IMultiplayerServerService`, backfill.
- [`reference/cloud-prerequisites.md`](reference/cloud-prerequisites.md) — packages and
  cloud setup per workflow.
- [`reference/lower-level-clients.md`](reference/lower-level-clients.md) — the three lower-level
  clients, what each is for, and the two conditions that justify using one.
