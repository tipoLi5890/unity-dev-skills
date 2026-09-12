---
name: unity-live-services
description: >-
  Discipline for putting a Unity game on a backend, Unity Gaming Services or
  otherwise: which environment a build talks to and how to make that visible,
  where credentials may live, what the client is not believed about, and the
  offline path designed before the online one. Load when adding accounts,
  cloud save, remote config, economy, leaderboards, cloud code or analytics to
  a game that has none; when dev and production data got mixed up; when the
  game calls a third-party HTTP API (an LLM, a translation service) or a
  player supplies their own API key; when deciding what a build may send off
  the device; or when a key leaked through a screenshot or log. The API calls
  themselves are unity-ugs.
---

# unity-live-services — the parts that are not an API call

> **A backend turns a game you ship into a service you run.** The API is the small part. The
> decisions below are the ones that are painful to reverse after real players have data.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| A tester's progress reset, or test rows appeared in production | §1 |
| "Where do I put this key?" | §2 |
| A player has currency or an unlock they did not earn | §3 |
| The game hangs on a spinner, or the menu will not open offline | §4 |
| A reward was granted twice after a timeout | §4 idempotency |
| Server logic exists only in a web console | §5 |
| The game calls a third-party HTTP API directly (LLM, content service) | §6 |
| The key belongs to the player, not to you | §6 |
| "What is this build allowed to send off the device?" | §6 |
| A key appeared in a screenshot, a log or a bug report | §6 |

Provider-agnostic backend discipline — where secrets live, fail direction, deploy ordering,
emulate-locally-first — belongs to a backend skill that is not tied to a provider, rather than
here. This skill is the Unity-shaped subset.

**When to jump.** What this skill decides is operational: which environment a build is bound to,
where a credential is allowed to live, which values the client is not believed about, and what the
game does when the backend is unreachable. The call-by-call layer next door is `unity-ugs` — which
package provides which service, the initialisation order, Cloud Save access classes and queries,
Cloud Code modules, Remote Config and the deployment file types. Settle the four questions here,
write the calls there, and return before a build points at production.

## 1. Which environment is this build talking to?

UGS projects have named environments (`development`, `production`, …). The failure is not
choosing wrong; it is **not being able to tell**.

- **The environment name must be visible in a non-release build** — on the debug overlay, in the
  first log line, somewhere a screenshot will capture it. A tester reporting "my progress reset"
  is unanswerable without it.
- **Bind the environment to the build configuration, not to a runtime toggle.** A switch a QA
  build can flip is a switch that will get flipped, and then production data has test rows in it.
- **A release build must refuse to start against a non-production environment.** Same stance as
  `unity-android-release`: refuse rather than warn.
- Project id and environment belong with the build record —
  `unity-android-release` → `reference/build-automation.md` provenance JSON.

## 2. Where credentials may live

| Credential | Where |
|---|---|
| Project id, environment name | In the project. Not secret |
| Service account key / secret | **Gitignored file or CI secret only** — the shape of `unity-android-release`'s `templates/build-env.example`, kept as an ignored `Tools/.build-env` |
| Anything that authorises a write on behalf of another player | **Server only.** Never in a build |
| A key the *player* supplies, billed to their own third-party account | **On their device only** — entered in-app, never in the repo, the artifact, or your logs (§6) |

A key that ships inside a player build is public — decompilation is not required, `strings` is
enough. If a feature seems to need one client-side, the feature belongs in Cloud Code.

## 3. What the client is not allowed to be believed about

The default question for every value crossing the boundary: **what happens if a player sends an
arbitrary value here?**

Server-authoritative, always: currency balances and any grant, purchase entitlement, leaderboard
scores, anything gated by time, anything gated by another player's state. Client-authoritative
is fine for cosmetic preference, local settings, and analytics-shaped telemetry you already
treat as untrusted.

**Validation lives beside the data, not in the caller.** A rule enforced only by the client that
happens to write is a rule with no enforcement.

Cloud Save gives you that split as a storage property rather than as a convention. Data there
carries one of four access classes — Default (the owner reads and writes), Public (anyone reads,
the owner writes), Protected (the owner reads, only server code writes) and the game-wide Custom
(every player reads, only the server writes). **Protected is the list above, expressed in the
backend**: put anything the client is not allowed to be believed about there, so a client-side
write of it fails rather than succeeding quietly against a rule nobody enforced. The four classes,
the write-lock and the deployable policy files are `unity-ugs`.

## 4. Design the offline path first

> **Every backend call fails sometimes** — no signal, a token expired mid-session, a regional
> outage, the player put the phone in a tunnel.

- **Decide per feature what happens when it is unreachable,** and write it down before writing
  the call. "It shows a spinner forever" is the default you get by not deciding.
- **Never block the main menu or the first play on a network round trip.** A backend outage
  should degrade the game, not close it.
- **Sign-in is the one that surprises people:** an anonymous session that silently fails means a
  returning player looks like a new one, and the game happily starts them over. Fail loudly
  towards the player, not silently towards the save file.
- **Writes need idempotency.** A retry after a timeout that already succeeded must not grant the
  reward twice. That means a client-generated operation id, checked server-side.

## 5. Cloud Code is source code

It is the part that most often ends up edited in a web console and existing nowhere else.

- **In the repo, reviewed, and deployed by the same pipeline as the game.** Concretely, the
  deployable artefacts are files: Remote Config entries, access policies, Cloud Code module
  references, leaderboard and economy definitions and audience overrides live on disk as
  `.rc` / `.ac` / `.ccmr` / `.lb` / `.ec*` / `.ugo`, among others. If a service's configuration
  exists only as console state and none of those files is committed, the environment cannot be
  rebuilt and a change cannot be reviewed. `unity-ugs` holds the full table — every extension,
  and which package has to be present for the file type to exist at all.
- **Deployment order matters:** deploy server logic that tolerates both the old and the new
  client *before* shipping the client that needs it. Players update on their own schedule, and
  some never do.
- **Config and schema changes are one-way in practice** once live data exists. Treat a field
  rename as an additive migration, never as a rename.

## 6. When the backend is somebody else's HTTP API

A game that calls an LLM, a translation service or any other third-party API from the client has
§2's credential problem, §3's trust problem and §4's failure problem at once — rearranged, because
**the key may belong to the player rather than to you** and because the interesting direction is
outbound. Worked detail, test shapes and the artifact greps:
[`reference/third-party-api-keys.md`](reference/third-party-api-keys.md).

- **A player-supplied key is entered in-app, stored on the device, and passed to the transport at
  call time.** The build ships no key; the artifact grep in Verification is then "is *any* key in
  here", not "is mine". If the feature must run on *your* account instead, it is a thin proxy you
  operate — same conclusion as §2.
- **Mask the key everywhere it is rendered, the entry field included.** A key field left in its
  default, unmasked state is one screenshot away from a leak: a device screenshot of the entry
  screen pasted into a chat carries the full plaintext key with it. Last four characters are
  enough to confirm a paste. Any screenshot, recording or log containing a key is a **rotation**
  event, and the UI should say so.
- **The key never enters a log line, an analytics event or an error string.** Report status plus a
  truncated response body; never the request headers.
- **What leaves the device is an explicit allow-list, not whatever the record happens to hold.**
  Send derived values — scores, computed indicators, aggregates, deterministic tags — and never
  identity, raw event streams or captured audio. Filter free-form sections through a whitelist of
  key names so a field added locally later cannot ride along.
- **Pin that with a test that asserts on the serialised payload string**, and repeat it against
  the body the transport actually received — a clean builder does not prove the caller sent its
  output.
- **Put the HTTP call behind an injectable transport.** One swappable interface lets EditMode
  tests pin the request shape and PlayMode tests walk consent → result with no network and no
  key; restore the real transport in the same test body.
- **Persist a consent gate before the first outbound send**, and make the allow-list above the
  sentence that screen shows.
- **A third-party's prose is never a source of truth for numbers.** Compute every figure locally
  first, so a failed call degrades to "the numbers, plus a retry" instead of an empty screen.
- **Cache the response beside the record and key the cache on whatever changes it** (locale, for
  instance). Re-opening a result must not re-spend the player's money — §4's idempotency rule,
  billed.

## Verification

- Cold start with the network disabled — the game must reach playable.
- Kill the network mid-session and restore it — no duplicate grants, no lost writes.
- A build's environment must be readable from a screenshot of it.
- Grep the built artifact for anything that looks like a key — yours *or* a player's. The greps are
  in [`reference/third-party-api-keys.md`](reference/third-party-api-keys.md); the toolchain for
  reading an artifact back is `unity-android-release` → `reference/artifact-verification.md`.
- For a third-party API: run the whole flow with a fake transport and the network off, and assert
  the captured request body contains no player identity.

## Scope — what this skill does NOT do

The UGS API surface itself is `unity-ugs` — which package provides what, the initialisation order,
Cloud Save access classes and queries, Cloud Code modules, Remote Config and Game Overrides, and
the deployment file types. Real-time connections are `unity-multiplayer-services` (sessions,
matchmaking, relay) and `unity-vivox` (voice and text channels); the topology decision behind them
is `unity-multiplayer`. Purchases and ads are `unity-monetization`, and provider-agnostic cloud
backend method belongs to a backend skill that is not tied to a provider. For a third-party API
(§6), that provider's own request and response schema, which this skill deliberately does not
restate for any provider.
