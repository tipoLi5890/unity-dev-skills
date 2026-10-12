# Effectors and joints

Part of the `unity-physics-2d` skill. SKILL.md §6 lists the one-way platform checks; this file
holds the effectors and the joints a 2D game reaches for, with the settings that decide whether
they work.

## What every effector needs

An effector is a component beside a collider. It acts on the bodies touching that collider, and
only when the collider says so.

1. **A `Collider2D` on the same GameObject with `usedByEffector = true`.** Without it the effector
   is inert. Under a composite, the flag is on the `CompositeCollider2D`.
2. **The collider's trigger flag matches the effector's kind** — the table below.
3. **The target has a Dynamic `Rigidbody2D`** for any effector that applies force. A Kinematic
   sentry ignores an area effector exactly as it ignores `AddForce`.
4. **`Effector2D.useColliderMask` and `colliderMask`.** With `useColliderMask` on — it is on
   in a new effector, with every layer set — the effector decides which layers it affects from
   its own mask and the layer collision matrix is not consulted for that collider. A platform
   that stopped holding a new enemy type usually has a mask written before the layer existed.

| Effector | Collider | Does | Courier-run use |
|---|---|---|---|
| `PlatformEffector2D` | Solid | One-way pass, no friction or bounce on the sides | A ledge the runner jumps up through |
| `SurfaceEffector2D` | Solid | Drives touching bodies along the surface at `speed` | A conveyor rooftop; a boost strip |
| `AreaEffector2D` | Trigger | A constant force inside the area | A launch pad's updraught; wind across a gap |
| `PointEffector2D` | Trigger | Attracts to or repels from a point | A blast that scatters pickups |
| `BuoyancyEffector2D` | Trigger | Floats bodies at a surface level, with flow | A flooded yard |

## `PlatformEffector2D`, setting by setting

| Property | Set to | Meaning |
|---|---|---|
| `useOneWay` | `true` | Bodies pass from behind the surface and are stopped from in front of it |
| `surfaceArc` | `170` | Width in degrees of the arc, centred on local up, that counts as the surface. Contacts whose normal falls outside it pass. A new effector has `180` |
| `rotationalOffset` | `0` | Rotates the arc away from local up: `180` makes a ceiling the runner drops through from above and cannot rise through |
| `useOneWayGrouping` | `true` for a multi-collider runner | All of a body's contacts with the platform pass or block together |
| `useSideFriction`, `useSideBounce` | `false` | Whether the faces inside `sideArc` apply friction and bounce. Off, a runner slides down the side of a platform and does not stick |
| `sideArc` | Leave | Width of the arcs centred on local left and right that count as sides |

`sideFriction` and `sideBounce` are the obsolete names of the two `useSide…` properties.

Why each failure looks the way it does:

- **Blocks from below.** `useOneWay` is off, `usedByEffector` is off, or the collider was merged
  into a composite that does not carry the flag. Check `collider.usedByEffector` and
  `collider.composite` on the object that is actually colliding.
- **Passes from above.** The platform's local up points down — a 180° Z rotation, or
  `rotationalOffset` left at a test value.
- **The runner catches on the end of the platform.** `surfaceArc` is 180, so a contact on the
  vertical end face counts as surface. Narrow it to 170.
- **The runner is held with its head through the platform.** Two colliders, one above the surface
  and one below, decided separately. `useOneWayGrouping`.
- **The ground check says grounded while rising through it.** The check is a cast, and no query
  knows about effectors. Accept a platform hit only when the hit normal points up, the runner's
  feet are above the hit point and its vertical velocity is not upward —
  `unity-2d-controller` → `reference/platformer.md`.
- **A new body type falls through.** `useColliderMask` is on and `colliderMask` lacks its layer.

### Dropping through

```csharp
// On the runner. Down + jump while standing on a Platform-layer collider.
IEnumerator DropThrough(Collider2D runner, Collider2D platform)
{
    Physics2D.IgnoreCollision(runner, platform, true);
    yield return new WaitForSeconds(0.25f);
    if (runner != null && platform != null) Physics2D.IgnoreCollision(runner, platform, false);
}
```

0.25 s covers a 1-unit-thick platform at any fall speed above 4 units/s. The ignore is one pair:
the sentry on the same ledge stays where it is. Two alternatives and what each breaks — disabling
the platform's collider drops everything on it; flipping `rotationalOffset` to 180 does the same
and also blocks whatever jumps up at it from below.

If the runner can be pooled or respawned during those 0.25 s, restore the pair in `OnDisable` as
well; the reason is in `reference/layers-and-matrix.md`.

## The force effectors in brief

- **`AreaEffector2D`** — `forceAngle`, `forceMagnitude`, `forceVariation`; `useGlobalAngle` picks
  world or local space for the angle; `forceTarget` applies the force at the body's centre of
  mass or at the collider (`EffectorSelection2D.Rigidbody` or `Collider`), which decides whether
  an off-centre shape spins. `linearDamping` and `angularDamping` slow bodies while inside.
- **`PointEffector2D`** — a negative `forceMagnitude` attracts and a positive one repels;
  `forceMode` is `EffectorForceMode2D.Constant`, `InverseLinear` or `InverseSquared`, with
  `distanceScale` scaling the distance used; `forceSource` and `forceTarget` choose collider or
  body positions.
- **`SurfaceEffector2D`** — `speed`, `speedVariation`, `forceScale` (how hard it pulls a body
  towards that speed: `1` snaps, lower lets the runner fight it); `useContactForce` applies the
  force at the contact point and so rolls round bodies; `useFriction` and `useBounce` keep the
  material's values.
- **`BuoyancyEffector2D`** — `surfaceLevel` in the effector's local Y, `density` of the fluid
  against the body's own, `linearDamping` and `angularDamping`, and `flowAngle`, `flowMagnitude`,
  `flowVariation` for a current.

Each of these acts once per step on every touching body, so a force effector over a field of
forty sleeping pickups wakes and simulates all forty. Narrow it with `colliderMask`.

## Joints worth knowing

A joint lives on one `Rigidbody2D` and constrains it to `connectedBody`, or to a fixed world point
when `connectedBody` is empty. Put the joint on the Dynamic body — the one that should move.

| Joint | Keeps | Key properties | Courier-run use |
|---|---|---|---|
| `DistanceJoint2D` | Two anchors a fixed distance apart, rigidly | `distance`, `autoConfigureDistance`, `maxDistanceOnly` (a rope: slack when closer) | A swinging hazard on a chain |
| `SpringJoint2D` | Two anchors near a distance, softly | `distance`, `frequency` (Hz; higher is stiffer), `dampingRatio` (`0`–`1`; `1` does not oscillate) | A pickup bobbing under a drone |
| `HingeJoint2D` | A shared pivot, free to rotate | `useLimits` + `limits` (`JointAngleLimits2D`), `useMotor` + `motor` (`JointMotor2D`), read `jointAngle` | A gate that swings; a see-saw rooftop |
| `SliderJoint2D` | Motion on one line | `angle`, `autoConfigureAngle`, `useLimits` + `limits` (`JointTranslationLimits2D`), `useMotor` + `motor`, read `jointTranslation` | A crusher hazard; a lift |
| `TargetJoint2D` | One body pulled towards `target` | `target`, `autoConfigureTarget`, `maxForce`, `frequency`, `dampingRatio` | Dragging a pickup with the pointer |

`FixedJoint2D`, `RelativeJoint2D`, `FrictionJoint2D` and `WheelJoint2D` complete the set.

Common to all, from `Joint2D` and `AnchoredJoint2D`:

- **`anchor` and `connectedAnchor` are in each body's local space.** With
  `autoConfigureConnectedAnchor` on, the connected anchor is computed for you from the pose the
  bodies are in — convenient while authoring, and a moving target for a pooled object set up in
  code. Turn it off there and write both anchors.
- **`enableCollision`** decides whether the two joined bodies collide with each other. Off by
  default; a gate hinged to its own frame wants it off, a chain of crates wants it on.
- **Breaking.** `breakForce` and `breakTorque` are infinite by default. When the reaction exceeds
  either, `breakAction` decides what happens:

  | `JointBreakAction2D` | Effect |
  |---|---|
  | `Destroy` | Calls `OnJointBreak2D`, then destroys the joint component |
  | `Disable` | Calls `OnJointBreak2D`, then disables it — the choice for anything pooled |
  | `CallbackOnly` | Calls `OnJointBreak2D` and leaves the joint working |
  | `Ignore` | Nothing |

  `void OnJointBreak2D(Joint2D joint)` arrives on the GameObject carrying the joint. Read
  `joint.reactionForce` there to tune the threshold: log the peak during a normal run and set
  `breakForce` to about twice it.

Three traps:

- **A joint on a Kinematic body does not move it.** The joint applies forces, and a Kinematic body
  ignores forces. The Kinematic body can be the anchor end; the Dynamic body is the one that swings.
- **Mass ratio.** A 0.1-mass pickup hung from a 50-mass crate by a stiff joint stretches and
  jitters. Keep joined masses within about 10 : 1, or use a `SpringJoint2D`, which is built to give.
- **`simulated = false` on the body switches its joints off** along with its colliders. Park and
  restore a jointed chain as a whole.
