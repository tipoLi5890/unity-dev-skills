# Dedicated server sessions

The server-side entry points live in their own assembly, `Unity.Services.Multiplayer.Server`, and
that assembly does not exist in a client build. Getting the build constraints wrong is the first
problem every dedicated-server project hits, so it comes before the API.

## The build constraint

`Unity.Services.Multiplayer.Server.asmdef` carries `defineConstraints` on **`UNITY_SERVER`** or
**`ENABLE_UCS_SERVER`**: the assembly is compiled only for a server build. Your own code that
references it therefore has to disappear on the same condition.

| Approach | What it looks like |
|---|---|
| Scripting define | Wrap the references — types, calls, and any `using` that pulls a server-only namespace — in `#if UNITY_SERVER` … `#endif` |
| Assembly definition | Put `"defineConstraints": ["UNITY_SERVER"]` in the `.asmdef` of the assembly that references the server API, so the whole assembly is skipped for client targets |

Either works; a project with more than a handful of server files wants the second, because a
missed `#if` in one file breaks the client build for everyone. The failure looks like a missing
type in a build that compiled fine yesterday — check what changed about the platform, not about
the code.

## The service

| Topic | Detail |
|---|---|
| Assembly | `Unity.Services.Multiplayer.Server` |
| Access | `MultiplayerServerService.Instance`, or `unityServices.GetMultiplayerServerService()` from `Unity.Services.Core.UnityServicesExtensions`, after services initialisation inside a server build |
| Core type | `IMultiplayerServerService` — creates and resolves server-side sessions, returning `IServerSession` |

`IServerSession`, `SessionOptions` and the rest of the session types come from the main
`Unity.Services.Multiplayer` assembly. The Server assembly adds the server entry points and the
matchmaker extensions, nothing else — for option tables and networking helpers use
[`session-api.md`](session-api.md) and apply the same options here.

```csharp
// New dedicated-server session from options. Throws SessionException on failure.
Task<IServerSession> CreateSessionAsync(SessionOptions sessionOptions)

// Server session under a chosen id — creates it, or joins it if it already exists.
Task<IServerSession> CreateSessionAsync(string sessionId, SessionOptions sessionOptions)

// Server session bound to a Matchmaker match id, honouring matchmaker configuration on the options.
Task<IServerSession> CreateMatchSessionAsync(string matchId, SessionOptions sessionOptions)
```

> **Check `GetSessionAsync`'s accessibility in the resolved package before writing a call to it.**
> On `IMultiplayerServerService` it may be `internal`, and member visibility moves between package
> versions. Treat the three `Create*` methods above as the supported way for a server process to
> get a session. A name that appears in a decompiler, or in autocomplete against a different
> assembly, proves nothing about whether game code can call it.

## Backfill

Players leave a running match. Backfill is what puts the allocation back in front of the matchmaker
so the empty slots refill instead of the match limping to the end short-handed.

```csharp
// Set on SessionOptions before the create/match call.
T WithBackfillingConfiguration<T>(this T options, bool enable, bool automaticallyRemovePlayers,
    bool autoStart, int playerConnectionTimeout, int backfillingLoopInterval) where T : SessionOptions

// Control it on a matchmade session.
Task StartBackfillingAsync(this ISession session)
Task StopBackfillingAsync(this ISession session)
```

All three are `MatchmakerServerExtensions`, declared in `Unity.Services.Multiplayer.Server`, so
they are subject to the same build constraint as everything else in this file. `autoStart` decides
whether the loop begins on its own or waits for `StartBackfillingAsync` — a match with a warm-up
phase usually wants to start it by hand, after the doors close.

## Errors

`IMultiplayerServerService`'s async methods throw `SessionException`, the same type and error
family as the client API. A server that swallows it exits zero with no match, which is the worst
version of this failure: the hosting layer sees a healthy process.
