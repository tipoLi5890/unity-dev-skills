# Secondary motion — hood, bag, hem and hair that swing

The courier runner's hood should bounce on the jump, the back bag swing on a lane snap, the
jacket hem and shorts flick, the hair spikes lag the head. This file covers the free route: a
spring-bone runtime that ships here (`resources/`, namespace `UnityDev.SecondaryMotion`, plain
C#, no package) driving extra `cc_` bones the rig side adds.

## The route, and what it is not

- **An image-to-3D mesh is one fused shell.** The jacket, the bag and the hair are not separate
  meshes, so there is nothing for a cloth simulation to drape. Chains of extra bones weight
  *regions* of the shell instead: each region follows its chain, the rest of the skin is untouched.
- **The chains are added at rig time as plain `cc_` bones** on the bound Auto-Rig Pro rig
  (`character-autorig`), not as Auto-Rig Pro limbs. Auto-Rig Pro's exporter keeps any bone named
  `cc_*` as a deform bone, with its name and parent; a limb (`tail`, `kilt`, `ears`) would need
  Match to Rig and a rebind, which throws away the body's weight repair. If someone wants FK
  controls to key the chain in Blender, `tail` is the limb that adds without a rebind of its own.
- **Each chain ends in an unweighted tip bone** (`cc_<chain>_end.<side>`): an FBX carries no bone
  tails, and the last segment needs a point to aim at.
- **Weights stay at four per vertex.** The rig side takes the chain's share from the existing
  weights and limits to four itself; the exporter would otherwise trim silently.
- **Not here:** a cross-body strap fixed at both ends (it rides the chest weights; a free-tip
  spring is the wrong tool), true cloth on separate garment meshes, paid spring or cloth assets.
- **No-collision alternative:** Unity's Animation Rigging package (Damped Transform) gives a lag
  without colliders; use it only where nothing can pass through the body.

## The chains on the runner — defaults per kind

| Chain | kind | Bones | Hangs from | stiffness / drag / gravity / max° / radius m | Colliders |
|---|---|---|---|---|---|
| Hood | `hood` | 2 + tip | UpperChest or Neck, whichever carries the region | 0.35 / 0.35 / 0.6 / 40 / 0.04 | UpperChest, Chest |
| Back bag | `bag` | 1 + tip | Spine | 0.25 / 0.45 / 1.0 / 30 / 0.06 | Hips, Spine, UpperLeg.L/R |
| Jacket hem | `hem` | ring of 4–6 chains × 1 + tip | Hips | 0.55 / 0.40 / 0.3 / 25 / 0.02 | UpperLeg.L/R, Hips |
| Shorts hems | `shorts_hem` | 3 per leg × 1 + tip | UpperLeg | 0.65 / 0.40 / 0.2 / 20 / 0.015 | both UpperLegs, its own shrunk clear of the hem |
| Hair spikes | `hair` | up to 6 chains × 1–2 + tip | Head | 0.75 / 0.30 / 0.1 / 20 / 0.01 | Head |

Names: `cc_<chain>_<NN>.<side>` (`.x` centre, `.l`/`.r` sided), e.g. `cc_hood_01.x`,
`cc_hemFL_01.x`, `cc_shortsLB_01.l`. Body colliders are capsules between two bone origins (Hips
across the thighs, Spine, Chest, UpperChest, Upper/LowerLeg) and a Head sphere, fitted by the rig
side so no chain joint starts inside one of its group: a collider that would is shrunk or left out
of that chain's list (a hood resting on the back may keep one or none). Do not cut a chain's `radius` to make
room: a thinner particle sinks further before it collides.

## `secondary/1` — the hand-off file

Written beside the body FBX as `<name>.secondary.json` by the rig side (`secondary_chains.py`);
read by `SecondaryMotionSetup`. Bone names are the exported names. Every position Unity uses hangs
off bones; `parent_head`, `joints` and a sphere's `center` are rest positions in the skeleton/1
frame (metres, +Z up, facing −Y), used only to self-check axes and scale.

```json
{
  "schema": "secondary/1", "tool": "secondary_chains.py",
  "producer": {"skill": "character-autorig", "script": "secondary_chains.py"},
  "character": "Runner", "units": "m", "up": "+Z", "forward": "-Y",
  "chains": [
    {"name": "hood", "kind": "hood", "parent": "neck.x", "parent_role": "Neck",
     "bones": ["cc_hood_01.x", "cc_hood_02.x", "cc_hood_end.x"],
     "joints": [[0, 0.10, 1.47], [0, 0.15, 1.40], [0, 0.17, 1.32]],
     "parent_head": [-0.0018, 0.0457, 1.4263],
     "radius": 0.04, "stiffness": 0.35, "drag": 0.35, "gravity": 0.6, "wind": 0.2,
     "inertia": 1.0, "max_angle_deg": 40, "colliders": ["Chest", "UpperChest"]}
  ],
  "colliders": [
    {"name": "Chest", "shape": "capsule", "a": "spine_02.x", "b": "spine_03.x",
     "a_role": "Chest", "b_role": "UpperChest", "radius": 0.13},
    {"name": "UpperChest", "shape": "capsule", "a": "spine_03.x", "b": "neck.x", "radius": 0.12},
    {"name": "Head", "shape": "sphere", "a": "head.x", "a_role": "Head",
     "center": [0, -0.01, 1.62], "radius": 0.11}
  ]
}
```

| Field | Meaning |
|---|---|
| `stiffness`, `drag` | fractions per 1/60 s: pull back to the animated pose, velocity lost. Converted per substep, so the result does not depend on frame rate |
| `gravity`, `wind` | multiples of the system's gravity and wind |
| `inertia` | 1 (default): the chain lags the whole-body motion fully; lower: carried along with the model's travel (calms a lane snap) |
| `max_angle_deg` | largest angle between a segment and its animated direction |
| `radius` | particle radius against colliders, metres |
| `colliders` | the names this chain tests; left out: all of them |
| `parent_role`, `a_role`, `b_role` | `HumanBodyBones` names, used when a name lookup fails on a Humanoid |
| `inset` | capsule: fraction trimmed off each end |

Required on every chain: `name`, `kind`, `parent`, `bones` (at least one `cc_` bone and the
`_end` tip), `stiffness`, `drag`, `gravity`, `radius`, `max_angle_deg`; a missing one refuses.
`wind` defaults to 0, `inertia` to 1; `colliders`, `joints` and `parent_head` are optional, but
without `parent_head` the axis self-check does not run. `"chains": []` is valid (nothing loose on
the body): setup removes what an earlier run built, adds nothing and reports `ok` with 0 chains.

## Setup in Unity

1. **Optimize Game Objects off** on the body FBX (`reference/unity-import.md` §3). With it on, the
   bones are not the transforms that skin the mesh: writing them moves nothing. Setup refuses;
   the runtime checks `Animator.hasTransformHierarchy` and switches itself off with one message.
2. Copy the five runtime files into a runtime folder and `Editor/SecondaryMotionSetup.cs` into an
   Editor folder.
3. Select the character prefab, then **Tools/Unity Dev/Rigged Character/Add Secondary Motion**, or:

   ```
   Unity -batchmode -quit -projectPath . \
     -executeMethod UnityDev.SecondaryMotion.SecondaryMotionSetup.SetupFromCommandLine \
     -character Assets/Characters/Runner/Runner.prefab
   ```

   `-spec <file>` when the file is not `<name>.secondary.json` beside the FBX; `-out <prefab>`
   when `-character` is the FBX itself (default `<name>_Secondary.prefab`, written even when the
   file has no chains). Exit 0 built, 2 refused, 1 usage error, 3 harness error. The menu takes a
   prefab or a scene instance, not the model asset.

What it does, re-runnable: refuses (changing nothing) on a wrong stamp, a missing `cc_` bone (the
FBX predates the chains), a chain bone not under the one before it, or a `parent_head` more than
1 cm from that bone's bind pose (axis or scale mismatch at export). Then it removes every spring
component and `SM_Collider_*` object under the model, adds a `SpringCollider` on an
`SM_Collider_<name>` child of bone `a`, a `SpringChain` on each chain's first bone (stores the rest
rotations), and one `SecondaryMotionSystem` on the GameObject with the Animator — the model, not
the gameplay root; lengths and radii scale with it. **Rest penetration:** a chain joint (other
than the pinned first one) inside a collider of its group would pop on frame one, so that collider
is shrunk — to no less than half its radius — or dropped from that chain's group. The rest
rotations are read from the pose it finds: run it on the prefab or an instance at bind pose,
never on one an Animation window preview has posed. It logs:

`[RIGGED-CHAR] {"step":"secondary","ok":true,"chains":N,"bones":M,"particles":P,"colliders":K,"self_checked":S,"shrunk":[…],"dropped":[…],"warnings":[…],"refused":null}`

## The runtime, per frame

`SecondaryMotionSystem.LateUpdate` runs after the Animator (execution order 1000):

1. **The animated pose.** A chain bone still holding exactly what the spring wrote last frame
   (compared float by float, never with the approximate `Quaternion ==`) was not written by the
   Animator: it goes back to its rest rotation. A bone the clip wrote keeps it. So the same chain
   works under Generic and Humanoid, with clips from `blender-retarget` (Auto-Rig Pro's export
   bakes every `cc_` bone at rest into each clip) and with `humanoid-motion` solves that never
   touch them.
2. **Reset instead of a step** on enable, `ResetPose()`, a teleport (moved more than
   `teleportDistance` or turned more than `teleportAngle` in one frame) and on coming back on
   screen after being skipped (`skipWhenInvisible`). Call `ResetPose()` after a spawn, a respawn,
   a pooled reuse or a camera cut.
3. **Fixed substeps** of `1/substepRate` (60), at most `maxSubsteps` (4) a frame; a frame longer
   than `maxFrameDt` (1/15 s) counts as that much. Fixed, not split to fit the frame: the sag a
   pull-to-pose spring settles at depends on the substep length. Per substep, per particle after
   the pinned first: Verlet with drag, gravity and wind; the pull toward the animated segment hung
   from the simulated parent; collider push-out; the angle clamp; the exact bone length, then up
   to two more push-out and length passes for a particle pressed between a collider and its
   parent.
4. **Write.** Root to tip, each bone turns along its simulated segment, read between the last two
   substeps by the time left over, so a frame with no substep (144 Hz, a 60 Hz frame that came in
   short) still moves instead of sticking for a frame; twist stays the animation's.

**Cost:** per frame, substeps × Σ over chains of particles × (1 + colliders it tests), plus one
`FromToRotation` per bone; no allocation, no `GetComponent` in the loop. The runner's full set (19
chains) is about forty particles. Keep particles × colliders × substeps in the low thousands per
character and read the real cost with `unity-profiling`.

`Simulate(dt)` steps one frame by hand (a recorder that calls `Animator.Update` first, a test);
`Rebuild()` after adding or removing a chain at runtime.

## Tests

`resources/Tests/SecondaryMotionTests.cs` (EditMode, namespace `UnityDev.SecondaryMotion.Tests`):
gravity settles a chain below its parent at exact lengths, stiffness returns it, sphere and
capsule colliders keep particles outside, a teleport resets instead of exploding, 30, 144 and
jittered frame rates agree, the chain moves on every frame at 144 Hz and at an uneven 60 Hz, the
angle clamp holds, unanimated bones return to rest, a zero-length bone makes no NaN, and the
`secondary/1` reader takes an empty chain list and refuses broken files. Run them in a project that has the files:

```
Unity -batchmode -projectPath <project> -runTests -testPlatform EditMode \
  -testFilter UnityDev.SecondaryMotion -testResults results.xml -logFile tests.log
```

## When it looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| Chains never move | Optimize Game Objects on; or the system sits above the model and found no chains; or the renderer is culled | turn it off and reimport; put the system on the Animator's GameObject; check `skipWhenInvisible` |
| Jitter or a buzz at rest | drag too low for the stiffness | raise `drag` |
| Chains move in slow motion at a low frame rate | frames longer than `maxFrameDt` lose the rest | raise `maxFrameDt` and `maxSubsteps` together |
| Hood or bag sinks into the back | collider radius below the shell; dropped from the chain's group | raise the radius on the rig side, re-run setup, read `shrunk` / `dropped` |
| A chain pops on the first frame or after a respawn | a joint starts inside a collider; no `ResetPose()` after a pooled reuse | re-run setup (rest-penetration gate); call `ResetPose()` |
| Vertices outside the hood move with it | the rig side's weights leak | fix the region weights rig-side; Unity does not repaint weights |
