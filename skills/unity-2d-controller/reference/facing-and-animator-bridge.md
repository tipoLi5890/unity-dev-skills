# Facing and the Animator bridge — one fact, written once a frame

> Part of the `unity-2d-controller` skill. Which way the runner faces is a fact the controller
> owns; `resources/AnimatorBridge2D.cs` is the one script that turns it, and three other facts,
> into a picture. This file covers where the facing comes from in each movement model, the
> three ways to show it and what each breaks, and the bridge's contract with the Animator. The
> graph on the other side of the contract is `unity-animation`.

## 1. Where the facing comes from

| Model | `Facing` is | Type |
|---|---|---|
| Platformer (`PlatformerController2D`) | The sign of the last non-zero horizontal **input**; set away from the wall by a wall jump, to the dash direction by a dash | `int`, −1 or +1 |
| Top-down (`TopDownMotor2D`) | The last non-zero move direction, snapped to four; or the aim, with `faceAim` | unit `Vector2` |
| Cell (`GridStepMover`) | The direction of the last step asked for, refused ones included | `Vector2Int` |

**Never from velocity.** Velocity passes through zero when the runner stops, reverses for a
frame when it is pushed, and points along a wall it is sliding on. A facing derived from it
flickers on every stop and turns the runner round on every knock-back. The controllers set it
from intent and keep it when intent is zero.

## 2. Three ways to show it

| | `SpriteRenderer.flipX` | Negative scale on a `Visual` child | A clip set per direction |
|---|---|---|---|
| Art cost | One set | One set | Two sets side-on; four or eight from above |
| Mirrors | The one sprite | Every child renderer, bone and attachment under `Visual` | Nothing: each direction is drawn |
| Right when | A single-sprite character symmetric enough to mirror | A character of several sprites or a skinned rig | A satchel on one shoulder, a number on the chest, light drawn into the frames; anything seen from above |
| Written by | The bridge (`flipSprite`) | The bridge's owner, one line | The Animator, from `FaceX` / `FaceY` |

What each breaks:

**`flipX`**
- Mirrors about the sprite's **pivot**. A pivot off the horizontal centre makes the body jump
  sideways on every turn.
- Flips the picture and nothing else. A muzzle point, a hitbox or a held pickup stays on the
  old side: list them in `mirrorWithFacing` and the bridge negates their local x on the same
  line that writes `flipX`.
- Must not be keyed in a clip. A keyed `flipX` is a second writer, and the clip wins on the
  frames it has a key for.
- Under 2D lights with a normal map, put a light to one side and turn the runner: the lit side
  must stay towards the light. If it follows the sprite — `unity-2d-rendering` →
  `reference/shadows-and-normals.md`.

**Negative scale**
- On the object that carries the `Rigidbody2D` or a collider it mirrors the collider too: an
  off-centre box moves to the other side, and a physics shape is rebuilt on every turn. Only
  ever on a `Visual` child that holds no physics.
- Flips the sign of every child's local x and the winding of every child's rotation, which is
  the point — and which also mirrors text, a health bar and a particle system's direction.
  Keep those outside `Visual`.

```csharp
// The one line, for a multi-sprite or skinned character. Put it where the facing changes.
visual.localScale = new Vector3(run.Facing, 1f, 1f);
```

**Directional clip sets**
- Each direction is a state or a blend-tree entry, so the art cost multiplies by the number of
  actions: four directions × idle, walk, carry, hurt is sixteen clips.
- The facing must be **quantised and held** before it reaches the Animator, or two clips trade
  places on a diagonal. `TopDownMotor2D` snaps to four with the current facing winning a near
  tie.
- Written undamped: frames do not blend, so a damped `FaceX` shows the wrong direction for the
  length of the damp.
- Side-on, a left set and a right set can still share `flipX` for everything but the
  asymmetric detail — the cheapest fix is often to draw the satchel as a separate sprite.

## 3. The bridge's contract

One component, on the runner, after gameplay (`DefaultExecutionOrder(100)`), in `Update`. It
reads the controller and writes every parameter every frame:

| Fact | Default parameter | Type | Read from |
|---|---|---|---|
| Grounded | `Grounded` | Bool | `PlatformerController2D.Grounded`; true for the other two models |
| Moving | `Moving` | Bool | Platformer: horizontal **speed** above 0.1 · top-down: `Moving` · cell: `Stepping` |
| Vertical speed | `VelY` | Float | `PlatformerController2D.Velocity.y` |
| Speed | *(empty: not written)* | Float | Ground speed ÷ `authoredRunSpeed` — a playback-rate multiplier |
| Facing | *(empty: not written)* `FaceX`, `FaceY` when set | Float | The model's `Facing` as a vector |

The names are fields. The defaults are the ones the sprite state graph of `unity-animation` is
built with (`Grounded`, `Moving`, `VelY`); set `faceX` and `faceY` to `FaceX` and `FaceY` for
its directional blend tree, and `speed` to the parameter a walk state uses as its speed
multiplier. Clear a name to leave it unwritten.

Why it is built this way — the full argument is `unity-animation` →
`reference/parameter-contract.md`:

- **One writer.** No other script calls `SetBool` or `SetFloat` on this Animator, and no clip
  has a curve named like a parameter. Find a second one with
  `grep -rnE 'Set(Bool|Float|Integer|Trigger)\(' Assets --include='*.cs'`.
- **Every frame, not on change.** A pooled runner that was disabled comes back with the
  Animator at its defaults; the next `Update` repairs all of it.
- **Checked at start.** A name the controller does not have, or has with another type, logs
  `[ANIM2D]` once in `Awake` and is then skipped. An unchecked rename is a character frozen in
  one pose and a warning per frame nobody reads.
- **`Moving` from speed on a platformer.** A runner pushed against a wall with the stick held
  is not running; input would say it is.
- **Undamped.** `VelY` decides Jump against Fall on its sign; `Speed` damped is feet sliding.
- **`Update`, because the Animator evaluates after it.** With `Animator.updateMode` set to
  `AnimatorUpdateMode.Fixed`, move the body of `Update` to `FixedUpdate`.
- **Instants are not copied.** Hurt, land and jump arrive as events from the game
  (`PlatformerController2D.Jumped`, `Landed`); subscribe in the bridge's owner and set the
  trigger there, on an Animator where that transition is reachable from Any State.

## 4. Which graph for which model

| Model | Graph | Parameters used | Built by |
|---|---|---|---|
| Platformer, one sprite | Idle ⇄ Run, Jump, Fall | `Grounded`, `Moving`, `VelY`; `flipSprite` on | `unity-animation` → `reference/sprite-state-graph.md` |
| Top-down, four or eight directions | One directional tree per action, switched by `Moving` | `Moving`, `FaceX`, `FaceY`; `flipSprite` off | `unity-animation` → `reference/blend-trees.md` |
| Cell | The same trees; `Moving` is `Stepping` | `Moving`, `FaceX`, `FaceY` | `unity-animation` → `reference/blend-trees.md` |
| Skinned 2D rig | Any of the above, mirrored by scale on `Visual` | as above; `flipSprite` off | `unity-2d-animation` → `reference/skeletal-vs-frames.md` |

A walk cycle on a cell mover should finish with the step: author it so one loop covers one
cell, and write `speed` so playback rate follows `Velocity` — with a 0.36 s loop drawn for one
1-unit cell, `authoredRunSpeed` is 1 / 0.36 = 2.78, and a 0.18 s step plays it at rate 2.

## 5. The object layout

```
Runner              controller, motor, Rigidbody2D, collider, AnimatorBridge2D
├── Visual          Animator, SpriteRenderer      ← flipX or negative scale lives here
└── Muzzle          listed in mirrorWithFacing
```

Physics on the parent, picture on the child. The Animator never has a position curve for
`Runner`: a clip that moves the body is a second writer of the transform the motor owns. A
hop, a squash or a recoil is animated on `Visual`, whose local position nothing else writes.

## 6. Traps

| Symptom | Cause |
|---|---|
| The runner flickers left and right when it stops | Facing from velocity, or `flipX` from the sign of this frame's x speed |
| Turning makes the body jump half a unit | Pivot off-centre under `flipX`; or negative scale on the collider's object |
| The gun fires from the wrong side after a turn | The muzzle is not in `mirrorWithFacing` |
| Jump clip never plays, Fall does | `VelY` damped, or the `!Grounded` transition listed before `!Grounded && VelY > 0` |
| Run plays against a wall | `Moving` written from input |
| Character frozen in one pose | A renamed parameter: read the `[ANIM2D]` error from `Awake` |
| Sprite direction lags the stick from above | `FaceX` / `FaceY` written with damping |
| Lit from the wrong side when facing left | A normal map on a mirrored sprite — the check in §2 |

## Where each need is answered

| Need | Answer |
|---|---|
| The parameter rule, triggers that queue | `unity-animation` → `reference/parameter-contract.md` |
| Idle / Run / Jump / Fall built from script | `unity-animation` → `reference/sprite-state-graph.md` |
| Directional trees, thresholds, quantising a facing | `unity-animation` → `reference/blend-trees.md` |
| Frames into clips, pivots on one ground line | `unity-2d-sprites` → `reference/sprite-animation.md` |
| Bones, skinned sprites, swapping parts | `unity-2d-animation` → `reference/skeletal-vs-frames.md` |
| Sorting a multi-sprite character as one | `unity-2d-rendering` → `reference/sort-order.md` |
