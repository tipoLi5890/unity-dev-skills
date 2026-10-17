# Blend trees from script — 1D, 2D directional, and the sprite case

> Part of the `unity-animation` skill. A blend tree is one state whose motion is a weighted mix
> of clips, positioned by one or two float parameters. Build it from script: the positions are
> numbers that have to match the numbers the bridge writes, and a tree dragged together by hand
> matches them only until somebody retunes the speed.

The 1D tree on `MoveBlend` is already built by `CharacterAnimatorBuilder.cs`
(`unity-rigged-character` → `reference/editor-scripts.md`). This file covers what that one
leaves out: thresholds, the 2D types, in-place clips and sprite sets.

## 1. Which type

| `BlendTreeType` | Parameters | Use for | Constraint |
|---|---|---|---|
| `Simple1D` | 1 | Slow → fast along one axis: `MoveBlend` | Add children in ascending threshold order |
| `SimpleDirectional2D` | 2 | One clip per direction: strafe sets, 4-way and 8-way sprite sets | One motion per direction, plus one at (0, 0) |
| `FreeformDirectional2D` | 2 | Several speeds per direction: walk and run, each in 8 directions | Needs a motion at (0, 0) |
| `FreeformCartesian2D` | 2 | Two unrelated axes: forward speed × turn rate | Positions are a grid, not directions |
| `Direct` | one per child | Facial shapes, additive poses | Each child names its own parameter |

Two clips pointing the same way in a `SimpleDirectional2D` tree is the usual wrong choice: the
tree picks between them unpredictably. The builder refuses it and names the type to use.

## 2. Thresholds in a 1D tree

```csharp
var tree = new BlendTree {
    name = "MoveBlend", blendType = BlendTreeType.Simple1D, blendParameter = "MoveBlend",
    useAutomaticThresholds = false,              // or AddChild's thresholds are overwritten
    hideFlags = HideFlags.HideInHierarchy,
};
AssetDatabase.AddObjectToAsset(tree, controller);
tree.AddChild(jog, 0f);
tree.AddChild(run, 0.6f);
tree.AddChild(sprint, 1f);
```

- **`useAutomaticThresholds` spreads children evenly** between `minThreshold` and `maxThreshold`.
  With three clips that puts the middle one at 0.5 whatever you passed.
- **Put the threshold where the clip is true.** The bridge writes
  `InverseLerp(minSpeed, maxSpeed, speed)`; a run authored for 7 units/s in a 4–9 range belongs at
  `(7 - 4) / (9 - 4) = 0.6`, not at 0.5.
- **`tree.children` returns a copy.** To change a threshold afterwards, read the array, edit the
  element, assign the array back.
- **A tree created with `new BlendTree()` is not saved** until `AddObjectToAsset` puts it inside
  the controller. Skip it and the state's motion reads `None` after the next domain reload.

## 3. A 2D directional tree

`resources/Editor/DirectionalBlendTreeBuilder.cs` builds the state from clips keyed by direction.
Names carry the direction as their last token — `n ne e se s sw w nw`, `up down left right`,
`forward back`, a pair such as `back_left`, and `idle` for the centre.

```csharp
var clips = new List<AnimationClip>();   // runner_idle, runner_walk_n, runner_walk_e, …
var skipped = new List<string>();
var entries = DirectionalBlendTreeBuilder.FromNames(clips, skipped);

// Report first; show it; wait for a yes.
Debug.Log(DirectionalBlendTreeBuilder.Report(controller, 0, "Move", "MoveX", "MoveY", entries));

BlendTree tree = DirectionalBlendTreeBuilder.Build(controller, 0, "Move", "MoveX", "MoveY", entries);
Debug.Log(DirectionalBlendTreeBuilder.Describe(tree));     // read the positions back
```

```
controller   Assets/Animations/Runner.controller
state        Move  (exists — its motion is REPLACED)
tree         SimpleDirectional2D on MoveX, MoveY
parameter    MoveX  (add, Float)
parameter    MoveY  (add, Float)
motion       (0.000, 0.000)  runner_idle  0.800 s
motion       (0.000, 1.000)  runner_walk_n  0.667 s
motion       (1.000, 0.000)  runner_walk_e  0.667 s
…
```

Positions are unit vectors (diagonals at 0.707), so the bridge writes a **normalised** direction
scaled by how hard the character is moving:

```csharp
// 3D strafe: velocity in the character's own frame, as a fraction of top speed.
Vector3 local = transform.InverseTransformDirection(run.Velocity) / run.MaxSpeed;
anim.SetFloat(MoveXId, local.x, 0.1f, Time.deltaTime);
anim.SetFloat(MoveYId, local.z, 0.1f, Time.deltaTime);
```

To position clips by their real speed instead (units/s, `Compute Positions → Velocity XZ` in the
Inspector), pass `Entry` values with the authored speed as the vector's length, use
`BlendTreeType.FreeformDirectional2D`, and write the unscaled local velocity.

**The clip at (0, 0) is load-bearing.** With both parameters at 0 and nothing at the origin, the
tree blends opposing directions against each other and the feet skate. The builder reports its
absence as a warning; it is only safe to ignore when the bridge never writes (0, 0) (§5).

## 4. In-place clips and the playback rate

A locomotion clip either carries its own translation (root motion) or is authored on the spot
(in-place). With in-place clips the script moves the transform, and the feet slide unless the
clip plays at the rate the ground is passing:

```
MoveSpeed = ground speed / the speed the clip was authored for
```

`CharacterAnimatorBuilder.cs` wires `MoveSpeed` as the state's `speedParameter` for the single-clip
case. Three rules keep it honest:

- Write `MoveSpeed` undamped. A playback rate that lags the ground speed is the slide.
- Clamp it — 0.5 to 1.6 is a sane range. Beyond that the gait reads as slow motion or
  fast-forward, and the fix is a second clip in a 1D tree, not a wider clamp.
- Inside a tree the rate applies to the whole blend, so author the children for speeds that
  match their thresholds; then one `MoveSpeed` of 1 is right along the whole axis.

Who owns the transform when the clip does carry translation: `reference/root-motion.md`.

## 5. Sprite sets — the tree as a direction switch

A frame clip is an object-reference curve, and object references do not interpolate. In a tree of
sprite clips **the child with the highest weight supplies the frame**: the tree is a switch with
a 2D input. That makes `SimpleDirectional2D` the right container for a top-down character's
4-way or 8-way sets, and changes three rules.

**Write a facing, not a velocity.** Keep the last non-zero direction, so the character still
faces somewhere when it stops, and the tree never sits at the origin:

```csharp
Vector2 v = run.Velocity2D;                       // replace with your game's velocity
if (v.sqrMagnitude > 0.01f) _facing = Snap(v, _facing);
anim.SetFloat(FaceXId, _facing.x);                // undamped: frames do not blend
anim.SetFloat(FaceYId, _facing.y);
anim.SetBool(MovingId, v.sqrMagnitude > 0.01f);
```

Two states read the same pair: `Idle` (a tree of idle clips per direction) and `Move` (a tree of
walk clips), switched by `Moving` with a zero-duration transition
(`reference/sprite-state-graph.md`).

**Snap before writing, with hysteresis.** On an exact diagonal two children of a 4-way tree tie,
and noise in the input flips the winner every frame — the character flickers between two
facings. Quantise in the bridge and keep the current facing until the new one clearly wins:

```csharp
// 4-way: change axis only when the other axis leads by a margin.
static Vector2 Snap(Vector2 v, Vector2 current)
{
    bool wasHorizontal = Mathf.Abs(current.x) > Mathf.Abs(current.y);
    float bias = wasHorizontal ? 1.2f : 1f / 1.2f;
    return Mathf.Abs(v.x) * bias >= Mathf.Abs(v.y)
        ? new Vector2(Mathf.Sign(v.x), 0f)
        : new Vector2(0f, Mathf.Sign(v.y));
}
```

For 8-way, round `Mathf.Atan2(v.y, v.x)` to the nearest 45° with the same idea: stay in the
current sector until the angle is more than 30° from its centre.

**Give every clip in one tree the same length and frame count.** A tree plays its children in
step, by normalised time. Equal lengths mean a facing change lands on the same frame of the
walk cycle instead of restarting the stride.

## 6. Why a zero-length clip breaks a tree

A tree's length is the weight-blended length of its children, and the state's normalised time is
elapsed time divided by that length. A child of length 0 at weight 1 makes the divisor 0: the
state's `normalizedTime` stops being a number that exit times, `AttackWindowBehaviour` and
`AnimatorStateInfo.loop` arithmetic can use.

A clip has length 0 when every key sits at time 0 — a pose exported as one frame, the usual
"idle" at the origin of a directional tree. The builder refuses it. Fix the clip, not the tree:

- **3D pose:** in the model's import settings give the clip a range of at least two frames, or
  duplicate the key one frame later.
- **Sprite:** a clip built by `unity-2d-sprites` → `reference/sprite-animation.md` already has
  length `N / fps`, so a one-frame idle is `1 / fps` long. A clip keyed by hand at time 0 only
  is not.

Read it back before trusting it: `clip.length` in the report must be greater than 0 for every
`motion` line.
