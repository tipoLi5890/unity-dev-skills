# A ball you integrate yourself: no PhysX

> Part of the `unity-physics-3d` skill. Every other page here diagnoses PhysX. This one is for when
> the ball should not be a `Rigidbody` at all: a sports ball whose flight, bounce and contact the
> rules depend on, that must replay bit for bit, and that the game must be able to **predict**
> exactly (for the receiver's plan, a landing marker, the animation's contact tick). Worked
> setting: a tennis ball in a 120 Hz rally simulation. Code: `resources/BallFlight.cs` (pure C#,
> its own small vector type, tested outside the Editor).

## When to leave PhysX for the ball

| You need | PhysX gives | Own integrator gives |
|---|---|---|
| Drag and Magnus lift | Linear damping only; forces added by script per `FixedUpdate` | The real terms, in one function |
| A spin-dependent bounce (topspin kicks, backspin checks) | Restitution and friction combine modes, no spin–friction coupling | An impulse model that couples them |
| Prediction that matches play exactly | A second `PhysicsScene` with copies of every collider and body, simulated separately; still a float simulation not promised to match the live one bit for bit | The same function and step for prediction and play: a test asserts they are identical every tick in flight |
| The same result from the same inputs, for replays | Deterministic on one platform only with the same step, insertion order and inputs, a discipline no test sees break; not promised across platforms | Deterministic by construction and tested: bit-identical within a build, event log identical across runtimes |
| A thread of its own | Main thread, the physics step | Anywhere: no engine types |

Keep PhysX for everything else (characters, props, triggers). The ball reads the venue from data,
not from colliders: §5.

## 1. Flight

Tennis ball: mass 0.057 kg, radius 0.0335 m, air density 1.21, drag coefficient 0.55.

| Term | Formula |
|---|---|
| Drag | `a = −k·|v|·v`, `k = ½ρC_dA/m ≈ 0.0206 /m` |
| Magnus | `a = ½ρA/m · C_L · |v| · (ω̂ × v)`, `C_L = 1 / (2 + |v| / (r·|ω|))`, clamped to 0.35 |
| Spin decay | `ω *= (1 − dt/τ)` per step, τ = 4 s; no `Exp`, so no transcendental call in the step |

- **Midpoint integration** (two acceleration evaluations per step), in double precision.
- **Directions are vectors, never angles.** Topspin for a ball travelling along `d` is
  `up × d̂ · rpm · 2π/60`; forehand or backhand is the sign of a cross product. Starting spins per
  shot kind: drive topspin 2 500 rpm, power drive 1 200, low drive 600, lob topspin 1 500, drop
  backspin 2 000, overhead smash 300.
- Tests that pin it: no drag and no spin match the analytic parabola; drag alone reaches terminal
  velocity; topspin dips shorter and backspin floats longer; spin falls to 1% by 4τ.

## 2. Contact: swept, earliest first, and never through a wall

Each 120 Hz tick is **8 substeps** (1.04 ms). Per substep: integrate freely; for each shape, find
the earliest time the ball's centre comes within one radius (bisection on the shape's distance
function, 24 halvings); re-integrate **from the substep start** to that time (not a lerp, so the
contact state equals the predicted one); respond; push out of overlap; spend the remaining time.
At most 4 contacts per substep.

- **The no-tunnelling rule:** the stretch of path where the ball overlaps a shape is at least a
  diameter long, so a substep must move less than that. At 40 m/s a substep moves 4.2 cm against
  a 6.7 cm diameter; at the 60 m/s speed clamp, 6.25 cm. A test fires a ball at 60 m/s at a 1 cm
  plate and asserts exactly one contact and no pass-through.
- **A zero-thickness surface (the net's plane) needs its own crossing test.** A distance function
  sampled at two instants cannot see a plane crossed in between.
- **Rolling needs its own resistance.** `BallFlight.cs` has none, so a ball set rolling rolls on;
  add a per-second loss on the ground (0.35/s in play, 0.3/s for the dead ball, §8).
- **A resting or rolling contact is not an event.** Below a 0.25 m/s normal speed, restitution is 0
  and no contact is reported; otherwise every substep of a rolling ball emits a "bounce". A test
  bounces a ball to rest and asserts 3 to 30 contacts, not thousands.
- **Contacts carry their own time and position**, because the frame that shows them may be a
  later moment.

## 3. The bounce: impulse with spin–friction coupling

Hollow sphere, `I = ⅔mr²`. Per unit mass:

```
J_n = (1 + e)·v_n                                   e = 0.78 − 0.0035·(v_n − 10), clamped to [0.70, 0.80]
u   = v + ω × r_c          (contact-point velocity, r_c = −r·n)
J_t = min(|u_t| / (1 + r²/(I/m)),  μ·J_n)          1 + r²/(I/m) = 2.5 for a hollow sphere; μ = 0.55
v  += J_n·n − J_t·û_t ;   ω += r_c × (−J_t·û_t) / (I/m)
```

The first term in the `min` brings the contact point to pure rolling (the ball "bites"); the
friction cap makes it slide instead. Topspin leaves the bounce faster and lower, backspin checks.
Tests: topspin > flat > backspin in forward speed after a bounce; **10 000 random contacts never
increase kinetic plus rotational energy**.

Other surfaces are a restitution and a friction each (fence 0.25 / 0.6, wood 0.5 / 0.4, concrete
0.65 / 0.5); foliage is a soft volume that damps instead of bouncing.

## 4. The net: a curve, a body and a cord

- **Height is a curve**, not a constant: 0.914 m at the centre, 1.07 m at the posts, parabolic
  between. The prior prototype used a flat 1.045 m.
- **Body** below the cord: a vertical plane that absorbs (normal velocity × 0.1, tangential × 0.3);
  the ball drops on the striker's side.
- **Cord** along the top: a 0.03 m capsule, restitution 0.35, friction 0.4. Rolling over or falling
  back is decided by the physics, deterministically, and a cord contact raises an event (a serve
  that clips the cord and lands in is a let).

## 5. Venue geometry is data, and its hash is in the replay

Venue shapes (boxes, capsules, soft volumes) are authored as simple objects in a `COLLISION`
collection of the venue's `.blend`, with custom properties for type, material and radius, and
exported to JSON in simulation coordinates rounded to 0.1 mm so the file, and its hash, are
byte-stable. The hash goes into every replay header next to the balance hash. The export, the
handedness trap between Blender and the game, and the venue tests (nothing inside the play area,
the enclosure closed when sampled all the way round, a ball fired at the back wall comes back):
`unity-3d-level` → `reference/venue-from-scripts.md`.

## 6. Aiming: a shooting-method solver

A shot is specified by what it must do (land at a target, clear the net by a margin, peak at a
height), and the solver finds the launch velocity that does it under drag and Magnus.

- **Unknowns are the initial velocity components**, not angles; Newton's method with a
  finite-difference Jacobian, at most 10 iterations, converged at 2 cm landing error.
- Fixed per shot kind: drives fix speed (from timing quality) and solve direction; a lob fixes an
  apex of 5–7 m and solves speed and direction; a drop fixes a landing 1.5–3 m past the net.
- Net clearance at the crossing ≥ the net height at that x + radius + margin (0.25 m drives,
  0.10 m drops); short of it, raise the target and solve again.
- **Gate:** 10 000 random launches (anywhere behind the baseline, any target in the far court, a
  range of clearances and spins) converge **≥ 99.5%**, every converged landing within 2 cm, every
  crossing above the cord. A request that needs more than 60 m/s is physically impossible, not a
  solver failure, and must stay ≤ 3% (the caller backs off). The 10 000 run takes about a minute
  and is explicit; a 1 000 version runs on every change. A typical drive solves in a median under
  3 ms on a desktop (budget for 2–3× slower on a phone).

## 7. Faults come out of the physics

Timing quality sets a scatter σ (and an early or late bias in direction); the scatter is added to
the **target**, and the solver flies a real shot at the scattered target. Nets, outs and short
balls then happen because the ball really did that. Nothing is scripted to go out.

## 8. After the point: a dead ball for the eyes only

When a point ends, keep integrating up to 3 s or until the ball stops (rolling resistance 0.3/s,
bouncing off the fence) on a separate path the score never reads. The ball does not vanish, and
the rules cannot be changed by it.

## Traps

| Symptom | Cause | Fix |
|---|---|---|
| The ball passes through a thin fence at serve speed | Substep longer than the overlap stretch | Substeps so one step < a diameter at the clamp speed; assert it with a plate test |
| The predicted landing is centimetres off the real one | Prediction stepped differently, or the contact state was lerped | One function, one step size for both; re-integrate to the contact time |
| A rolling ball fires a bounce event every substep | No resting threshold | Normal speed below 0.25 m/s: e = 0, no event |
| Topspin and backspin bounce the same | Friction applied to velocity only | Apply the tangential impulse to spin as well (§3) |
| Replays diverge after a tuning change | Tuning not in the header | Hash balance, venue and geometry into every replay |
| Results differ between the Editor and a test runner by 1e-12 | Different runtime maths | Compare event logs exactly and state within 1e-6 m; bit-identical only within a build |

## Scope

The ball's own simulation. A ball that is a `Rigidbody` and passes through things is §2 of
`SKILL.md`. The thread and clock this runs on: `unity-gameplay` → `reference/sim-host-and-clock.md`.
Which shot a press produces: `unity-input` → `reference/timing-press.md`.
