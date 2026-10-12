# Reading a project's perspective off its files

> Part of the `unity-gameplay` skill. What `scripts/fingerprint.py` looks at, the same checks as
> shell one-liners for when Python is not to hand, and how to read the combination — because no
> single line of the result is the answer.

A Unity project states its perspective in four places, in descending order of trust:

1. **Components in scenes and prefabs** — what the game is built from.
2. **Scripts** — what the code is written against.
3. **Project settings** — gravity, the active input handler.
4. **Packages** — what is installed, which says the least: templates install things.

The script reads all four and never starts Unity. It needs text-serialised assets (Asset
Serialization set to Force Text, the default); a binary scene is counted in
`scanned.binary_skipped` and named in `notes`.

```bash
python3 scripts/fingerprint.py . --indent 2
python3 scripts/fingerprint.py . --exclude Plugins --exclude Vendor      # replaces the default excludes
```

Exit 0 with one JSON object, or 2 when the path holds no `Assets/` and `ProjectSettings/`.
`Plugins`, `TextMesh Pro`, `ThirdParty`, `Samples` and `StreamingAssets` are skipped by default,
because a vendored demo scene outvotes a small game.

## The same checks by hand

Run from the project root. Quote every `--include` pattern: unquoted, zsh expands it against the
working directory and grep never sees the flag.

```bash
# Dimension — which physics the scenes and prefabs are made of.
# Component headers sit at column zero, so anchor the pattern or "Rigidbody:" also counts Rigidbody2D.
grep -rhc '^Rigidbody2D:' Assets --include='*.unity' --include='*.prefab' | paste -sd+ - | bc
grep -rhc '^Rigidbody:'   Assets --include='*.unity' --include='*.prefab' | paste -sd+ - | bc
grep -rhE '^(CharacterController|NavMeshAgent|[A-Za-z]+Collider2D|(Box|Sphere|Capsule|Mesh)Collider):' \
     Assets --include='*.unity' --include='*.prefab' | sort | uniq -c

# Projection — one line per Camera component.
grep -rh  '^  orthographic: ' Assets --include='*.unity' --include='*.prefab' | sort | uniq -c
grep -rhE '^  (orthographic size|field of view): ' Assets --include='*.unity' | sort | uniq -c

# View, 2D — does anything fall?
grep 'm_Gravity' ProjectSettings/Physics2DSettings.asset
grep -rh '^  m_GravityScale: ' Assets --include='*.unity' --include='*.prefab' | sort | uniq -c
grep -rl '^PlatformEffector2D:' Assets --include='*.unity' --include='*.prefab' | head

# Movement model — cells, and what kind.
grep -rh '^  m_CellLayout: ' Assets --include='*.unity' --include='*.prefab' | sort | uniq -c
grep -rh '^  m_CellSize: '   Assets --include='*.unity' --include='*.prefab' | sort | uniq -c
grep -rlE 'WorldToCell|CellToWorld|GetCellCenterWorld' Assets --include='*.cs' | head

# Packages that change API names — resolved versions, not declared ones.
python3 -c "import json;d=json.load(open('Packages/packages-lock.json'))['dependencies'];[print(k,d[k]['version']) for k in ('com.unity.cinemachine','com.unity.inputsystem','com.unity.ai.navigation') if k in d]"

# Input — installed, switched on, and used are three different facts.
grep 'activeInputHandler' ProjectSettings/ProjectSettings.asset     # 0 Input Manager · 1 Input System · 2 both
find Assets -name '*.inputactions' | head
grep -rlE 'Input\.(GetAxis|GetKey|GetButton|GetMouseButton)' Assets --include='*.cs' | head
```

`m_CellLayout` reads `0` rectangle, `1` hexagon, `2` isometric, `3` isometric with Z as Y.
`m_BodyType` on a `Rigidbody2D` reads `0` dynamic, `1` kinematic, `2` static.

## What each verdict is derived from

| Key | Derived from | Values |
|---|---|---|
| `dimension` | The first of these that has evidence on one side only: physics components, script references, renderers, camera projection | `2d` · `3d` · `mixed` (with `leans`) · `unknown` |
| `projection` | `orthographic: 0/1` on every `Camera` | `orthographic` · `perspective` · `mixed` · `unknown` |
| `view` | 2D: project gravity, per-body gravity scale, `PlatformEffector2D`, grid layout. 3D: the steepest camera pitch | `side` · `top-down` · `isometric` · `behind-or-eye-level` · `ambiguous` · `unknown` |
| `movement_model.hints` | Body types, `CharacterController`, `NavMeshAgent`, cell API calls beside a `Grid`, root-motion code | A list — a project usually has more than one |
| `grid` | `Grid` components: layout and cell size, and the `Tilemap` count | Counts per layout |
| `sprites.pixels_per_unit` | `spritePixelsToUnits` on sprite-typed texture `.meta` files | Counts per value |
| `input` | The active handler, `.inputactions` files, legacy calls and Input System references in scripts | — |
| `packages` | `Packages/packages-lock.json`, or `manifest.json` when there is no lock | Versions; `cinemachine.major` |
| `cameras` | Each camera with projection, size or FOV, and pitch and yaw from its own local rotation | First 20 |

Camera pitch comes from the camera's **local** rotation. `parented: true` on a camera means a
rig above it may add rotation the file scan does not compose — read that camera's pitch as a
lower bound on certainty, not a measurement.

Cinemachine components are `MonoBehaviour` documents identified by a script GUID, so they do not
appear in the component counts. Their presence is read from scripts (`script_refs.cinemachine_2x`,
`cinemachine_3x`) and the major from the lock file.

## Reading the combination

| The result says | It is | Open |
|---|---|---|
| `2d`, orthographic, gravity non-zero, bodies fall, effectors present | A side view with free movement | `reference/genre-2d-side.md` |
| `2d`, orthographic, 2D gravity `0` or every body at gravity scale `0` | Seen from above, free movement | `reference/genre-2d-topdown.md` |
| `2d`, cell API calls beside a `Grid`, few or no dynamic bodies | Cell movement; the layout says rectangular, hexagonal or isometric | `reference/genre-2d-grid.md` |
| `2d`, one orthographic camera, no camera code, kinematic bodies or none | A fixed screen | `reference/genre-2d-fixed-screen.md` |
| `3d`, perspective, `character-controller` or a dynamic body, pitch under 50° | Behind the character or through its eyes — the files cannot tell which; look for a camera parented under the player | `reference/genre-3d.md` |
| `3d`, pitch 50° or more, or `navmesh-agent` with pointer code | Overhead or fixed camera | `reference/genre-3d.md` |
| `3d` physics, orthographic camera | 2.5D: 3D controller rows, 2D camera rows | both genre files, by row |
| `mixed` | Two games in one project, or 2D physics for UI effects on a 3D game — follow `leans`, then confirm with the player prefab | — |
| Everything `unknown` | No evidence: a new project, the wrong directory, binary scenes | the default ladder in SKILL.md §0 |

Three combinations that read as contradictions and are not:

- **Tilemaps in a 3D project.** A `Grid` with a `Tilemap` and 3D colliders is a tile-authored 3D
  level or a minimap. Route by the player's body.
- **Gravity scale `0` in a side view.** Kinematic-style platformer motors zero the gravity scale
  and integrate gravity themselves. `PlatformEffector2D` counts and a `side` camera with a ground
  layer settle it; so does one look at the player script for a `gravity` field.
- **Both `dynamic-body-2d` and `kinematic-body-2d` hints.** Normal: the player is one, moving
  platforms and projectiles are the other. Find which the *player* prefab carries.

## Four notes the script raises, and what to do about each

| Note | Meaning | Do |
|---|---|---|
| Input System installed, active handler is the old Input Manager | The package compiles and its devices report nothing | Switch Active Input Handling before debugging "no input" — `unity-input` |
| Scripts call `UnityEngine.Input`, handler is Input System only | Each call throws `InvalidOperationException` at runtime | Migrate the calls or set the handler to both — `unity-input` |
| Scripts use Cinemachine 2.x names, 3.x resolved (or the reverse) | The project is mid-upgrade or was pasted from a sample of the other major | Read the name map before touching a camera — `unity-camera` |
| No `packages-lock.json` | Versions shown are the declared ones | Open the project once so the lock resolves, then re-run |

## When the fingerprint and the user disagree

The user wins on intent; the fingerprint wins on what exists. "Make it first-person" on a
project fingerprinted as third-person is a request to change a constraint: write the new value
into `templates/GAMEPLAY_RECIPE.md`, list the rows that change with it (camera rig, controller
facing, which animations are ever seen), and change those — nothing else.
