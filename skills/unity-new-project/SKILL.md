---
name: unity-new-project
description: >-
  Start a new Unity 6 project: pin the editor, git and LFS, pinned UPM packages, asmdef layout.
---

# unity-new-project — day-one decisions for a Unity 6 project

> **Everything here is cheap now and expensive later.** None of it is urgent on day one, which
> is exactly why it gets skipped — and every item is something that, once a team and a history
> exist, costs a migration rather than a setting.

## Request → where to look

| Request or symptom | Go to |
|---|---|
| Starting a Unity project; which editor version; render pipeline at creation | §1 |
| A freshly created template project does not compile | §1, then [`reference/package-bootstrap.md`](reference/package-bootstrap.md) |
| Onboarding a repo to version control: `.meta`, ignores, LFS from day one | §2, [`reference/version-control-setup.md`](reference/version-control-setup.md) |
| Publishing an existing project to a git remote | [`reference/version-control-setup.md`](reference/version-control-setup.md) §4 |
| Adding a UPM git dependency; pinning it to an annotated tag | §3 |
| Mobile is even "maybe": IL2CPP / Android baseline | §4 |
| Installing packages; which packages a starting project needs | §4b, [`reference/package-selection.md`](reference/package-selection.md) |
| Reviewing early project structure: asmdef module boundaries, the single input funnel, Boot scene | [`reference/project-structure.md`](reference/project-structure.md) |
| Tests for pure assemblies without opening the Editor | [`reference/pure-test-lane.md`](reference/pure-test-lane.md) |
| A scaffolder that wipes Inspector values; generated ScriptableObjects | [`reference/generated-assets.md`](reference/generated-assets.md) |

## 1. Pin the editor, first commit

- Record the exact editor version (e.g. `6000.0.47f1`) and install via Unity
  Hub; `ProjectSettings/ProjectVersion.txt` is the SoT and is committed.
  A teammate (or CI) on a different patch version silently reserializes
  assets — diffs become noise and prefabs drift.
- Decide the render pipeline (URP for mobile/2.5D) at creation — swapping
  pipelines later touches every material.
- **Once the target platforms are known, put the editor install in the background and keep asking**
  — `unity install <version> --module <modules> --yes --accept-eula` runs for minutes, none of the
  remaining decisions depend on it, and `unity editors --installed` is the confirmation that it
  landed before you create the project. An install that died halfway looks exactly like one still
  running. **Both flags are what makes it backgroundable**: without them the install stops on a
  prompt nobody is watching, and a job blocked on stdin is indistinguishable from a slow download.
- **A template is not a working configuration.** Creating from `universal-2d` on Unity 6000.4
  gives project-wide compile errors from the template's own stale package locks. When a *fresh*
  project will not compile, suspect `Packages/manifest.json` before the code —
  `reference/package-bootstrap.md`.

## 2. Version control (Unity's own layout fights git)

- **`.meta` files ARE committed** (they carry GUIDs — a missing .meta = broken
  references for everyone else); enable `Visible Meta Files` +
  `Asset Serialization: Force Text`; caches (`Library/` etc.) stay ignored.
- Large binaries → **git LFS from day one** — retrofitting LFS rewrites history. Write
  `.gitattributes` in the *first* commit, then **prove the first binary commit used it**:
  `git lfs ls-files | wc -l` and `git show HEAD:<path> | head -c 60` (an LFS blob starts
  `version https://git-lfs.github.com/spec/v1`). `git lfs ls-files --cached` does not exist — it
  exits with `Error: unknown flag: --cached`, which is easy to miss inside a chained command. Full
  file, the text-YAML exception that grows (a dynamic CJK TMP font asset can grow from ~202 KB to
  1.3–1.6 MB over a day of Editor sessions), and publishing an already-large repo to a remote:
  `reference/version-control-setup.md`.
- **Keep an LFS ledger**: each binary commit states what it adds against the plan's quota, a
  push of several hundred MB or of purchased assets waits for the person, and when agents share
  a checkout, check `git log origin/main..HEAD` before pushing → `reference/version-control-setup.md` §5–§7.
- Three hosting shapes, and the choice is the user's, not a default: **GitHub/GitLab + LFS**;
  **UVCS**, which handles large binaries natively and needs no LFS at all; or plain local `git`.
- Push the first commit **after** packages are installed and the Editor has generated `.meta`
  files — an initial commit of an empty project is a commit you will have to amend. If you are
  scripting creation, that is what `--no-initial-commit` is for. **If creation already committed**
  — a `--vcs` run without that flag publishes the bare project as commit one — add a follow-up
  commit for the packages and `.meta` files rather than amending or re-committing the same tree
  twice; the history is already public by then, and two initial commits are worse than one empty
  one.
- **Credentials go in on stdin, never in `argv`** (`--git-token-stdin`). A token expanded from an
  environment variable is still visible in the process list and in shell history; CI must mask it
  in logs too.

## 3. UPM git dependencies — the pinning iron law

Add private packages by git URL **pinned to an annotated tag**, never a
branch:

```
"com.<vendor>.<pkg>": "https://github.com/<org>/<repo>.git?path=unity-package#vX.Y.Z"
```

Tracking `master` means builds change under you; a pinned tag makes every
upgrade a deliberate ref bump. Keep NDK/AGP versions aligned with what the
native packages were built against — don't bump blindly, and expect a native
SDK to pin those deliberately rather than take automated dependency bumps.
Note the `?path=` form when the package lives in a subfolder — the usual
shape for a native SDK, whose Unity package sits one folder inside the repo
that also carries the native sources.

Three consequences of it being a *git* URL:

- **Credentials, not Unity, decide whether it resolves.** A machine can reach a private dependency
  non-interactively over https (an osxkeychain helper, say) and **not over SSH**. Run
  `git ls-remote <that exact URL>` before the installer on any new machine or CI box; without it
  the project simply fails to compile, and the symptom you actually see is "no test results file",
  not a package error.
- **`manifest.json` is the request; `packages-lock.json` is what you compiled.** The lockfile
  carries the resolved commit `hash` — check it against the tag, and check
  `Library/PackageCache` for the directory that was really unpacked.
- **A tag bump touches three places together**: the version constant in your installer script,
  `manifest.json`, and `packages-lock.json`.

## 4. Android/IL2CPP baseline (if mobile is even "maybe")

Set in Player Settings on day one: **IL2CPP + ARM64**, minSdk to what your
plugins demand now, and a real package name (`com.<org>.<app>` — renaming
later touches keystore/store identity, same trap as Flutter's `--org`).
Build/release mechanics: `unity-android-release`.

> **The minSdk you ask for is not necessarily the minSdk you ship.** Unity
> 6000.4 clamps minSdk up to its own floor of 25: ask for 23 and you get `AndroidApiLevel25`
> back, so the build ships **minSdk 25** whatever the plugin's documented floor says. Treat a
> plugin's number as a lower bound, not the answer: set it in the setup method below, read
> `PlayerSettings.Android.minSdkVersion` back, and ship *that* value — it is the one for the
> release notes. Check the floor on your own editor version rather than assuming 25.

Put these in a re-runnable `[MenuItem]` + `-executeMethod` method rather than clicking them,
and set `EditorSettings.serializationMode = ForceText` and
`VersionControlSettings.mode = "Visible Meta Files"` in the same method — §2 depends on both,
and both vanish when someone recreates the project from a template.
→ `reference/generated-assets.md`

## 4b. Packages: install them through the API, never by hand

Install only what the concept actually needs, prefer what the template already ships (a URP
template already has the render pipeline and Input System), and **do not pin a version** unless
there is a stated minimum. Concept → need → id, and the subtraction step that shrinks the list:
[`reference/package-selection.md`](reference/package-selection.md). Two rules that decide whether
it works at all:

- **Never edit `Packages/manifest.json` by hand**, and never guess an id. List it with
  `Client.SearchAll()` — one call is cheaper than one wrong guess. The single exception is the
  template whose own locks do not compile (§1): there you replace the manifest wholesale with a
  set known good on *this* editor version, reopen the Editor, and let UPM rewrite the lockfile.
- A headless install that returns exit 0 and installs nothing is the normal failure mode, not an
  unusual one. → `reference/package-bootstrap.md`

If you are driving this as a guided flow, **start the editor install in the background while you
are still asking the concept questions**, then join on `unity editors --installed --format json`
before doing anything downstream. Parallelism only pays when there is conversation to overlap it
with — with nothing left to ask, just wait.

> **Ask one step at a time, and the concept interview is not this skill's.** What the game is
> belongs to `unity-game-brief`; what arrives here is a settled proposal. Even for the questions
> this skill does own — target platforms, hosting shape, editor version — put one on the table,
> wait for the answer, then move: platform and monetisation answers change which modules install
> and which packages go in the list, so a batch of questions collected up front produces a setup
> that has to be redone. Nothing is scaffolded before those answers exist.

## 5. Structure that survives growth → `reference/project-structure.md`

asmdef per module, a `noEngineReferences` assembly and its pure test lane, injected clock and
seed, one input funnel, a Boot scene, the art pipeline, generated assets as build output.

## Scope — what this skill does NOT do

This skill owns the **decisions**; the `unity` commands that execute them are `unity-cli`.

**No gameplay scaffolding.** A generic genre skeleton produces throwaway mock primitives that
have to be deleted before real work starts, so this skill stops at a clean, correctly-configured
project. Building the actual game is every other skill in this plugin.

What the game *is* — the brief, the constraints, the architecture proposal, the first interaction —
is `unity-game-brief`; this skill starts when that proposal names the assemblies.

Also not here: which packages a given genre needs beyond the starting point in §4b and
`reference/package-selection.md` — that table is something to subtract from once the concept is
known, never a list to install whole. Nor anything about shipping — `unity-android-release`,
`unity-web-release`.

Nor the font pipeline: this skill owns only the version-control consequence that TMP font assets
live in the text (non-LFS) half of the repo and grow there. Atlases, fallback chains and
locales are `unity-localization`.

## Related skills

The terminal: `unity-cli`. Verifying a change: `unity-debug`.

Gameplay: `unity-gameplay` (routes by perspective).
3C: `unity-input` · `unity-camera` · `unity-animation`.
2D runtime: `unity-2d-controller` · `unity-physics-2d` · `unity-2d-rendering` ·
`unity-2d-level` · `unity-2d-grid` · `unity-2d-animation`.
UI: `unity-game-ui` (routes) → `unity-ui-ugui` · `unity-ui-toolkit`.
Assets: `unity-3d-models` · `unity-2d-sprites` · `unity-rigged-character`.
Runtime domains: `unity-physics-3d` · `unity-navigation` · `unity-render-urp` ·
`unity-audio` · `unity-localization`.
Shipping: `unity-android-release` · `unity-web-release`.
Backend & commerce: `unity-live-services` (routes) → `unity-ugs` ·
`unity-multiplayer-services` · `unity-vivox` · `unity-iap` · `unity-ads-levelplay`.

Consistent AI art: `codex-visual`.
