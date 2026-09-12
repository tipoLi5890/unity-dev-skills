# Packages and cloud setup, per workflow

Check this before recommending a path. The characteristic failure it prevents is code that
compiles, runs, throws nothing useful, and finds no match — because the cloud-side resource it
names was never deployed.

Unity Gaming Services initialisation and authentication are required for all of it:
`com.unity.services.core` and `com.unity.services.authentication`.

Which row applies should be **inferred** — from the conversation, from `manifest.json`, from
whether there is a server build target, from deployment assets in the project. Ask only when two
rows genuinely fit and they differ in prerequisites, and ask in game terms rather than by reading
a row name aloud (see [`requirement-dimensions.md`](requirement-dimensions.md)).

| What the game is doing | What has to be in place |
|---|---|
| Rooms, codes, lists, properties — **no** shared simulation | `com.unity.services.multiplayer` alone. No gameplay netcode package until a custom `INetworkHandler` appears or something calls `StartRelayNetworkAsync` / `StartDirectNetworkAsync` |
| Shared simulation over the session's network | Exactly one gameplay stack: Netcode for GameObjects `com.unity.netcode.gameobjects` **or** Netcode for Entities `com.unity.netcode`; `com.unity.netcode.entities` is not a package id (registry 404). Wire transport through the session network APIs rather than starting the stack separately |
| Quick join by filter | A session `Type` the filters can key on, and index slots on the properties being filtered (`PropertyIndex`); `QuickJoinOptions` in code |
| Ticket matchmaking into a **player-hosted** match | A deployed Matchmaker queue whose name matches `MatchmakerOptions.QueueName`, the matchmaker configuration for the environment the build points at, and authenticated players |
| Ticket matchmaking onto a **dedicated server** | The queue configured for server allocation, a server build, and a hosting setup to allocate into (`com.unity.services.multiplay`). The server process takes the server session role, and usually `WithBackfillingConfiguration` plus `StartBackfillingAsync` / `StopBackfillingAsync` to refill slots on a live allocation |
| Editor-wired session with `MultiplayerSession` / `SessionConnector` | Same multiplayer package; the components live in `Unity.Services.Multiplayer.Components`. The netcode row above still applies if gameplay is networked |
| Deploying queues or multiplayer assets from the Editor | The Editor's Deployment window, pointed at the right environment, run **before** the code that names those resources — see Unity's deployment documentation for the Multiplayer Services SDK on [docs.unity.com](https://docs.unity.com/) |

Package ids move between Unity versions more often than the APIs do. When one does not resolve,
read the version the project actually got out of `packages-lock.json` rather than retyping the id
from memory.
