# Remote Config, Access Control, deployment, the four clients, Building Blocks

Moved out of SKILL.md, which keeps §1–§4 (packages, the order, Cloud Save access classes, Cloud Code for integrity) and §10 (three shapes); numbering continues it.

## 5. Remote Config holds the definitions; Game Overrides do the A/B

Remote Config stores what exists in the game — the achievement list, battle pass tiers, the shop
catalogue, feature flags — as typed entries fetched in one call and deployed as `.rc` files.
**Remote Config on its own has no A/B testing.** Game Overrides (`.ugo`, from
`com.unity.services.tooling`) replace values for a named audience, and `FetchConfigsAsync`
returns the overridden value — which is why a value right in the dashboard arrives wrong in a build.

Fetch and `.rc` format: [`reference/remote-config.md`](remote-config.md). Overrides:
[`reference/tooling.md`](tooling.md).

## 6. Access Control: deny wins

An `.ac` policy permits or denies access to UGS resources by URN, per principal (`Player` or
`ServiceAccount`), for `Read`, `Write` or both. **Deny takes precedence over Allow**, so the
workable shape is a blanket deny for `Player` on `urn:ugs:*:/**` plus explicit allows for the
endpoints a client legitimately calls. This is the enforcement half of §4: with a policy deployed
a direct write returns `403`, which also breaks any build still writing directly.

URNs and a full deny-then-allow policy: [`reference/tooling.md`](tooling.md).

## 7. What the Deployment Window pushes

**Services > Deployment** discovers UGS resource files under `Assets/`, targets one environment
and pushes them. A file type appears only if the package that registers it is installed: `.rc`
`.ac` `.ugo` `.ccmr` `.js` `.lb` `.ecc` `.eci` `.ecv` `.ecr` `.ddef`, plus Game Server Hosting
build config `.gsh` and Matchmaker queue config `.mmq` from `com.unity.services.multiplayer` —
same window, same environment picker, authored by `unity-multiplayer-services`. The UGS CLI does
the same job outside the Editor, and is unrelated to the `unity` CLI that `unity-cli` covers.

Per-type packages, `.ddef` scoping, the programmatic API and the UGS CLI:
[`reference/deployment.md`](deployment.md).

## 8. Services APIs — four clients, four trust levels

`com.unity.services.apis` is the generated REST layer under the friendly SDKs, for what they have
no path for — in practice, admin writes. `IGameClient` (player device, the signed-in player),
`IServerClient` (dedicated server, server key), `ITrustedClient` (dedicated server needing any
player's data, service account), `IAdminClient` (**Editor only**, service account key id + secret).
`IAdminClient` is the only supported way to write Cloud Save Custom data or give an Editor tool or
a custom deploy command elevated rights; its key is never in the project (`unity-live-services`
§2). Service areas: [`reference/apis.md`](apis.md).

## 9. Building Blocks and samples — start from one

Unity publishes free Building Block packages on the Asset Store — Achievements, Leaderboards,
Player Account, Multiplayer Session, Matchmaker Session — each a working vertical slice with UI,
runtime code, Cloud Code modules and cloud resource files. For "add achievements" or "add
leaderboards", import one and read it first; §10's blueprints then annotate something that runs.
`com.unity.starter-kits` returns 404 on the public registry: use the Asset Store links. Links,
dependencies, samples: [`reference/building-blocks.md`](building-blocks.md).
