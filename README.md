<div align="center">

<h1>unity-dev-skills</h1>

<p><b>Unity 6 skills that make Claude Code and Codex work like a careful Unity developer — and prove each step.</b></p>

<p><i>61 skills from the first idea to a build on a real phone.</i></p>

<p>
<a href=".claude-plugin/plugin.json"><img alt="version" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FtipoLi5890%2Funity-dev-skills%2Fmain%2F.claude-plugin%2Fplugin.json&query=%24.version&label=version&color=blue"></a>
<a href="https://github.com/tipoLi5890/unity-dev-skills/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/tipoLi5890/unity-dev-skills/actions/workflows/ci.yml/badge.svg"></a>
<a href="LICENSE"><img alt="licence: MIT" src="https://img.shields.io/badge/licence-MIT-green"></a>
<img alt="Unity 6" src="https://img.shields.io/badge/Unity-6-black?logo=unity">
<img alt="works with Claude Code · Codex" src="https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Codex-d97757">
</p>

<p><b>English</b> · <a href=".github/README.zh-TW.md">繁體中文</a> · <a href=".github/README.zh-CN.md">简体中文</a> · <a href=".github/README.ja.md">日本語</a></p>

<img src=".github/media/hero.jpg" alt="Two rows, each one character through four skills. Top, 2D: a character still, the same character keyed onto transparency, a strip of its run loop, and the sprite running in a Unity scene. Bottom, 3D: a concept drawing, its generated 3D mesh, the rig's joint markers, and the rigged character in an extreme pose" width="100%">

</div>

## Try asking

| You say | What happens |
|---|---|
| "The runner's jump doesn't always register." | `unity-input` latches each press in `Update`, spends it once in `FixedUpdate`, and a journey test proves one press gives one jump |
| "The sentry sees the runner through walls." | `unity-game-ai` builds the vision cone from distance, angle and one line-of-sight cast; a journey proves the chase starts only after sight |
| "It hitches when the third pickup spawns." | `unity-profiling` samples that moment in 90-frame windows (median, p95, worst), reads the work and GC counters, and compares before and after |
| "Turn this drawing of the runner into a character that runs in Unity." | `game-character-pipeline` sets the quality target and route first, then hands stages S0–S13 — views, 3D, rig, motion, import — to the skill that owns each, gated |
| "Show me the courier run before we write code." | `unity-game-brief` builds a timed simulated-gameplay preview from the game's own rule constants, with every sound logged |
| "Make a walk loop from this still of the runner." | `sprite-from-video` has a video model walk the still in place, keys every frame against the key the model actually painted, finds the loop by measurement, and writes equal-canvas frames plus `frames.json` |
| "Put it on my iPhone — without opening Xcode." | `unity-ios-build` runs a headless build, a compile gate, signing with what your Mac holds, a `devicectl` install, and reads the app's console |

## Install

```bash
claude plugin marketplace add tipoLi5890/unity-dev-skills
claude plugin install unity-dev@unity-dev
```

**Codex** reads the same tree: point it at `.agents/plugins/marketplace.json`, or at
`.codex-plugin/plugin.json` for the plugin on its own. Both are generated from the Claude-format
manifests, so they cannot come to say anything different.

**Or copy** the skills straight into a project: `skills/*` into `<project>/.claude/skills/`.

### Requirements

- **Required:** Claude Code or Codex; a Unity 6 project; Python 3.10 or newer for the scripts, with
  NumPy and Pillow for the ones that read images or audio.
- **Optional, for the asset and character pipeline only:** Blender, in a version your Auto-Rig Pro
  release supports (`character-autorig` explains); Auto-Rig Pro under your own licence; a
  self-hosted ComfyUI on a GPU machine; the `codex` CLI for 2D art; SciPy for `mesh-texture-paint`.
- **Optional, for video:** ffmpeg, for anything that writes one (previews, reels, sprites from video).
- **Optional, for devices:** a Mac with Xcode 15 or newer for iOS; the Android SDK for Android.

Work inside Unity needs none of the asset-pipeline or video tools; a phone build needs only what
that platform already asks for.

## See it work

### See the game before code

<div align="center">
<img src=".github/media/preview.gif" alt="A top-down courier run: the runner runs up a three-lane road, picks up parcels, passes a sentry, goes through one gate while it is open and hits the next once it has closed" width="400">
<p><sub>A simulated-gameplay preview of the courier run, drawn with the game's own art.</sub></p>
</div>

[`unity-game-brief`](skills/unity-game-brief/SKILL.md) →
[`codex-visual`](skills/codex-visual/SKILL.md)

Every pickup and gate is timed from the game's own rule constants and logged as an event, before
any code is written.

### From one still to a sprite that runs in Unity

<div align="center">
<img src=".github/media/sprites.gif" alt="Left: the runner's still on a green key. Right: four transparent animations of the same runner playing side by side on a checkerboard: idle, walk, run and jump" width="800">
<p><sub>One still on a green key: a breathing idle made from the still alone, then walk, run and jump cut from generated video.</sub></p>
</div>

<div align="center">
<img src=".github/media/keying.jpg" alt="The same close-up of the runner's hair and face keyed two ways: a plain green key leaves a bright green rim; sprite-from-video leaves a clean edge" width="640">
<p><sub>A plain green key leaves a green rim; <code>sprite-from-video</code> keys against the green the model actually painted and removes the spill.</sub></p>
</div>

<div align="center">
<img src=".github/media/unity.gif" alt="A Unity 6 2D scene: the runner sprite runs along a street, jumps three traffic cones, collects parcels, then runs through a gate and stops" width="720">
<p><sub>The same sprites in Unity 6: the runner jumps every cone, collects every parcel and runs through the gate.</sub></p>
</div>

[`codex-visual`](skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](skills/comfyui-asset-generation/SKILL.md) →
[`sprite-from-video`](skills/sprite-from-video/SKILL.md) →
[`unity-2d-sprites`](skills/unity-2d-sprites/SKILL.md) →
[`unity-2d-controller`](skills/unity-2d-controller/SKILL.md)

### From a dull generated texture to one that matches the concept

<div align="center">
<img src=".github/media/texture.gif" alt="A turntable in four columns: the runner with the texture image-to-3D baked, the same runner repainted, then the courier backpack baked and repainted. The repainted versions have brighter, cleaner colours and sharper details: the face, the gloves, the straps and their stitching" width="800">
<p><sub>Same meshes, same UVs. In each pair, left is the texture image-to-3D baked; right is the texture repainted from the concept art.</sub></p>
</div>

<div align="center">
<img src=".github/media/texture-steps.jpg" alt="Five panels of one camera: the concept art from behind, the untextured mesh, the render handed to the model (painted views in colour, the rest shown with the baked texture as a prior), the model's repaint, and the mesh after the repaint is projected into its texture" width="800">
<p><sub>One step of the loop: render what is painted so far, have a local edit model repaint that view against the concept art, gate it, project it into the UV texture, then pick the next camera.</sub></p>
</div>

[`codex-visual`](skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](skills/comfyui-asset-generation/SKILL.md) →
[`mesh-texture-paint`](skills/mesh-texture-paint/SKILL.md)

Image-to-3D gets the shape right and the colours muddy. This keeps the mesh, its UVs and its baked
normal and occlusion maps, and repaints only the base colour, one camera at a time, on your own
ComfyUI. Every view is checked against the render before it touches the texture (outline, collage,
colour drift, a washed-out background), and a close-up pass on the head sharpens the face.

### From one drawing to a moving, rigged character

<div align="center">
<img src=".github/media/motion.gif" alt="Top: a machine-generated two-camera video of the character, front and side. Bottom: the character's rig driven by the motion solved from that video" width="640">
<p><sub>Top: a generated two-camera video. Bottom: the character's rig, driven by the motion solved from it.</sub></p>
</div>

[`codex-visual`](skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](skills/comfyui-asset-generation/SKILL.md) →
[`mesh-texture-paint`](skills/mesh-texture-paint/SKILL.md) →
[`character-autorig`](skills/character-autorig/SKILL.md) →
[`humanoid-motion`](skills/humanoid-motion/SKILL.md) →
[`unity-rigged-character`](skills/unity-rigged-character/SKILL.md)

The 3D model, the rig and the motion are made on your own machines; only the 2D art goes through
the `codex` CLI. The two-camera solve is ported from [anymove](https://github.com/patch-gg/anymove) (Apache-2.0;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
The sprite clips and the motion video are machine-generated with MiniMax H3, run locally on its open
weights under the MiniMax H3 Community License Agreement.

## How it works

```mermaid
flowchart LR
    A["Your request"] --> B["SKILL.md<br/>symptom table"]
    B --> C["reference/<br/>only the part needed"]
    C --> D["scripts/ · resources/ · templates/"]
    D --> E{"Gate<br/>exit code + evidence"}
    E -->|fails| C
    E -->|passes| F["Done, with proof"]
```

- **Lands on the right method from your words.** Each skill opens with a table of symptoms in
  plain language, and four start-here skills route any gameplay, UI, character or backend request.
- **Runs code, not advice.** 100+ Python scripts, 170+ C# files and 50+ templates you copy into
  your project instead of retyping notes.
- **Proves it.** Methods end in a check you can read: a probe snapshot, a journey test, a re-imported FBX,
  a device log.
- **Light on context, self-contained.** A `SKILL.md` only routes; depth loads when the situation
  needs it. No other plugin is required: skills hand off to each other through their Scope sections. A few rigging and motion scripts call
  scripts in a sibling skill; [`tools/cross-skill-deps.txt`](tools/cross-skill-deps.txt) lists them, so install those skills together.

## Skills

> [!TIP]
> Not sure where to start? Use `unity-gameplay` for any gameplay request, `unity-game-ui` for any
> UI request, `game-character-pipeline` for a rigged character made from an image, and
> `unity-live-services` for any backend, online or monetisation request.

<details>
<summary><b>Every stage — terminal & search</b> — the Unity CLI, and finding anything in a project</summary>

| Skill | Use it when |
|---|---|
| [`unity-cli`](skills/unity-cli/SKILL.md) | Unity from a terminal, with exit codes that say whether a retry is honest |
| [`unity-search`](skills/unity-search/SKILL.md) | "Where is it, what references it?" answered as one Unity Search query |

</details>

<details>
<summary><b>Concept</b> — the brief, day-one project setup, gameplay routing</summary>

| Skill | Use it when |
|---|---|
| [`unity-game-brief`](skills/unity-game-brief/SKILL.md) | An idea becomes a brief, a locked look, a gameplay preview, one playable interaction |
| [`unity-new-project`](skills/unity-new-project/SKILL.md) | Day-one decisions that are costly to retrofit, plus tests that run without the Editor |
| [`unity-gameplay`](skills/unity-gameplay/SKILL.md) | **Start here** for any gameplay request: it fingerprints the project and routes the work |

</details>

<details>
<summary><b>3C prototype</b> — input, camera, 2D and 3D controllers, animation, physics, play harness</summary>

| Skill | Use it when |
|---|---|
| [`unity-input`](skills/unity-input/SKILL.md) | A jump that goes missing or fires twice; gameplay reads one input struct |
| [`unity-camera`](skills/unity-camera/SKILL.md) | A camera that jitters, shows outside the level or clips through walls |
| [`unity-2d-controller`](skills/unity-2d-controller/SKILL.md) | A 2D character that slides down slopes or sticks to walls: one kinematic motor |
| [`unity-3d-controller`](skills/unity-3d-controller/SKILL.md) | `isGrounded` flickers or jump height changes with frame rate: one 3D motor |
| [`unity-animation`](skills/unity-animation/SKILL.md) | An Animator stuck in a state or an attack that plays by itself |
| [`unity-physics-2d`](skills/unity-physics-2d/SKILL.md) | A 2D collision or trigger that never fires, triaged in Box2D's own vocabulary |
| [`unity-physics-3d`](skills/unity-physics-3d/SKILL.md) | A collision or trigger that never fires, or a ball your game integrates itself |
| [`unity-play-harness`](skills/unity-play-harness/SKILL.md) | Make the game drivable: a one-line probe snapshot and journey tests that assert invariants |

</details>

<details>
<summary><b>Vertical slice — 2D world</b> — levels as data, grid boards, tile palettes, draw order and 2D lights</summary>

| Skill | Use it when |
|---|---|
| [`unity-2d-level`](skills/unity-2d-level/SKILL.md) | A 2D level as data, with seeded generation that checks every pickup is reachable |
| [`unity-2d-grid`](skills/unity-2d-grid/SKILL.md) | Board logic for tactics and tile puzzles on square, isometric or hex grids |
| [`unity-tilemap`](skills/unity-tilemap/SKILL.md) | Tiles that won't connect as you paint: RuleTiles from your sheet, palettes per grid |
| [`unity-2d-rendering`](skills/unity-2d-rendering/SKILL.md) | A sprite drawn behind the wrong one, or a `Light2D` that turns everything black |

</details>

<details>
<summary><b>Vertical slice — 3D world</b> — greybox to metrics, URP lighting, NavMesh agents</summary>

| Skill | Use it when |
|---|---|
| [`unity-3d-level`](skills/unity-3d-level/SKILL.md) | A 3D greybox built from a metrics sheet and proven by a walk journey |
| [`unity-lighting`](skills/unity-lighting/SKILL.md) | A bake that did nothing, or a character black beside baked walls, on URP |
| [`unity-navigation`](skills/unity-navigation/SKILL.md) | An agent that won't move or walks through walls: NavMesh, links, transform ownership |

</details>

<details>
<summary><b>Vertical slice — systems</b> — doors and pickups, damage, enemy AI, scenes and saves</summary>

| Skill | Use it when |
|---|---|
| [`unity-interaction`](skills/unity-interaction/SKILL.md) | "Press E to open" that flickers or opens twice: one target, one prompt |
| [`unity-combat`](skills/unity-combat/SKILL.md) | A swing that hits twice or a shot through the sentry: one hit each |
| [`unity-game-ai`](skills/unity-game-ai/SKILL.md) | An enemy that sees through walls or never gives up: perception on a budget |
| [`unity-scene-flow`](skills/unity-scene-flow/SKILL.md) | Duplicated managers or a corrupted save: a Boot scene and versioned atomic saves |

</details>

<details>
<summary><b>Vertical slice — UI</b> — UI routing and HUDs, uGUI, UI Toolkit</summary>

| Skill | Use it when |
|---|---|
| [`unity-game-ui`](skills/unity-game-ui/SKILL.md) | **Start here** for any UI request: it detects the UI system and routes |
| [`unity-ui-ugui`](skills/unity-ui-ugui/SKILL.md) | A Canvas UI that renders nothing: six checks, then anchors and Layout Groups |
| [`unity-ui-toolkit`](skills/unity-ui-toolkit/SKILL.md) | A USS property that silently does nothing, plus UXML, flex layout and binding |

</details>

<details>
<summary><b>Production — assets</b> — asset ledger, 3D models, rigged characters, sprites, audio, languages</summary>

| Skill | Use it when |
|---|---|
| [`art-asset-registry`](skills/art-asset-registry/SKILL.md) | Which generated asset came from where, and what went stale: one append-only ledger |
| [`unity-3d-models`](skills/unity-3d-models/SKILL.md) | A 3D model into the game, at a budget picked under the game camera |
| [`unity-rigged-character`](skills/unity-rigged-character/SKILL.md) | A rigged FBX that T-poses in Unity: import, Avatar, Animator and gameplay rig |
| [`unity-2d-sprites`](skills/unity-2d-sprites/SKILL.md) | Sprite sheets sliced from script, and frames turned into a playable clip |
| [`unity-2d-animation`](skills/unity-2d-animation/SKILL.md) | Skeletal 2D characters from a PSB, with skins and equipment swapped at runtime |
| [`unity-2d-pixel-perfect`](skills/unity-2d-pixel-perfect/SKILL.md) | Pixel art that renders soft, shimmers as the camera moves or shows seams |
| [`unity-sprite-atlas`](skills/unity-sprite-atlas/SKILL.md) | Sprites that should share a draw call, packed into V2 atlases from script |
| [`unity-audio`](skills/unity-audio/SKILL.md) | Audio memory and CPU cut without the game sounding worse; it reports before reimporting |
| [`unity-localization`](skills/unity-localization/SKILL.md) | Shipping in more than one language, including the CJK font pipeline where it breaks |

</details>

<details>
<summary><b>Production — AI asset generation</b> — the character stage order, 2D art, audio, video and 3D, rigging and motion</summary>

| Skill | Use it when |
|---|---|
| [`game-character-pipeline`](skills/game-character-pipeline/SKILL.md) | **Start here** for a rigged character from an image: stages S0–S13, each gated |
| [`codex-visual`](skills/codex-visual/SKILL.md) | 2D art through the `codex` image model, kept on-style by one art bible |
| [`comfyui-asset-generation`](skills/comfyui-asset-generation/SKILL.md) | Music, SFX, video and 3D models from your own ComfyUI, one job each |
| [`mesh-texture-paint`](skills/mesh-texture-paint/SKILL.md) | A generated 3D model's dull texture repainted from the concept art, view by view, mesh and UVs kept |
| [`sprite-from-video`](skills/sprite-from-video/SKILL.md) | One character still turned into transparent sprite loops through a generated video |
| [`blender-character-rig`](skills/blender-character-rig/SKILL.md) | A rig built by hand in Blender when `character-autorig` does not fit, its FBX proven by re-import |
| [`blender-retarget`](skills/blender-retarget/SKILL.md) | Stock clips onto your Blender rig, gated on slide, jitter and pops |
| [`character-autorig`](skills/character-autorig/SKILL.md) | A humanoid rigged locally with your own Auto-Rig Pro, in one headless command |
| [`humanoid-motion`](skills/humanoid-motion/SKILL.md) | A move as a clip, solved from a two-camera video straight onto the skeleton |

</details>

<details>
<summary><b>Polish & optimisation</b> — game feel, URP, migration, profiling, scene cost, verification</summary>

| Skill | Use it when |
|---|---|
| [`unity-game-feel`](skills/unity-game-feel/SKILL.md) | A hit with no impact: one feedback row per gameplay event, with a budget |
| [`unity-render-urp`](skills/unity-render-urp/SKILL.md) | Post-processing that will not appear, and Render Graph features reviewed before shipping |
| [`unity-urp-migration`](skills/unity-urp-migration/SKILL.md) | Built-in to URP in five gated phases, or a half-moved project diagnosed |
| [`unity-profiling`](skills/unity-profiling/SKILL.md) | What a slow or uneven frame is doing, as 90-frame windows you compare |
| [`unity-scene-optimisation`](skills/unity-scene-optimisation/SKILL.md) | The fix once a counter names the cost, read back on the same counter |
| [`unity-debug`](skills/unity-debug/SKILL.md) | Verifying a change you cannot see — after proving the harness tells the truth |

</details>

<details>
<summary><b>Shipping</b> — real-phone tests, Android, iOS, web</summary>

| Skill | Use it when |
|---|---|
| [`unity-device-testing`](skills/unity-device-testing/SKILL.md) | Acceptance on a real phone: an agent drives, a person does the physical step |
| [`unity-android-release`](skills/unity-android-release/SKILL.md) | A signed APK or AAB, proven by reading the artifact back |
| [`unity-ios-build`](skills/unity-ios-build/SKILL.md) | A Unity project to a running iPhone app, without opening Xcode |
| [`unity-web-release`](skills/unity-web-release/SKILL.md) | A WebGL or WebGPU build small and fast enough that people wait for it |

</details>

<details>
<summary><b>Backend & commerce</b> — backend discipline, Gaming Services, purchases, ads, multiplayer, voice</summary>

| Skill | Use it when |
|---|---|
| [`unity-live-services`](skills/unity-live-services/SKILL.md) | Start here for backend, online and monetisation: the offline path, multiplayer topology, the SDK-to-store seam |
| [`unity-ugs`](skills/unity-ugs/SKILL.md) | A service that throws because nothing initialised: Gaming Services in the right order |
| [`unity-iap`](skills/unity-iap/SKILL.md) | Content granted twice or not at all: In-App Purchasing v5, call by call |
| [`unity-ads-levelplay`](skills/unity-ads-levelplay/SKILL.md) | No ads, or a build broken by ad dependencies: LevelPlay, consent before init |
| [`unity-multiplayer-services`](skills/unity-multiplayer-services/SKILL.md) | How players get into a game together, from join codes to host migration |
| [`unity-vivox`](skills/unity-vivox/SKILL.md) | A voice join that succeeds while nobody hears: Vivox chat, sign-in to push-to-talk |

</details>

## Contributing

Tooling, checks and repo rules: [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md). What each release contains: [CHANGELOG.md](CHANGELOG.md).

## Licence

MIT — see [LICENSE](LICENSE). Code ported from other projects keeps its own licence: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
