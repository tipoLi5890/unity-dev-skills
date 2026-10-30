---
name: unity-ugs
description: >-
  Unity Gaming Services API: which package, init and sign-in order, Cloud Save, Cloud Code, Remote Config.
---

# unity-ugs — initialise, sign in, and know who is allowed to write

## Symptom → where to look

| Symptom | Go to |
|---|---|
| `NullReferenceException` or "service not initialised" on a `*.Instance` | §2 |
| Sign-in succeeds, then the next call is `Unauthorized` | §2, [`reference/authentication.md`](reference/authentication.md) |
| "Add cloud save"; a write returned success but the read comes back empty | §3 — the read access class does not match the bucket |
| `403` on a Cloud Save write that used to work | [`reference/config-access-deploy.md`](reference/config-access-deploy.md) §6 — an `.ac` policy is now deployed |
| A player has XP, currency or an unlock they did not earn | §4 |
| The Deployment Window will not publish a Cloud Code module | [`reference/cloud-code.md`](reference/cloud-code.md) — the module file set |
| Remote Config values are right in the dashboard, wrong in the build | [`reference/config-access-deploy.md`](reference/config-access-deploy.md) §5 — a Game Override is targeting that player |
| `PlayerAccountService` does not resolve | [`reference/player-account.md`](reference/player-account.md) — it is a second assembly |
| Which UGS package does a feature need | §1 |
| "Add a battle pass / achievements / player accounts" — wiring a whole feature | §10 |

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
  read-only; a Cloud Code module or `IAdminClient.CloudSaveData` (`reference/config-access-deploy.md` §8) writes it.
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

## 5–9. Config, access, deployment, clients, samples → `reference/config-access-deploy.md`

§5 Remote Config holds the definitions, Game Overrides do the A/B; §6 Access Control, where deny
wins; §7 what the Deployment Window pushes; §8 the four Services API clients and their trust
levels; §9 start from a Building Block or sample. Same numbering there.

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
`unity-multiplayer-services`; the topology decision behind them is `unity-live-services`. Voice
chat is `unity-vivox`. Store purchases — receipts, entitlement, the store SDKs — are `unity-iap`,
and ad mediation is `unity-ads-levelplay`; UGS Economy's virtual purchases are a different thing
and stay here. Adding the packages themselves is `unity-new-project`.

Also outside: the Unity Dashboard's own configuration (identity providers, audiences,
environments, service accounts), which has no local representation, and server-side game design —
what an achievement should be worth, how a season is priced. `docs.unity.com` is the authority for
per-service detail this skill compresses.

## Reference

- [`reference/config-access-deploy.md`](reference/config-access-deploy.md) — §5–§9: Remote Config, Access Control, deployment, clients, samples
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
