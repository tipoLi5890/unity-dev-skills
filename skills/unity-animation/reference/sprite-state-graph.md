# The sprite state graph — idle, run, jump, fall, hurt

> Part of the `unity-animation` skill. A frame-clip character has nothing to cross-fade: a
> transition either swaps the frame now or swaps it late. Every default the Animator window
> gives a new transition — exit time on, 0.25 s duration — is a default for skeletal blending,
> and each one is a delay on a sprite.

Clips come first: `unity-2d-sprites` → `reference/sprite-animation.md` builds each one, and its
single-state controller is the whole graph for an idle or a one-shot. This file starts at the
second state. A sprite deformed by bones instead of swapped frame by frame is
`unity-2d-animation`; the graph below drives either.

## 1. The graph

```
parameters   Grounded Bool · Moving Bool · VelY Float · Hurt Trigger

Idle  ⇄ Run          Grounded && Moving  /  Grounded && !Moving
Idle, Run → Jump     !Grounded && VelY > 0        (listed first: wins when both hold)
Idle, Run → Fall     !Grounded
Jump → Fall          VelY < 0
Jump, Fall → Run     Grounded && Moving           (listed first: no idle frame on landing)
Jump, Fall → Idle    Grounded
Any State → Hurt     Hurt
Hurt → Idle          exit time 1
```

`resources/Editor/SpriteStateGraphBuilder.cs` builds exactly this from clips named by their last
token (`runner_idle`, `runner_run`, `runner_jump`, `runner_fall`, `runner_hurt`); jump, fall and
hurt are optional and their states are left out when the clip is missing.

```csharp
var clips = SpriteStateGraphBuilder.FindClips("Assets/Art/Runner/Clips");
Debug.Log(SpriteStateGraphBuilder.Report("Assets/Art/Runner/Runner.controller", clips));
// show the report, wait for a yes, then:
var controller = SpriteStateGraphBuilder.Build("Assets/Art/Runner/Runner.controller", clips);
Debug.Log(SpriteStateGraphBuilder.Describe(controller));
// states=Idle,Run,Jump,Fall,Hurt default=Idle transitions=13 parameters=4
```

An existing controller at the path has its parameters and layer 0 rebuilt in place, so its GUID
— and every Animator that references it — survives. Deleting and recreating the asset does not.

## 2. Transition settings

| Setting | Value | Otherwise |
|---|---|---|
| `hasExitTime` | `false` | The old clip finishes its cycle first: a jump that starts up to one run cycle late |
| `duration` | `0` | The swap waits out the duration, showing the old state's frames |
| `hasFixedDuration` | `true` | With it off, `duration` is a fraction of the source clip's length |
| `offset` | `0` | The destination starts part way through |
| Order in the state's list | Narrow condition first | The first transition whose conditions hold wins; `!Grounded` listed before `!Grounded && VelY > 0` means Jump never plays |

The one transition that keeps an exit time is `Hurt → Idle`, at `exitTime = 1`: leave when the
one-shot has played once. That is presentation waiting on presentation. The game's hurt — the
invulnerability window, the knock-back, when input comes back — runs on the game's own timer and
does not ask the Animator whether the clip has finished.

**A one-shot clip has Loop Time off, a cycle has it on.** The builder reports a run with Loop
Time off (it freezes on its last frame) and a hurt with it on (exit time 1 then fires once per
loop, not once per hit).

## 3. Any State, and re-entering every frame

An Any State transition is evaluated from every state, **including its own destination**. With
a condition that stays true, the Animator takes the transition again on every evaluation: the
state restarts each frame and the character is stuck on frame 0 of the clip.

| Condition on the Any State transition | `canTransitionToSelf` | Result |
|---|---|---|
| Bool, held while the game is in the state (`Hurting`) | `false` | Enters once, stays, leaves when the bool clears |
| Bool, held | `true` | Re-enters every frame — frozen on the first frame |
| Trigger | `true` | Consumed on entry, so no loop; a second hit restarts the clip |
| Trigger | `false` | A second hit during the clip stays set, queues, and replays the clip after it ends |

The builder uses a trigger with `canTransitionToSelf = true`. When hurt is a state the game
holds — a stun with a duration — switch to a Bool written by the bridge and set it `false`:

```csharp
AnimatorStateTransition any = sm.AddAnyStateTransition(hurt);
any.AddCondition(AnimatorConditionMode.If, 0f, "Hurting");
any.canTransitionToSelf = false;
any.hasExitTime = false; any.hasFixedDuration = true; any.duration = 0f;

AnimatorStateTransition back = hurt.AddTransition(idle);
back.AddCondition(AnimatorConditionMode.IfNot, 0f, "Hurting");
back.hasExitTime = false; back.hasFixedDuration = true; back.duration = 0f;
```

## 4. Facing — `flipX`, or a clip per direction

| | `SpriteRenderer.flipX` | Directional clips |
|---|---|---|
| Art cost | One set | Two sets (side view) or four to eight (top-down) |
| Right when | The character is symmetric enough to mirror | A satchel on one shoulder, a number on the chest, lighting drawn into the frame |
| Written by | The bridge, from the game's facing | A `SimpleDirectional2D` tree on `FaceX` / `FaceY` — `reference/blend-trees.md` §5 |

Rules for `flipX`:

- **The bridge writes it, from the game's facing — never from the sign of this frame's
  velocity.** Velocity passes through zero when the runner stops; a facing does not. The bridge
  for a 2D motor, and where its facing comes from: `unity-2d-controller` →
  `reference/facing-and-animator-bridge.md`.
- **Do not key `flipX` in a clip.** That is a second writer, and the clip wins on the frames it
  has a key for.
- **`flipX` mirrors about the sprite's pivot.** With the pivot at the horizontal centre the
  character turns on the spot; with it anywhere else the body jumps sideways on every turn.
- **It flips the picture only.** Children — a hitbox, a muzzle point — stay where they are.
  Mirror their local x in the same bridge method that writes `flipX`.
- **Do not flip by `transform.localScale.x = -1` on the object that holds the collider or the
  Rigidbody2D.** Negative scale mirrors the colliders with it. If a scale flip is needed for
  child sprites, put it on a `Visual` child and keep physics on the parent.

## 5. The object layout the graph assumes

```
Runner              gameplay, Rigidbody2D, collider, RunAnimatorBridge
└── Visual          Animator, SpriteRenderer      ← clips bound with path ""
```

A clip's binding path is relative to the Animator. Clips built for a renderer on the Animator's
own object have path `""`, and moving the Animator to the parent turns every one of them inert —
it plays and nothing changes. Keep the Animator on the object the clips were built against, and
let the bridge on the parent hold a reference to it.

**Clips do not move the character.** A position curve in a sprite clip is a second writer of
the transform the game owns. A hop, a squash or a recoil is animated on `Visual`, whose local
position nothing else writes.

## 6. The graph with no parameters

When the game's state maps one-to-one onto clips and nothing blends, the graph can be states
with no transitions at all, and the bridge selects one:

```csharp
int want = StateHashFor(run.Phase);          // replace with your game's state → hash table
if (want != _shown) { _anim.Play(want, 0, 0f); _shown = want; }
```

Call `Play` on change only: with an explicit normalised time it restarts the clip every call.
This trades the transition table for one line, keeps one writer, and loses the return path of a
one-shot — the bridge has to select the next state when the game's hurt ends, which the game
knows anyway.

## 7. Proving it

`templates/AnimatorStateJourneyTest.cs` samples the Animator's current state name into the probe
as `animState` and asserts it agrees with the game's `state` within 3 frames of every change. A
transition left at the default 0.25 s, or with exit time on, fails it by a wide margin:

```
1 violation(s):
  n=52 frame=1298 t=4.210 anim-agrees: state=Air wants Air, animState=Run for more than 3 samples
```

The journey, the recorder and the timeline it writes are `unity-play-harness` →
`reference/journeys.md`.
