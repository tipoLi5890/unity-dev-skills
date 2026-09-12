# unity-dev-skills

**English** · [繁體中文](.github/README.zh-TW.md) · [简体中文](.github/README.zh-CN.md) · [日本語](.github/README.ja.md)

Unity 6 game-development skills for AI coding agents. Twenty-nine skills covering the loop from an
empty project to a verified artifact — installable into Claude Code or OpenAI Codex.

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

| Group | Skill | Load it when |
|---|---|---|
| **Terminal & verification** | `unity-cli` | Driving Unity from a terminal: editors, licences, templates, CI, MCP, and exit codes that say whether a retry is honest |
| | `unity-debug` | You need to verify a change you cannot see — and to prove the harness is telling the truth before believing it |
| **Day one** | `unity-new-project` | Decisions that are expensive to retrofit: editor pinning, `.meta`/LFS, UPM tag pinning, IL2CPP/ARM64, asmdef boundaries |
| **UI** | `unity-game-ui` | **Start here for any UI request.** Detects the project's UI system and routes; owns the runtime `OnGUI` HUD nobody else documents |
| | `unity-ui-ugui` | Canvas, RectTransform, Layout Groups — and the six ways uGUI renders nothing |
| | `unity-ui-toolkit` | UXML/USS, flex, Painter2D — and the properties USS silently ignores |
| **Assets** | `unity-3d-models` | Static props: importing and decimating AI-generated meshes before Unity ever sees them |
| | `unity-2d-sprites` | Sprite sheets, slicing, pivots, 9-slice, and a set of frames turned into a playable `AnimationClip` — metadata that lives inside the importer |
| | `unity-2d-pixel-perfect` | Pixel art that renders soft, shimmers as the camera moves, or shows hairline seams — and which of the two components called `PixelPerfectCamera` you actually have |
| | `unity-sprite-atlas` | Sprites that should share a draw call: V2 atlases from script, packing and platform settings, and how the packed texture reaches the player |
| | `unity-tilemap` | Tile Palettes for rectangular, hexagonal and isometric grids, and RuleTiles built from a terrain sheet you already have |
| | `unity-rigged-character` | A playable character: art → image-to-3D → Mixamo → Avatar → Animator → gameplay rig |
| **AI asset generation** | `codex-visual` | 2D art through the `codex` image model, held on-style by one art bible and one anchor: grid one-shot sets, short animations generated as one gridded sheet and sliced into measured frames with a GIF preview, chroma-key transparency, normalised sizes |
| | `comfyui-asset-generation` | Music, SFX and MiniMax H3 video through a self-hosted ComfyUI — one job at a time, `/history` as the only proof, `/free` before a model switch |
| **Runtime domains** | `unity-physics-3d` | A collision or trigger that never fires, tunnelling, a raycast that misses |
| | `unity-navigation` | NavMesh, agents, obstacles, links — and deciding who owns the transform |
| | `unity-render-urp` | Post-processing that will not appear, the mobile subset, Render Graph review |
| | `unity-audio` | Memory, load types, sample rates, mixer cost — reports before it reimports |
| | `unity-localization` | Shipping in more than one language, and the CJK font pipeline where it goes wrong |
| **Shipping** | `unity-android-release` | Build it, then *prove* it: read the artifact back, keystore and versionCode discipline |
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
