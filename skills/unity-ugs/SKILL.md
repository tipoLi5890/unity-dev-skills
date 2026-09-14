---
name: unity-ugs
description: >-
  The Unity Gaming Services API layer: which package does what, the init and
  sign-in order, Cloud Save access classes and who may write each, Cloud Code
  C# modules, Remote Config and Game Overrides, Access Control, the Deployment
  Window. Load for: "add cloud save", "add a battle pass / achievements /
  player accounts", a service singleton that throws because nothing was
  initialised, Cloud Save data that reads back empty although the write
  succeeded, a Cloud Code module the Deployment Window refuses to publish, a
  403 on a write that used to work, which UGS package a feature needs. The
  operational discipline around it is unity-live-services.
---

# unity-ugs — initialise, sign in, and know who is allowed to write

> **Two orderings decide most UGS bugs.** The first is `InitializeAsync()` → sign-in → any
> service call; skip a step and the singleton you touch throws rather than explaining itself.
> The second is **who may write a given piece of data** — that single question fixes the Cloud
> Save access class, whether the mutation goes through Cloud Code, what the `.ac` policy says,
> and which bucket you must read back from. Get it wrong and the data does not error, it
> **disappears**: written to one bucket, read from another.

## The working contract

> **Report, then wait.** Deploying cloud resources changes a live environment that other people
> and real player data sit behind. Say which environment is selected, list the files that would
> be pushed, and wait for confirmation before pressing Deploy.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| `NullReferenceException` or "service not initialised" on a `*.Instance` | §2 |
| Sign-in succeeds, then the next call is `Unauthorized` | §2, [`reference/authentication.md`](reference/authentication.md) |
| A write returned success but the read comes back empty | §3 — the read access class does not match the bucket |
| `403` on a Cloud Save write that used to work | §6 — an `.ac` policy is now deployed |
| A player has XP, currency or an unlock they did not earn | §4 |
| The Deployment Window will not publish a Cloud Code module | [`reference/cloud-code.md`](reference/cloud-code.md) — the module file set |
| Remote Config values are right in the dashboard, wrong in the build | §5 — a Game Override is targeting that player |
| `PlayerAccountService` does not resolve | [`reference/player-account.md`](reference/player-account.md) — it is a second assembly |
| Which package do I actually need | §1 |
| Wiring a whole feature (achievements, battle pass, accounts) | §10 |

## 1. Packages, and what the floor should be

Each service is its own package, `com.unity.services.<service>`, except `com.unity.remote-config`
(no `services.` segment). The *API floor* is the vendor's stated minimum: if a call is missing at
the floor, pin higher, and read what resolved off `Packages/packages-lock.json`. A `latest`
dist-tag can be a pre-release — check Cloud Code's before you pin — and Cloud Code subscriptions
need `com.unity.services.wire` as a separate add. Adding packages is a project change:
`unity-new-project` → `reference/package-bootstrap.md`.

Check the project has UGS at all before writing against it:
`System.Type.GetType("Unity.Services.Core.UnityServices, Unity.Services.Core")` returns null when
no UGS package is installed.

Ids and floors: [`reference/packages.md`](reference/packages.md).

## 2. The order everything else depends on

```
Init ─▶ Auth ─┬─▶ Remote Config · definitions, read-only
              ├─▶ Cloud Save · Default / Public
              ├─▶ Economy · read
              └─▶ Cloud Code ─┬─▶ Cloud Save · Protected / Custom
                              ├─▶ Economy · write
                              └─▶ Leaderboards · submitted score
```

Left of that last fork the client is believed; right of it the server decides (§3, §4).

```csharp
using Unity.Services.Core;
using Unity.Services.Authentication;

await UnityServices.InitializeAsync();

if (!AuthenticationService.Instance.IsSignedIn)
    await AuthenticationService.Instance.SignInAnonymouslyAsync();

// CloudSaveService.Instance, CloudCodeService.Instance and the rest are usable from here.
```

- **`InitializeAsync()` first, once.** Singletons exist before it completes but are not usable,
  and the exception names neither the missing initialisation nor the service.
- **Guard the sign-in with `IsSignedIn`.** `SignInAnonymouslyAsync` covers a returning player
  (cached token) and a new one, but calling it while signed in is an error — usually a scene reload.
- **`IsSignedIn` and `IsAuthorized` are different questions.** A token exists, expired or not,
  versus a token currently valid. Branch retry logic on `IsAuthorized`.
- **On Xbox, PlayStation and Switch, token refresh is not automatic** — re-sign-in is yours.
- **Clearing credentials on an account with only anonymous sign-in destroys it permanently.**
  Link a provider first.

Sign-in methods, link/unlink, profiles, error codes: [`reference/authentication.md`](reference/authentication.md).

## 3. Cloud Save: four access classes, and who writes each

| Class | Who reads | Who writes | What belongs there |
|---|---|---|---|
| **Default** | Owner | Owner | Private settings, preferences, local progress |
| **Public** | Any player | Owner | Display name, avatar id, anything on a public profile |
| **Protected** | Owner | **Server only**, via Cloud Code | Anything the player must not be believed about |
| **Custom** | Any player | **Server only** | Game-wide shared state and config, not tied to a player |

> **A read from the wrong class returns nothing and raises nothing.** The classes are separate
> buckets: data written through `PublicWriteAccessClassOptions` is invisible to a load with no
> options, and Protected data to everything except `ProtectedReadAccessClassOptions()`. The usual
> cause is a feature that moved to server writes without the read side moving with it.

- **Custom data has no client write path at all.** `CloudSaveService.Instance.Data.Custom` is
  read-only; a Cloud Code module or `IAdminClient.CloudSaveData` (§8) writes it.
- **`SaveOptions`, `LoadOptions` and `DeleteOptions` exist twice**, at the root of
  `Unity.Services.CloudSave` and under `Models.Data.Player`; the access-class overloads are the
  second set. Importing both is an ambiguous reference — every sample here declares `using` aliases.

Methods, models, write locks, queries and files: [`reference/cloud-save.md`](reference/cloud-save.md).

## 4. Route integrity-affecting writes through Cloud Code

> **If a value decides what a player owns, the client does not write it.** XP, currency, rewards,
> unlocks, entitlement, anything gated by time or by another player's state. The client asks; the
> server decides, validates and writes.

```csharp
var result = await CloudCodeService.Instance.CallModuleEndpointAsync<GrantResult>(
    "BattlePassModule", "AwardXp", args);   // module name first, function name second
```

- **Prefer C# modules over JavaScript scripts.** Scripts (`CallEndpointAsync`) suit a throwaway
  prototype; only modules push messages to a client.
- **Modules run on plain .NET, not on Unity.** No `UnityEngine`, no Remote Config client.
- **A cold module is slow.** Design the screen so a first call can take a visible moment.
- **A module is a file set, not a file.** Solution, `.csproj`, the module class, `ModuleSetup.cs`,
  a `linux-x64` publish profile and the `.ccmr` asset; miss one and the Deployment Window fails
  while naming a different file.

The file set, templates and the `.gitignore` override: [`reference/cloud-code.md`](reference/cloud-code.md).

## 5. Remote Config holds the definitions; Game Overrides do the A/B

Remote Config stores what exists in the game — the achievement list, battle pass tiers, the shop
catalogue, feature flags — as typed entries fetched in one call and deployed as `.rc` files.
**Remote Config on its own has no A/B testing.** Game Overrides (`.ugo`, from
`com.unity.services.tooling`) replace values for a named audience, and `FetchConfigsAsync`
returns the overridden value — which is why a value right in the dashboard arrives wrong in a build.

Fetch and `.rc` format: [`reference/remote-config.md`](reference/remote-config.md). Overrides:
[`reference/tooling.md`](reference/tooling.md).

## 6. Access Control: deny wins

An `.ac` policy permits or denies access to UGS resources by URN, per principal (`Player` or
`ServiceAccount`), for `Read`, `Write` or both. **Deny takes precedence over Allow**, so the
workable shape is a blanket deny for `Player` on `urn:ugs:*:/**` plus explicit allows for the
endpoints a client legitimately calls. This is the enforcement half of §4: with a policy deployed
a direct write returns `403`, which also breaks any build still writing directly.

URNs and a full deny-then-allow policy: [`reference/tooling.md`](reference/tooling.md).

## 7. What the Deployment Window pushes

**Services > Deployment** discovers UGS resource files under `Assets/`, targets one environment
and pushes them. A file type appears only if the package that registers it is installed: `.rc`
`.ac` `.ugo` `.ccmr` `.js` `.lb` `.ecc` `.eci` `.ecv` `.ecr` `.ddef`, plus Game Server Hosting
build config `.gsh` and Matchmaker queue config `.mmq` from `com.unity.services.multiplayer` —
same window, same environment picker, authored by `unity-multiplayer-services`. The UGS CLI does
the same job outside the Editor, and is unrelated to the `unity` CLI that `unity-cli` covers.

Per-type packages, `.ddef` scoping, the programmatic API and the UGS CLI:
[`reference/deployment.md`](reference/deployment.md).

## 8. Services APIs — four clients, four trust levels

`com.unity.services.apis` is the generated REST layer under the friendly SDKs, for what they have
no path for — in practice, admin writes. `IGameClient` (player device, the signed-in player),
`IServerClient` (dedicated server, server key), `ITrustedClient` (dedicated server needing any
player's data, service account), `IAdminClient` (**Editor only**, service account key id + secret).
`IAdminClient` is the only supported way to write Cloud Save Custom data or give an Editor tool or
a custom deploy command elevated rights; its key is never in the project (`unity-live-services`
§2). Service areas: [`reference/apis.md`](reference/apis.md).

## 9. Building Blocks and samples — start from one

Unity publishes free Building Block packages on the Asset Store — Achievements, Leaderboards,
Player Account, Multiplayer Session, Matchmaker Session — each a working vertical slice with UI,
runtime code, Cloud Code modules and cloud resource files. For "add achievements" or "add
leaderboards", import one and read it first; §10's blueprints then annotate something that runs.
`com.unity.starter-kits` returns 404 on the public registry: use the Asset Store links. Links,
dependencies, samples: [`reference/building-blocks.md`](reference/building-blocks.md).

## 10. Three shapes, and everything is one of them

**Config + state + server writes.** Definitions in Remote Config, per-player state in Cloud Save
Protected, every mutation through a Cloud Code module, an `.ac` policy denying the direct path:
achievements, battle passes, quests, seasons — anything the player earns.
[`reference/achievements.md`](reference/achievements.md), [`reference/battlepass.md`](reference/battlepass.md).

**Client-direct data.** Cloud Save Default or Public, written straight from the client:
preferences, display name, avatar choice. The test is whether a player editing the value
arbitrarily would matter; if not, a server round trip buys nothing.
[`reference/player-account.md`](reference/player-account.md).

**Competitive.** Scores go to Leaderboards — directly when the score is uninteresting to cheat
over, through Cloud Code when it is not — and rankings come back client-side with pagination and
player-relative queries.

## Before you call it done

- The project compiles, and the Cloud Code module solution builds on its own.
- Initialisation order holds on every entry path, including a scene reload.
- Every write that decides what a player owns goes through a module; grep for direct writes of
  those keys and expect none.
- The read access class matches the bucket that was written, per key.
- The `.ac` policy denying direct player writes is deployed, not just authored.
- The `.ccmr` filename matches the module name passed to `CallModuleEndpointAsync`.
- Remote Config keys match the strings the client and the module use.
- Every resource file is under `Assets/` and appears in the Deployment Window against the
  environment you meant (`unity-live-services` §1).
- The project is linked under **Edit > Project Settings > Services**.

## Scope — what this skill does NOT do

**The operating discipline is `unity-live-services`, and it comes first.** Which environment a
build is bound to and how that is made visible, where a service account key may live, what each
feature does when the backend is unreachable, and making a retried write idempotent — none of
that is an API question, and this skill deliberately does not restate it.

Real-time sessions, matchmaking, lobbies and dedicated server hosting are
`unity-multiplayer-services`; the topology decision behind them is `unity-multiplayer`. Voice
chat is `unity-vivox`. Store purchases — receipts, entitlement, the store SDKs — are `unity-iap`,
and ad mediation is `unity-ads-levelplay`; UGS Economy's virtual purchases are a different thing
and stay here. Adding the packages themselves is `unity-new-project`.

Also outside: the Unity Dashboard's own configuration (identity providers, audiences,
environments, service accounts), which has no local representation, and server-side game design —
what an achievement should be worth, how a season is priced. `docs.unity.com` is the authority for
per-service detail this skill compresses.

## Reference

- [`reference/authentication.md`](reference/authentication.md) — sign-in, linking, profiles, error codes
- [`reference/cloud-save.md`](reference/cloud-save.md) — methods, models, write locks, queries, files
- [`reference/cloud-code.md`](reference/cloud-code.md) — the module file set, subscriptions, bindings
- [`reference/remote-config.md`](reference/remote-config.md) — fetch, `.rc` format, typing
- [`reference/tooling.md`](reference/tooling.md) — `.ac` policies and URNs, `.ugo` overrides
- [`reference/deployment.md`](reference/deployment.md) — file types, `.ddef`, programmatic API, UGS CLI
- [`reference/apis.md`](reference/apis.md) — the four clients, admin service areas
- [`reference/packages.md`](reference/packages.md) — package ids, API floors, what resolved
- [`reference/building-blocks.md`](reference/building-blocks.md) — Building Blocks, sample projects
- [`reference/achievements.md`](reference/achievements.md) — blueprint: definitions, records, module, `.ac`
- [`reference/battlepass.md`](reference/battlepass.md) — blueprint: tiers, premium track, XP validation, claims
- [`reference/player-account.md`](reference/player-account.md) — blueprint: three sign-in flows, profile data
