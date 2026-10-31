---
name: unity-live-services
description: >-
  START HERE for any backend, online or monetisation request: accounts, cloud data, multiplayer, voice, purchases, ads or a third-party API.
  Routes to the API skill.
---

# unity-live-services — the parts that are not an API call

> **A backend turns a game you ship into a service you run.** The API is the small part. The
> decisions below are the ones that are painful to reverse after real players have data.

## Request → where to go

This skill is the entry point for everything that leaves the device. It routes the call-by-call
work to the API skill that owns it and keeps the decisions none of those APIs can make for you.

| Request or symptom | Go to |
|---|---|
| Accounts, sign-in, cloud save, remote config, economy, leaderboards, cloud code, analytics — the calls | `unity-ugs` |
| Adding any of those to a game that has none; dev and production data got mixed up | §1–§5 here, then `unity-ugs` |
| "Peer-to-peer, listen server or dedicated?"; a cheater affected someone else; lobby and game disagree; a player lost signal | [`reference/multiplayer.md`](reference/multiplayer.md) |
| Sessions, lobbies, matchmaking, relay, dedicated-server sessions — the calls | `unity-multiplayer-services` |
| Voice or text chat channels, tokens, the participant roster | `unity-vivox` |
| Voice chat broke another microphone feature; mute is not instant; works in two editors, not on two phones | [`reference/multiplayer.md`](reference/multiplayer.md) §3–§4 |
| Netcode APIs — client prediction, sending input or turns, networked scene management | Out of scope for this plugin; the topology and authority they implement: [`reference/multiplayer.md`](reference/multiplayer.md) |
| In-app purchases: store connection, catalogue, purchase flow, receipts | `unity-iap` |
| Ad mediation, ad units, privacy-consent APIs | `unity-ads-levelplay` |
| Purchases work in the editor, not on device; an SDK broke the build or added permissions; store declarations; where receipts are validated | [`reference/monetization.md`](reference/monetization.md) |
| The game calls a third-party HTTP API, or the player supplies their own key | §6 |
| Persistent player data, currency, unlocks — who is believed | §3 |

## Symptom → section

| Symptom | Go to |
|---|---|
| A tester's progress reset, or test rows appeared in production | §1 |
| "Where do I put this key?" | §2 |
| A player has currency or an unlock they did not earn | §3 |
| The game hangs on a spinner, or the menu will not open offline | §4 |
| A reward was granted twice after a timeout | §4 idempotency |
| Server logic exists only in a web console | §5 |
| A key appeared in a screenshot, a log or a bug report; "what may this build send off the device?" | §6 |

Provider-agnostic backend discipline — where secrets live, fail direction, deploy ordering,
emulate-locally-first — belongs to a backend skill that is not tied to a provider, rather than
here. This skill is the Unity-shaped subset. Settle the questions here, write the calls in the API
skill, and return before a build points at production.

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
treat as untrusted. **Validation lives beside the data, not in the caller.** A rule enforced
only by the client that happens to write is a rule with no enforcement.

Cloud Save gives you that split as a storage property: Default (the owner reads and writes),
Public (anyone reads, the owner writes), Protected (the owner reads, only server code writes) and
the game-wide Custom (every player reads, only the server writes). **Protected is the list above,
expressed in the backend** — a client-side write of it fails rather than succeeding quietly. The
classes, the write-lock and the policy files are `unity-ugs`.

## 4. Design the offline path first

> **Every backend call fails sometimes** — no signal, a token expired mid-session, a regional
> outage, the player put the phone in a tunnel.

- **Decide per feature what happens when it is unreachable,** before writing the call. "It shows
  a spinner forever" is the default you get by not deciding.
- **Never block the main menu or the first play on a network round trip.** A backend outage
  should degrade the game, not close it.
- **Sign-in surprises people:** an anonymous session that silently fails means a returning player
  looks like a new one and starts over. Fail loudly towards the player, not silently towards the
  save file.
- **Writes need idempotency.** A retry after a timeout that already succeeded must not grant the
  reward twice: a client-generated operation id, checked server-side.

## 5. Cloud Code is source code

It is the part that most often ends up edited in a web console and existing nowhere else.

- **In the repo, reviewed, and deployed by the same pipeline as the game.** Remote Config
  entries, access policies, Cloud Code module references, leaderboard and economy definitions and
  audience overrides live on disk as `.rc` / `.ac` / `.ccmr` / `.lb` / `.ec*` / `.ugo`, among
  others. If a service's configuration exists only as console state and none of those files is
  committed, the environment cannot be rebuilt and a change cannot be reviewed. `unity-ugs` holds the full
  table and which package each file type needs.
- **Deploy server logic that tolerates both the old and the new client *before* shipping the
  client that needs it.** Players update on their own schedule, and some never do.
- **Config and schema changes are one-way once live data exists.** A field rename is an additive
  migration, never a rename.

## 6. When the backend is somebody else's HTTP API

A game that calls an LLM, a translation service or any other third-party API has §2's credential,
§3's trust and §4's failure problems at once — and **the key may belong to the player**. All of it,
with test shapes and artifact greps:
[`reference/third-party-api-keys.md`](reference/third-party-api-keys.md).

- A player-supplied key is entered in-app, stored on the device, passed to the transport at call
  time; the build ships no key. On *your* account, it is a thin proxy you operate.
- Mask the key wherever it renders, the entry field included; a screenshot, recording or log
  containing it is a **rotation** event. It never enters a log line, analytics event or error
  string.
- What leaves the device is an explicit allow-list of derived values, pinned by a test on the
  serialised payload and again on the body the transport received.
- An injectable transport, a persisted consent gate before the first send, figures computed
  locally, and a response cache keyed on what changes it.

## Verification

- Cold start with the network disabled — the game must reach playable.
- Kill the network mid-session and restore it — no duplicate grants, no lost writes.
- A build's environment must be readable from a screenshot of it.
- Grep the built artifact for anything that looks like a key — yours *or* a player's
  ([`reference/third-party-api-keys.md`](reference/third-party-api-keys.md);
  `unity-android-release` → `reference/artifact-verification.md`).
- For a third-party API: the whole flow with a fake transport and the network off, asserting the
  captured body holds no player identity.
- Multiplayer and monetisation carry their own checks in their reference files.

## Scope — what this skill does NOT do

Every API call. `unity-ugs` owns the UGS surface (packages, initialisation order, Cloud Save,
Cloud Code, Remote Config, deployment files); `unity-multiplayer-services` sessions, matchmaking
and relay; `unity-vivox` voice and text channels; `unity-iap` the purchase flow and receipts;
`unity-ads-levelplay` mediation and consent. Netcode APIs, pricing and monetisation design, server
fleet operations and provider-agnostic cloud backend method are out of scope; so is a third-party
provider's own request and response schema.
