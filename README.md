# unity-dev-skills

**English** · [繁體中文](.github/README.zh-TW.md) · [简体中文](.github/README.zh-CN.md) · [日本語](.github/README.ja.md)

Unity 6 game-development skills for AI coding agents. Fifty-seven skills covering every stage of
making a game, from concept to a verified build — installable into Claude Code or OpenAI Codex.

Three things make this different from a pile of Unity notes:

1. **It is self-contained.** No skill tells you to go install something else first. They route to
   each other through their own `Scope — what this skill does NOT do` sections, so you land in the
   right one from any direction.
2. **Each skill is a method you run on your own project.** What to check, how to check it, and the
   code that does it — Python in `scripts/`, C# and shader source in `resources/`, whole files to
   copy in `templates/` — not notes to retype.
3. **Skills are split by loading situation, not by topic.** A `SKILL.md` is a router with a symptom
   table, and depth lives in the `reference/` files it names, so a skill only pulls in what the
   situation needs.

## Install

```bash
claude plugin marketplace add tipoLi5890/unity-dev-skills
claude plugin install unity-dev@unity-dev
```

Codex reads the same tree: point it at `.agents/plugins/marketplace.json`, or at
`.codex-plugin/plugin.json` for the plugin on its own. Both are generated from the Claude-format
manifests, so they cannot come to say anything different.

Or drop the skills straight into a project — copy `skills/*` into `<project>/.claude/skills/`.

## The skills

The groups follow the stages a game moves through, top to bottom. For any gameplay request,
start at `unity-gameplay`: it reads the project and routes to the rest.

| Group | Skill | Load it when |
|---|---|---|
| **Every stage — terminal & search** | `unity-cli` | Driving Unity from a terminal: editors, licences, templates, CI, MCP, and exit codes that say whether a retry is honest |
| | `unity-search` | "Find it / where is it / what references it" as one Unity Search query — type filters, folders, labels, `ref=` relationships, scene component queries — shown before it runs, and opened in a live Editor when there is one |
| **Concept** | `unity-game-brief` | The first hour, before any Unity work: one line of idea into a one-page experience brief, the look locked with images, an architecture proposal derived from the constraints, invariants, and one interaction a human can play |
| | `unity-new-project` | Decisions that are expensive to retrofit: editor pinning, `.meta`/LFS, UPM tag pinning, IL2CPP/ARM64, asmdef boundaries |
| | `unity-gameplay` | **Start here for any gameplay request that names no perspective.** Fingerprints the project — 2D or 3D, projection, view, movement model — and routes controls, camera, animation and verification; owns genre recipes written as constraints, level metrics derived from the controller's numbers, and production stages with exit checks |
| **3C prototype** | `unity-input` | Player input that gameplay reads as one struct, never a device: an actions asset for keyboard, gamepad and touch, presses latched in `Update` and spent once in `FixedUpdate` — the jump that goes missing or fires twice — plus buffering, on-screen sticks, pointer aim and rebinding |
| | `unity-camera` | A camera that jitters, shows outside the level or clips through walls: the two clocks behind the jitter, Cinemachine rigs for 2D follow with a room confiner, pixel-perfect follow, third-person orbit and first person, shake and blends, the 2.x → 3.x name table, and a journey that proves a rig holds |
| | `unity-2d-controller` | A 2D character that slides down slopes, sticks to walls or jumps a different height every time: a kinematic platformer motor that asks physics where the ground is — slopes, one-way and moving platforms, coyote time, variable jump, dash, wall jump — free top-down movement with aim split from move, cell steps shown as tweens, the Animator bridge, and journeys that prove apex, coyote and buffer |
| | `unity-3d-controller` | A 3D character whose `isGrounded` flickers, that slides down the ramp, refuses the step or jumps a different height at another frame rate: one owner of the transform, a `CharacterController` motor that finds ground by its own cast — slopes, steps, moving platforms — third-person, first-person, top-down and lane-runner controllers reading one input struct, the Animator bridge, and journeys that prove ramp, step, apex and lane change |
| | `unity-animation` | An Animator that disagrees with the game — stuck in a state, an attack that plays by itself, a hitbox that stays on: one writer per parameter, blend trees and sprite state graphs built from script, events and attack windows that survive interruption, IK, Timeline handover, root motion |
| | `unity-physics-2d` | `OnCollisionEnter2D` or `OnTriggerEnter2D` that never fires, a bullet through a tilemap wall, a ground check that hits the player itself, a runner that snags on tile seams: a triage ladder in Box2D's own vocabulary, a two-sided probe and a read-only scene audit |
| | `unity-physics-3d` | A collision or trigger that never fires, tunnelling, a raycast that misses |
| | `unity-play-harness` | Making the game drivable and readable: a one-line probe snapshot, named situations that boot straight into a moment and wait on a readiness set, journey tests that assert invariants, a feel complaint turned into a repeatable test — for a 3D or a 2D game |
| **Vertical slice — 2D world** | `unity-2d-level` | A 2D level put together as data: a serialisable level painted into a fixed stack of Tilemap layers, runtime tile edits, rooms and doors, chunks stitched into an endless run, Tiled and LDtk import, SpriteShape terrain, and seeded generation with reachability checked per level |
| | `unity-2d-grid` | Board logic for tactics games and tile puzzles on rectangular, isometric and hexagonal grids, as plain C# with no scene: hex offset, axial and cube conversion, movement range, A* paths, lines of sight, one occupancy map, push rules, turn order, undo, pointer to cell |
| | `unity-tilemap` | Tile Palettes for rectangular, hexagonal and isometric grids, and RuleTiles built from a terrain sheet you already have |
| | `unity-2d-rendering` | A sprite that draws behind the wrong one, a `Light2D` that does nothing or turns everything black: the four sorting keys in priority order, `SortingGroup`, Y-sort for top-down, isometric and hex scenes, shadow casters, normal maps, sprite masks and parallax layers |
| **Vertical slice — 3D world** | `unity-3d-level` | A 3D level built to its metrics before art exists: a greybox from a metrics sheet — door, corridor, step, ramp, jump gap — proven by a walk journey, a modular kit on a 1/2/4 m grid, prefab structure with an override audit, collision proxies on one layer, Terrain, spline roads and lanes, and URP decals |
| | `unity-lighting` | A bake that did nothing, a character black beside baked walls, the sky reflected indoors, shadows that flicker or stop a few metres away: a symptom ladder over light modes, the bake, probes, shadows and the environment on URP, a read-only scene audit, a bake that reads its result back, and the subset a phone can afford |
| | `unity-navigation` | NavMesh, agents, obstacles, links — and deciding who owns the transform |
| **Vertical slice — systems** | `unity-interaction` | Making things usable — "press E to open the door", a prompt that flickers between two objects, a gate that opens twice, a switch used through a wall, a coin collected twice: one `IInteractable` contract, an interactor that keeps one selected target found by perspective, one prompt, pickups, switches, gates as state machines, locked doors, pointer hotspots, and a journey proving a gate opens once |
| | `unity-combat` | One swing that deals damage twice, a sword that hits every frame, spikes that drain every heart, a shot straight through the sentry: a damage struct and a receiver with teams, invincibility and death as a state, hit and hurt layers, query hitboxes that own a swing id and a hit list, opened by animation windows, knock-back through the motor, cast-per-step projectiles and bullet patterns as data — in 2D and 3D |
| | `unity-game-ai` | An enemy that sees through walls, never gives up, flickers between two states or raycasts every frame: perception on a budget, decisions on a tick and movement left to whoever owns the transform — a code state machine, a small behaviour tree, a vision cone, hearing and memory, patrol and chase, 2D pathfinding, wave spawners, turn-based move scoring, and a journey proving the sentry chases only after it sees |
| | `unity-scene-flow` | Managers duplicated after a return to the menu, a loading screen stuck at 90%, a pause that stops nothing, a corrupted save: a Boot scene that never unloads and owns the services, additive loading with one operation in flight, a game phase machine in which pause is a state, a versioned save with migrations and an atomic write, checkpoints that rebuild, object pools, ScriptableObject config |
| **Vertical slice — UI** | `unity-game-ui` | **Start here for any UI request.** Detects the project's UI system and routes; owns the runtime `OnGUI` HUD nobody else documents |
| | `unity-ui-ugui` | Canvas, RectTransform, Layout Groups — and the six ways uGUI renders nothing |
| | `unity-ui-toolkit` | UXML/USS, flex, Painter2D — and the properties USS silently ignores |
| **Production — assets** | `unity-3d-models` | Static props: importing AI-generated meshes — inspect first, decimate what is over budget, before Unity ever sees them |
| | `unity-rigged-character` | A playable character: art → image-to-3D → Mixamo → Avatar → Animator → gameplay rig — or, for proportions Mixamo cannot rig, an FBX from `blender-character-rig` in Mixamo's place |
| | `unity-2d-sprites` | Sprite sheets, slicing, pivots, 9-slice, and a set of frames turned into a playable `AnimationClip` — metadata that lives inside the importer |
| | `unity-2d-animation` | Skeletal 2D characters with the 2D Animation and PSD Importer packages: a PSB imported as a rig, bones then geometry then weights, `SpriteSkin` and CPU or GPU deformation, Sprite Library skins and equipment swapped at runtime, 2D IK, and an audit of what a rig costs |
| | `unity-2d-pixel-perfect` | Pixel art that renders soft, shimmers as the camera moves, or shows hairline seams — and which of the two components called `PixelPerfectCamera` you actually have |
| | `unity-sprite-atlas` | Sprites that should share a draw call: V2 atlases from script, packing and platform settings, and how the packed texture reaches the player |
| | `unity-audio` | Memory, load types, sample rates, mixer cost — reports before it reimports |
| | `unity-localization` | Shipping in more than one language, and the CJK font pipeline where it goes wrong |
| **Production — AI asset generation** | `codex-visual` | 2D art through the `codex` image model, held on-style by one art bible and one anchor: grid one-shot sets, short animations generated as one gridded sheet and sliced into measured frames with a GIF preview, chroma-key transparency, normalised sizes and a geometry gate on the shipped files |
| | `comfyui-asset-generation` | Music, SFX, MiniMax H3 video and image-to-3D props through a self-hosted ComfyUI — one job at a time, `/history` as the only proof, `/free` before a model switch |
| | `blender-character-rig` | An image-to-3D character rigged and animated in a running Blender through its MCP server: bones from measured landmarks, weights computed by position, a prop on a hand bone, a keyed action, a preview, and an FBX proven by re-import |
| | `blender-retarget` | Stock clips moved onto a character rigged in Blender: through Auto-Rig Pro or a pure-bpy bone map that converts each rotation key between the two rest poses, a clip manifest, a local weight repair, an action library with an NLA review track, a prop checked against its hand bone in every clip, and an audit that re-opens the saved file |
| **Polish & optimisation** | `unity-game-feel` | A hit with no impact, a game left frozen after a hit, an enemy that stays white after its flash, thirty pickups playing thirty sounds, a pad that keeps vibrating: one feedback row per gameplay event with a budget — hit stop through one owner of `Time.timeScale`, flashes that restore, squash and tweens with no library, particles, trails, pooled SFX with a voice cap, rumble that stops |
| | `unity-render-urp` | Post-processing that will not appear, the mobile subset, Render Graph review |
| | `unity-urp-migration` | Moving a Built-in project to URP in five gated phases read back from the saved project, and diagnosing one that was half-moved: magenta materials, PPv2 into a Volume, lightmaps that never rebaked, `GrabPass`/`OnRenderImage` |
| | `unity-profiling` | What a slow or uneven frame is actually doing: counters without the Profiler window, 90-frame windows with median/p95/worst, work counters, a before/after table |
| | `unity-scene-optimisation` | The change to make once a profiling counter has named the cost: batching paths and why GPU instancing does nothing under URP, `LODGroup` and Mesh LOD, baked and GPU occlusion culling, per-layer cull distances, texture size and mipmap streaming, sprite and particle overdraw — each lever tested in one window first and read back on the same counter |
| | `unity-debug` | You need to verify a change you cannot see — and to prove the harness is telling the truth before believing it |
| **Shipping** | `unity-device-testing` | Acceptance on a **real phone**, Android or iOS: a probe scene that logs one tagged line per state change, a driver that asserts on it and taps system dialogs, a human asked for one physical action at a time and verified from the device, and exit codes that separate a real failure from a broken harness |
| | `unity-android-release` | Build it, then *prove* it: read the artifact back, keystore and versionCode discipline |
| | `unity-ios-build` | From a Unity project to a process on an iPhone without opening Xcode: headless build, an unsigned compile gate, signing with what this Mac actually holds, `devicectl` install, the console as the only log, and native `.mm` plugins iterated in 30 s |
| | `unity-web-release` | WebGL/WebGPU download size, the server headers, browser memory ceilings |
| **Backend & commerce** | `unity-live-services` | Which environment a build talks to, where keys live, designing the offline path first |
| | `unity-ugs` | The Gaming Services API surface: which package provides what, the initialisation order everything else depends on, Cloud Save access classes, Cloud Code, Remote Config |
| | `unity-iap` | In-App Purchasing v5 call by call: connecting to a store, the pending/confirm flow, receipts, entitlement, restore — and content granted twice or not at all |
| | `unity-ads-levelplay` | LevelPlay mediation: native dependency resolution, consent before init, rewarded/interstitial/banner units, impression-level revenue |
| | `unity-monetization` | Where IAP and ad SDKs collide with shipping: merged manifest, store declarations, receipts |
| | `unity-multiplayer` | Topology as the expensive decision, plus voice chat and microphone contention |
| | `unity-multiplayer-services` | Sessions: how players get into a game together — join codes, a browsable game list, quick join, ticket matchmaking, relay, host migration, dedicated servers |
| | `unity-vivox` | Voice and text chat call by call: sign-in, group/echo/positional channels, the roster, mute and push-to-talk, microphone permission |

## Working on this repo

```bash
python3 tools/lint-skills.py            # frontmatter + name/dir match + size limits + executable syntax
python3 tools/check-consistency.py      # manifests agree, companions declared
python3 tools/sync-codex-manifests.py   # regenerate the Codex manifests
claude plugin validate .                # manifest shape
```

`.claude-plugin/*` are the sources of truth. `.codex-plugin/plugin.json` and
`.agents/plugins/marketplace.json` are **generated — never hand-edit them.**

Routing to a plugin outside this repo is a declared dependency: add it to `COMPANIONS` in
`tools/check-consistency.py`, with the reason. An undeclared one fails the gate.

What this release contains: [CHANGELOG.md](CHANGELOG.md).

## Licence

MIT — see [LICENSE](LICENSE).
