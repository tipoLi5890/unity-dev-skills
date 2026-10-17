---
name: unity-animation
description: >-
  Keep an Animator a rendering of the game's state, for 3D Humanoid and 2D
  frame-clip characters: one writer per parameter through a bridge, blend
  trees and sprite state graphs built from script, AnimationEvents and attack
  windows that survive interruption, override controllers, foot and hand IK,
  Timeline handover, root motion, and a journey proving the shown state
  follows the game. Load for: "the animation is stuck", "the attack plays by
  itself", "the jump starts late", "footsteps fire twice", "the feet slide",
  "the sprite flickers between directions", "the hitbox stays on". Importing
  rigs is unity-rigged-character; frames into clips is unity-2d-sprites;
  agent coupling is unity-navigation.
---

# unity-animation — the game's state is the truth, and the Animator renders it

> **An Animator is a state machine, and the game already has one.** Every "stuck in the jump",
> "attack played twice", "hitbox stayed on" report is the two disagreeing. They cannot disagree
> when one of them is a copy: the game owns the state, one bridge writes it into parameters
> once per frame, and nothing in gameplay waits on an animation unless a **named** event says so.

The same contract serves a 3D Humanoid and a 2D frame-clip character. What differs is how the
picture is allowed to follow:

| | 3D skeletal | 2D frame clips |
|---|---|---|
| A state change shows | Over a 0.08–0.15 s cross-fade | On the same frame: duration 0, no exit time |
| Two clips at once | Blend by weight | The heavier one supplies the frame — a switch |
| Facing | The transform's rotation | `SpriteRenderer.flipX`, or one clip per direction |
| Pose correction | IK after the clip | None — offsets go on a `Visual` child |
| Who moves the transform | One owner, chosen once (`reference/root-motion.md`) | The game, always |

---

## The contract

| Rule | Looks like | Broken when |
|---|---|---|
| **One writer per parameter** | A bridge beside the Animator: reads the game, writes every parameter in `Update` | `SetBool` / `SetTrigger` appears in an input handler, a hazard, a UI button |
| **Gameplay never reads the Animator** | Decisions use the game's own flags and timers | `GetCurrentAnimatorStateInfo(0).IsName("Attack")` guards a gameplay branch |
| **Only named moments cross back** | An AnimationEvent, an attack window, a Timeline signal — each with a game-side fallback | A coroutine waits `clip.length` seconds; a hit resolves "when the swing looks right" |

A trigger is the usual first breach. It is a bool the Animator clears **only when a transition
consumes it**: set where no transition can take it, it waits — a frame or ten seconds — and
fires on its own later. Raise instants through Any State, or use a Bool the bridge derives from
game state. → `reference/parameter-contract.md`

---

## Start here

1. **Audit what exists.** `AnimatorParamAudit.Json(controller)` lists every parameter, where
   the graph reads it and which scripts write it. Fix every verdict that is not `ok` before
   touching a transition.
2. **Write the bridge.** One component, hashed ids, every parameter every frame, a check at
   `Awake` that each id exists in the controller. → `reference/parameter-contract.md` §3
3. **Build the graph from script**, so its numbers match the numbers the bridge writes.
   3D: `unity-rigged-character` → `reference/editor-scripts.md` builds the locomotion
   controller (`Grounded`, `MoveBlend`, `MoveSpeed`, `Hurt`); add directional trees with
   `DirectionalBlendTreeBuilder`. 2D: `SpriteStateGraphBuilder`. Both report first.
4. **Mark the moments the game listens for** — events with `ClipEventWriter`, spans with
   `AttackWindowBehaviour` — and give each a game-side fallback.
5. **Prove it.** `templates/AnimatorStateJourneyTest.cs` samples `animState` beside the game's
   `state` and fails when they disagree for more than 3 frames.

Copy `resources/AttackWindowBehaviour.cs` and `resources/FootIK.cs` into a Runtime assembly, the
four files under `resources/Editor/` into an Editor one, and the template into a PlayMode test
assembly next to the harness files.

| File | Does | Writes assets |
|---|---|---|
| `resources/Editor/AnimatorParamAudit.cs` | Parameters × graph × script text scan, as JSON | No |
| `resources/Editor/DirectionalBlendTreeBuilder.cs` | A 2D directional tree state from clips named by direction | Yes — `Report` first |
| `resources/Editor/SpriteStateGraphBuilder.cs` | Idle / run / jump / fall / hurt controller from named clips, rebuilt in place | Yes — `Report` first |
| `resources/Editor/ClipEventWriter.cs` | Adds or moves an event by normalised time; reads the clip back | Yes — report clip, function and time first |
| `resources/AttackWindowBehaviour.cs` | Open / close callbacks by normalised time, closed on any exit | — |
| `resources/FootIK.cs` | Humanoid foot planting from two raycasts | — |

---

## Load what the situation needs

| The situation | Read |
|---|---|
| A parameter two scripts set; "the attack plays by itself later"; a blend that snaps; a renamed parameter that froze the character | `reference/parameter-contract.md` |
| Strafe or walk/run trees; a 4-way or 8-way sprite set; feet sliding on in-place clips; a tree whose time stops | `reference/blend-trees.md` |
| A 2D character's jump shows late; the hurt clip freezes on frame 0; the sprite flickers between facings; flipX versus directional clips | `reference/sprite-state-graph.md` |
| Footsteps fire twice; an event never arrives; the hitbox stays on after a hit interrupts the swing; events on a clip inside a model | `reference/events-and-windows.md` |
| The hitbox an attack window opens: one swing, one damage event | `unity-combat` → `reference/attack-windows.md` |
| Weapon sets or skins on one graph; "swapping the controller reset the character" | `reference/override-controllers.md` |
| `OnAnimatorIK` never called; feet floating on slopes; a hand that must reach a switch; whether Animation Rigging is worth adding | `reference/ik-and-rigging.md` |
| A cutscene takes the character and the game never gets it back; signals; skipping | `reference/timeline.md` |
| Animates on the spot, moves twice, or slides back each loop; a Rigidbody under root motion | `reference/root-motion.md` |
| Import, Avatar, Humanoid versus Generic, Mixamo clips, the locomotion controller itself | `unity-rigged-character` → `reference/editor-scripts.md` |
| Turning a frame set into a clip; pivots and ground line; the one end-of-clip event | `unity-2d-sprites` → `reference/sprite-animation.md` |
| An agent and an Animator both moving one character; a head tracking the path | `unity-navigation` → `reference/recipes.md` |
| The probe, the recorder, running the journey headless | `unity-play-harness` → `reference/journeys.md` |
| The bridge for a 2D character: facing, grounded and speed read from the motor | `unity-2d-controller` → `reference/facing-and-animator-bridge.md` |
| The bridge for a 3D character: grounded, gait and speed read from the mover | `unity-3d-controller` → `reference/animator-bridge.md` |
| Where the bridge's inputs come from — the input struct the game reads | `unity-input` |
| The camera that follows the character, and jitter between its clock and the Animator's | `unity-camera` |
| Which movement model the game uses, and so which rows above apply | `unity-gameplay` |

---

## Numbers to start from

| Quantity | 3D skeletal | 2D frame clips |
|---|---|---|
| Transition duration into a reaction (jump, hurt) | 0.05–0.10 s, no exit time | 0, no exit time |
| Transition duration between gaits | 0.10–0.20 s | 0 |
| `SetFloat` damp on a blend position | 0.08–0.15 s | 0 |
| `SetFloat` damp on a condition or a playback rate | 0 | 0 |
| `MoveSpeed` (playback rate) clamp | 0.5–1.6 | — |
| Journey budget: `animState` agrees with `state` within | 3 frames once the fade is 0; else fade + 3 | 3 frames |
| Attack window, as fractions of the state | open 0.25, close 0.55 — then tune per clip | same |
| Foot IK smoothing · ray reach below the foot | 0.1 s · 0.45 units | — |
| Hand IK weight ramp | 0.15–0.25 s | — |

---

## Discipline

- **The bridge writes every parameter every frame.** A value set on change goes stale the first
  time the Animator is disabled, pooled or has its controller swapped; a value written each
  frame heals on the next one.
- **Hash once, check once.** `Animator.StringToHash` in a `static readonly int`, and an `Awake`
  loop over `animator.parameters` that logs an error for an id the controller lacks. A missing
  parameter is otherwise a warning and a frozen character.
- **A trigger is for an instant the graph can take now.** Anything that can be raised where no
  transition reads it is a Bool derived from state, or is reset when the state ends.
- **No exit time on a transition the game causes.** Exit time is for a clip finishing on its
  own; on a jump or a hit it is up to one full cycle of delay.
- **List the narrow transition first.** A state's transitions are tried in order and the first
  whose conditions hold wins.
- **Any State with a held Bool needs `canTransitionToSelf = false`**, or the state re-enters
  every evaluation and sits on its first frame.
- **Whatever an event opens, a StateMachineBehaviour or the game closes.** An event at 55% never
  fires when the state is left at 40%; `OnStateExit` runs however the state is left.
- **Filter events by weight.** Every clip above zero weight fires its events — both children of
  a blend, both sides of a cross-fade. Read `AnimationEvent.animatorClipInfo.weight`.
- **Normalised time for windows, game time for rules.** "Open at 25% of the swing" survives a
  retimed clip; "invulnerable for 0.4 s" is a game timer.
- **One owner of the transform.** Root motion, a mover, an agent and a Rigidbody are four
  candidates; pick one and make the others listeners. An empty `OnAnimatorMove` is an owner that
  moves nothing.
- **IK weights and rig weights are parameters too.** The bridge writes them from game state; a
  foot that decides for itself from a raycast is a second opinion about `Grounded`.
- **Report before an Editor tool writes.** The builders print what they would create or replace;
  show it and wait for a yes. Then read the asset back — `Describe` — not the exit code.
- **Check the package before the `using`.** Read `Packages/packages-lock.json` for
  `com.unity.animation.rigging`, `com.unity.timeline` or `com.unity.2d.animation` before writing
  code against them.
- **Sample the shown state, do not eyeball it.** `animState` in the probe beside `state` turns
  "the jump looks late" into a count of frames.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Importing a model, Avatars, Humanoid versus Generic, Mixamo, the base locomotion controller | `unity-rigged-character` |
| Rigging and skinning a character that has no skeleton yet | `blender-character-rig` |
| Retargeting stock or purchased clips onto a rig in Blender, before they reach Unity | `blender-retarget` |
| Slicing sheets, frames into AnimationClips, pivots and the ground line | `unity-2d-sprites` |
| Bones, skinning weights, PSB rigs, Sprite Library and 2D IK on a sprite | `unity-2d-animation` |
| Generating the sprite frames or the sheet in the first place | `codex-visual` |
| A NavMeshAgent sharing the transform with the Animator | `unity-navigation` |
| Reading devices and actions into the struct the game consumes | `unity-input` |
| Camera follow, Cinemachine, camera shake on a hit | `unity-camera` |
| Choosing the movement model, perspective and genre constraints | `unity-gameplay` |
| A hitbox trigger that never fires once the window is open | `unity-physics-3d` · `unity-physics-2d` |
| Playing the footstep or the swing sound an event asks for | `unity-audio` |
| The probe, situations, journeys and timelines themselves | `unity-play-harness` |
| Running tests headless, screenshots, trusting a result file | `unity-debug` |
| Animator cost on a crowd: culling modes measured, not guessed | `unity-profiling` |
