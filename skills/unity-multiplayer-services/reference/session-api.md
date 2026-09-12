# The session API in full

Everything here belongs to `Unity.Services.Multiplayer` (package `com.unity.services.multiplayer`).
Check defaults and limits against the package the project resolved before relying on a number.

- [Getting the service](#getting-the-service)
- [What it can do](#what-it-can-do)
- [Method signatures](#method-signatures)
- [Options](#options)
- [Filters and sorting](#filters-and-sorting)
- [Session configuration](#session-configuration)
- [The session network](#the-session-network)
- [Host migration](#host-migration)
- [Matchmaking results](#matchmaking-results)
- [Errors and observation](#errors-and-observation)
- [Editor components](#editor-components)

## Getting the service

`MultiplayerService.Instance` is the static accessor. The instance form is
`unityServices.GetMultiplayerService()`, an extension in `UnityServicesExtensions` — use it when
the project already passes an `IUnityServices` around rather than reaching for statics. Either way
Unity Gaming Services has to be initialised and the player authenticated first; a call before that
fails, it does not queue.

`ISession` is what every call hands back and the only handle worth storing:

| On `ISession` | For |
|---|---|
| Players, session properties, `Type`, role | Reading and reacting to who is in and what the game is set to |
| `Network` (client side) | The live connection state — see [The session network](#the-session-network) |
| `LeaveAsync`, `RefreshAsync` | Ordinary lifecycle |
| `ReconnectAsync` | Rejoining a session this peer was already in |
| `SaveCurrentPlayerDataAsync` | Pushing this player's properties back up |

Cast to `IHostSession` when this peer hosts, to `IServerSession` inside a dedicated server build.

## What it can do

| Area | Surface |
|---|---|
| Registry of joined sessions | `Sessions` (read-only map) with `SessionAdded`, `SessionRemoved`, `AddingSessionStarted`, `AddingSessionFailed` |
| Create and join | `CreateSessionAsync`, `CreateOrJoinSessionAsync`, `JoinSessionByIdAsync`, `JoinSessionByCodeAsync`, `ReconnectToSessionAsync`, `GetJoinedSessionIdsAsync` |
| Matchmaking that ends in a session | `MatchmakeSessionAsync` with either `QuickJoinOptions` (filter, retry, optionally create) or `MatchmakerOptions` (queue and ticket attributes), both alongside `SessionOptions` |
| Browsing | `QuerySessionsAsync` + `QuerySessionsOptions`; the returned `QuerySessionsResults` can `StartPolling` / `StopPolling` for a live list |

## Method signatures

```csharp
// Host a new session. Host-side handle. Throws SessionException on failure.
Task<IHostSession> CreateSessionAsync(SessionOptions sessionOptions)

// Join the session with this id, or create it under that id if nobody has.
Task<ISession> CreateOrJoinSessionAsync(string sessionId, SessionOptions sessionOptions)

// Join an existing session by id.
Task<ISession> JoinSessionByIdAsync(string sessionId, JoinSessionOptions sessionOptions = default)

// Join by the short human-readable code a host shares.
Task<ISession> JoinSessionByCodeAsync(string sessionCode, JoinSessionOptions sessionOptions = default)

// Rejoin a session this player was dropped from.
Task<ISession> ReconnectToSessionAsync(string sessionId, ReconnectSessionOptions options = default)

// Ticketed matchmaking through a deployed queue. Cancellable.
Task<ISession> MatchmakeSessionAsync(MatchmakerOptions matchOptions, SessionOptions sessionOptions,
                                     CancellationToken cancellationToken = default)

// Filter-based auto pick, retried until the timeout, optionally creating one instead.
Task<ISession> MatchmakeSessionAsync(QuickJoinOptions quickJoinOptions, SessionOptions sessionOptions)

// Browse sessions matching the query.
Task<QuerySessionsResults> QuerySessionsAsync(QuerySessionsOptions queryOptions)

// Ids of sessions this player is already in.
Task<List<string>> GetJoinedSessionIdsAsync()
```

## Options

### `SessionOptions` — create, create-or-join, matchmake

Inherits `BaseSessionOptions`.

| Property | Type | Default | Notes |
|---|---|---|---|
| `Name` | `string` | new GUID | Display name |
| `MaxPlayers` | `int` | `0` | Counts the host. **Must be set above 0 to create** — the default is not a usable value |
| `IsLocked` | `bool` | `false` | Locked sessions refuse new joins |
| `IsPrivate` | `bool` | `false` | Hidden from queries and from quick join |
| `Password` | `string` | `null` | 8–64 characters. Cannot be read back off the session afterwards |
| `SessionProperties` | `Dictionary<string, SessionProperty>` | empty | Game-specific values such as `"map"`. Cap of 20 |
| `Type` | `string` (base) | new GUID | Client-side key identifying this kind of session |
| `PlayerProperties` | `Dictionary<string, PlayerProperty>` (base) | empty | Per-player values such as `"role"`. Cap of 10 per player |

Fluent extensions live on `SessionOptionsExtensions`: `.WithRelayNetwork()`, `.WithDirectNetwork()`,
`.WithDistributedAuthorityNetwork()`, `.WithNetworkHandler()`, `.WithHostMigration()`,
`.WithPlayerName()`.

### `JoinSessionOptions` — join by id, join by code, quick-join fallback

Inherits `BaseSessionOptions`. Carries `Password` (`null`), plus the inherited `Type` and
`PlayerProperties`. Nothing else: the joiner does not get to restate the session's own settings.

### `ReconnectSessionOptions` — reconnect

Only `Type` (`string`, new GUID). Fluent `.WithNetworkHandler(INetworkHandler)`, which turns the
default netcode integration off for that reconnect.

### `MatchmakerOptions` — ticketed matchmaking

| Property | Type | Default | Notes |
|---|---|---|---|
| `QueueName` | `string` | `null` | Must name a queue that exists in the environment. This is the field that silently produces nothing when the cloud side was never deployed |
| `TicketAttributes` | `Dictionary<string, object>` | empty | Sent with the ticket, matched against queue rules |
| `PlayerProperties` | `Dictionary<string, PlayerProperty>` | empty | Forwarded per player |

### `QuickJoinOptions` — filter-based matchmaking

| Property | Type | Default | Notes |
|---|---|---|---|
| `Filters` | `List<FilterOption>` | empty | A candidate session must satisfy all of them |
| `Timeout` | `TimeSpan` | SDK default | How long to keep retrying |
| `CreateSession` | `bool` | `false` | Create one if the timeout expires with no match |

> **Leave `Timeout` alone unless the user asked for a specific wait.** With `CreateSession = true`,
> shortening it turns a match that would have been found into a new empty game; with the default it
> just fails sooner.

### `QuerySessionsOptions` — browsing

| Property | Type | Default |
|---|---|---|
| `Count` | `int` | `100` |
| `Skip` | `int` | `0` |
| `FilterOptions` | `List<FilterOption>` | empty |
| `SortOptions` | `List<SortOption>` | empty |
| `ContinuationToken` | `string` | `null` |

### `AddingSessionOptions` — event payload, read-only

Carries `Type`: the session type string that was passed to the create or join call that raised the
event.

## Filters and sorting

`FilterOption(FilterField field, string value, FilterOperation operation)`.

| Enum | Values |
|---|---|
| `FilterField` | `MaxPlayers`, `AvailableSlots`, `Name`, `Created` (RFC3339), `LastUpdated` (RFC3339), `IsLocked`, `HasPassword`, `StringIndex1`–`StringIndex5`, `NumberIndex1`–`NumberIndex5` |
| `FilterOperation` | `Contains` (`Name` only), `Equal`, `NotEqual`, `Less`, `LessOrEqual`, `Greater`, `GreaterOrEqual` |

`SortOption(SortOrder order, SortField field)`.

| Enum | Values |
|---|---|
| `SortOrder` | `Ascending`, `Descending` |
| `SortField` | `Name`, `MaxPlayers`, `AvailableSlots`, `CreationTime`, `LastUpdated`, `Id`, `StringIndex1`–`StringIndex5`, `NumberIndex1`–`NumberIndex5` |

A custom property is only filterable or sortable once it has been given an index slot — see
`PropertyIndex` below. A game browser that filters on "game mode" is filtering on
`StringIndex1`, whatever the property is called.

## Session configuration

| Topic | Detail |
|---|---|
| Room-like fields | Max players, name, password, locked and private flags, the `Type` key, session and player properties |
| Property visibility | `VisibilityPropertyOptions`: `Public`, `Member`, `Private` — decides who can read a property, including whether it shows in a query result |
| Indexing | `PropertyIndex` maps a custom property onto one of the string or number index slots so filters and sorts can reach it |
| Networking | `SessionOptionsExtensions`: `WithRelayNetwork`, `WithDirectNetwork` (listen/publish address, or `DirectNetworkOptions`), `WithNetworkOptions` (e.g. `RelayProtocol`), `WithNetworkHandler` for a custom `INetworkHandler` |
| Host migration | `WithHostMigration` plus an `IMigrationDataHandler`; on `IHostSession`, `GetHostMigrationDataAsync` / `SetHostMigrationDataAsync` |
| Player name | `WithPlayerName`, with its own visibility |
| Backfill | `MatchmakerServerExtensions.WithBackfillingConfiguration` on `SessionOptions`; `StartBackfillingAsync` / `StopBackfillingAsync` on the matchmade session — see [`dedicated-server-sessions.md`](dedicated-server-sessions.md) |

## The session network

When the options carry any of the `With*Network*` extensions, create / join / matchmake / reconnect
bring the configured netcode stack up as part of the call. There is no second start step on that
path, and adding one is how a project ends up with two competing connection lifecycles.

| Surface | Role |
|---|---|
| `IHostSessionNetwork` | `StartDirectNetworkAsync`, `StartRelayNetworkAsync`, `StopNetworkAsync`, network state and failure events, the `INetworkHandler` |
| `IClientSessionNetwork` | Client-side `NetworkState` and its events, `NetworkHandler` |
| `NetworkConfiguration` | Transport endpoints and relay server data. `NetworkType`: `Direct`, `Relay`, `DistributedAuthority`. `NetworkRole`: `Client`, `Server`, `Host` |

Reach for `StartRelayNetworkAsync` / `StartDirectNetworkAsync` explicitly only in the deliberate
"metadata now, gameplay later" shape — a room that exists while players are still choosing, with
the connection raised at the moment the match starts.

## Host migration

`WithHostMigration()` on the options plus an `IMigrationDataHandler` is what lets the match survive
the host leaving. The handler is where the game says what a new host needs in order to continue:
`GetHostMigrationDataAsync` on the outgoing host, `SetHostMigrationDataAsync` on the incoming one.
Whatever is not in that payload is gone. Decide the payload with the same care as a save format,
because that is what it is.

## Matchmaking results

`MatchmakerExtensions.GetMatchmakingResults(ISession)` reads the stored ticket outcome off a
session that came out of matchmaking — teams and assignment data, once the session exists.

## Errors and observation

Every async call on `IMultiplayerService` throws `SessionException` on failure, and
`SessionException` carries a specific `SessionError` value alongside the message. Branch on the
error value; the message is for the log, not for control flow.

`SessionObserver` watches add and failure events for one session **type**, which is the hook for
"the join failed somewhere three layers down the UI" without threading a callback through it.

## Editor components

`Unity.Services.Multiplayer.Components` is the no-code path, and useful for a prototype:

| Item | Role |
|---|---|
| `MultiplayerSession` (ScriptableObject) | Holds the `ISession` and exposes UnityEvent groups for lifecycle, session and player changes |
| `SessionConnector` / `SessionConnectorBehaviour` | Create or create-or-join driven from a scene event, e.g. on sign-in |

It is still the same API underneath, so a project can start here and move to code without changing
what the calls mean.
