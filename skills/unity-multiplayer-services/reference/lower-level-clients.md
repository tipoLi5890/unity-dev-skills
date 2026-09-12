# The three clients underneath, and when they are the answer

The session API is built on three services that also ship their own clients. Going straight to one
of them is legitimate in exactly two situations:

1. The goal cannot be reached through `IMultiplayerService` — confirmed by looking at
   [`session-api.md`](session-api.md), not by assuming.
2. The user asked for that namespace or that product by name.

Outside those two, the cost is concrete: a second lifecycle to create, refresh, and tear down in
step with the session's, and the composed calls that were handling it become unusable because the
session no longer owns the thing they manage. The bug that follows is the reconnect that half
works.

| Service | Namespace | Package | What only it does |
|---|---|---|---|
| Lobby | `Unity.Services.Lobbies` | `com.unity.services.lobby` — note the id is singular, `com.unity.services.lobbies` returns 404 | Lobby CRUD, queries, realtime lobby events and migration payloads for a lobby that is not a session at all |
| Matchmaker | `Unity.Services.Matchmaker` | `com.unity.services.matchmaker` | Raw ticket lifecycle — create, poll status, backfill tickets — when something other than a session consumes the result |
| Relay | `Unity.Services.Relay` | `com.unity.services.relay` | Allocations and join codes handed to a transport the session API does not know about |

The session equivalents, for comparison: `MatchmakeSessionAsync` with `MatchmakerOptions` replaces
ticket handling; `WithRelayNetwork()` and `StartRelayNetworkAsync` replace allocation and join-code
plumbing; session properties and `QuerySessionsAsync` replace lobby CRUD and queries.

Both accessor styles exist here too — the statics, and `IUnityServices` extension methods on an
initialised services instance. Nothing about dropping a layer changes the requirement to initialise
and authenticate first.

This table is for deciding an implementation. It is not something to present to a user who asked
how their players get into a game together.
