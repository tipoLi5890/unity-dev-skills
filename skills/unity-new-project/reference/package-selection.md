# Turning a concept into a package list

> Part of the `unity-new-project` skill. The tables below are a **starting point for subtraction**,
> not a manifest. How the install is actually executed — the async deadlock, the verification, the
> registry check — is `reference/package-bootstrap.md`; this file only decides *what goes in the
> list*.

## The method, in three moves

1. **Read the concept back as needs, not as products.** "Runner on a tablet, three lanes, one
   thumb" is *modern input*, *2D sprites*, *a camera that follows*, *text* — four needs. A genre
   label is not a package list, and neither is a wishlist.
2. **Look up each need below and write down the id.** One id per need. Resist the urge to add the
   thing you will "probably want later": an unused package still costs resolve time, build size and
   a compile dependency, and removing it later is a manifest edit nobody wants to make.
3. **Subtract whatever the template already ships.** This is the step that gets skipped, and it is
   where the list actually shrinks. A URP template already carries the render pipeline and usually
   the Input System; a 2D template already carries most of the 2D feature set. Open
   `Packages/manifest.json` on the *created* project, cross off every id already there, and install
   the remainder in one pass.

**Do not pin a version** unless something states a minimum. Resolution without a version takes the
latest release compatible with the editor, which is what you want on day one; a pin is a promise to
maintain that number.

## Confirm the id before it goes in the list

An id you recalled is a guess. `Client.SearchAll()` inside the Editor lists every package the
project's registries offer, with each one's versions — one call, and it settles spelling, existence
and the available range at once. From a terminal, a single known id can be checked against the
registry without an Editor, but there is **no free-text search endpoint** and built-in packages are
not on the registry at all — both traps, with the `curl` form, are in
`reference/package-bootstrap.md`.

## Every project, more or less

| The need | Id | Why it is on this list |
|---|---|---|
| Text on screen | `com.unity.ugui` | uGUI, and TextMeshPro rides along inside it. UI Toolkit needs no package — it is in the Editor |
| Input from anything | `com.unity.inputsystem` | One action map serves touch, keyboard and gamepad; the legacy Input Manager makes that a rewrite |
| Tests that a command can run | `com.unity.test-framework` | Usually already present. Without it there is no test lane at all |
| A camera that follows, frames and shakes | `com.unity.cinemachine` | Cheap to add, unpleasant to hand-roll — 3D and most 2D alike |
| Content that ships after the build | `com.unity.addressables` | Add when download size matters or content updates are planned, not before |

## Render pipeline — exactly one, and usually the template already chose

| Choice | Id | Choose it when |
|---|---|---|
| Universal (URP) | `com.unity.render-pipelines.universal` | The default answer: mobile, web, 2D, most 3D. Widest platform reach |
| High Definition (HDRP) | `com.unity.render-pipelines.high-definition` | Desktop and console fidelity only — not mobile, not web |
| Built-in | *(no package)* | A throwaway prototype, or an existing project you are not migrating |

Swapping later touches every material, which is why `SKILL.md` §1 makes this a creation-time
decision rather than a package-list one.

## Dimension and look

| Look | Id |
|---|---|
| 2D of any kind | `com.unity.2d.feature` — the bundle: sprites, tilemap, animation, pixel-perfect |
| Pixel art specifically | `com.unity.2d.pixel-perfect`, already inside the bundle above |
| Anything that has to walk around a 3D level | `com.unity.ai.navigation` |
| Cutscenes, scripted sequences, timed juice | `com.unity.timeline` |
| Logic authored as graphs rather than code | `com.unity.visualscripting` |

## What the game does

Read down the left column for the closest description, then **add** the foundation rows above.

| The game is | Add |
|---|---|
| Endless or level-based running, jumping, dodging | Render pipeline, Input System, Cinemachine, plus the 2D bundle if it is 2D and AI Navigation if the hazards chase |
| Cards, tiles, matching, a board | Render pipeline or the 2D bundle, Input System, uGUI/TextMeshPro, Timeline for the reveal animations |
| Seen from above, moving and aiming at once | Render pipeline, Input System, Cinemachine, AI Navigation |
| Long-form, with inventories, quests and areas | All of the above plus Addressables and Timeline — this is the list that grows fastest |
| Vehicles and contact | Render pipeline, Input System, Cinemachine. Physics is in the engine; there is no package |
| Tapping, waiting, numbers going up | The 2D bundle or a render pipeline, Input System, uGUI/TextMeshPro — and stop there. Lean is the feature |
| Players in the same match | `com.unity.netcode.gameobjects` for the simulation and `com.unity.services.multiplayer` for getting them together; the topology decision comes first — `unity-multiplayer` |

## Target platform

**Platform support is an Editor module, not a package.** Android, iOS, web and each console are
installed with the editor (`unity install <version> --module …` — `unity-cli`), and no id in any
table above adds one. A project that builds nothing for Android is missing a module, not a package.

What the platform does change is the shape of the list:

| Target | What it argues for |
|---|---|
| Phones and tablets | URP over HDRP; Addressables so the initial download stays small; as few dependencies as the concept allows |
| Web | URP, never HDRP; every package earns its download — `unity-web-release` |
| Desktop and console | URP or HDRP by how much fidelity the art is actually built for |

## Money

Install the package now so the manifest is complete; do the wiring in the skill that owns it.

| Goal | Id | Wire it up in |
|---|---|---|
| Selling things inside the app | `com.unity.purchasing` | `unity-iap` |
| Ads and mediation | `com.unity.services.levelplay` | `unity-ads-levelplay` |
| Accounts, saves, currency, remote values, leaderboards | The UGS set — `com.unity.services.core` and `com.unity.services.authentication` first | `unity-ugs`, with the discipline in `unity-live-services` |

Which of the UGS ids a given feature actually needs, and the order they initialise in, is
`unity-ugs`; picking whether to monetise at all is `unity-monetization`.

## A worked subtraction

The courier-run prototype: three 1.3-unit lanes, a runner dodging hazards and collecting pickups,
a gate and a sentry, three buttons on a gamepad, read on a tablet held at 2–3 m.

Needs, in order: input from a gamepad; 2D sprites; a camera that stays with the runner; text for
the pickup counter; nothing streamed, nothing sold, nobody else in the match.

| Id | Verdict |
|---|---|
| `com.unity.render-pipelines.universal` | Template already has it — **cross off** |
| `com.unity.2d.feature` | Template already has it — **cross off** |
| `com.unity.ugui` | Template already has it — **cross off** |
| `com.unity.inputsystem` | Present but stale in the template's locks; it is reinstalled by the fix in `reference/package-bootstrap.md`, not added here |
| `com.unity.cinemachine` | **Install** — the only genuine addition |
| `com.unity.addressables` | No streamed content on day one — **leave out** |
| `com.unity.ai.navigation` | The sentry moves on a fixed lane path — **leave out** |

One id installed out of seven considered. That ratio is normal, and a list that does not shrink at
step 3 is a list assembled from a genre label rather than from the concept.
