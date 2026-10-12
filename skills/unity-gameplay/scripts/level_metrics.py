#!/usr/bin/env python3
"""level_metrics.py — turn controller numbers into the reach table a level is built against.

Give any TWO of --gravity, --jump-velocity, --apex, --time-to-apex (the other two are derived)
plus --run-speed. Prints ONE JSON object: the derived jump, a reach table (how far the jump
carries to a landing N level units higher or lower), the clearances that follow from the body
size, and a verdict for every level number supplied with --gap, --height, --step, --door or
--ceiling. The formulas are in `reference/level-metrics.md`.

Lengths are world units, times are seconds, gravity is a positive magnitude in units/s².

Exit codes: 0 every supplied level number is inside reach · 1 at least one is outside reach
(or only "tight", with --strict) · 2 usage error or numbers that describe no jump.

Examples:
  level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 --fall-multiplier 1.5
  level_metrics.py --gravity 37.5 --jump-velocity 15 --run-speed 8 --gap 5 --height 2
  level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 --step 0.5 --step-offset 0.3
  level_metrics.py --apex 1.2 --time-to-apex 0.35 --run-speed 5 --body-width 0.8 \\
      --body-height 1.8 --door 1.0 --ceiling 2.6 --indent 2
"""
import argparse
import json
import math
import sys

FAILING = ("unreachable", "blocks-walking", "too-narrow")


def derive(gravity, velocity, apex, time_to_apex):
    """Fill in the two missing jump numbers. Raises ValueError unless exactly two are given."""
    given = [v is not None for v in (gravity, velocity, apex, time_to_apex)]
    if sum(given) != 2:
        raise ValueError("give exactly two of --gravity, --jump-velocity, --apex, "
                         "--time-to-apex (got %d)" % sum(given))
    for name, value in (("--gravity", gravity), ("--jump-velocity", velocity),
                        ("--apex", apex), ("--time-to-apex", time_to_apex)):
        if value is not None and value <= 0:
            raise ValueError("%s must be greater than zero, got %g" % (name, value))

    if gravity is not None and velocity is not None:
        pass
    elif apex is not None and time_to_apex is not None:
        gravity = 2.0 * apex / (time_to_apex * time_to_apex)
        velocity = 2.0 * apex / time_to_apex
    elif gravity is not None and apex is not None:
        velocity = math.sqrt(2.0 * gravity * apex)
    elif gravity is not None and time_to_apex is not None:
        velocity = gravity * time_to_apex
    elif velocity is not None and apex is not None:
        gravity = velocity * velocity / (2.0 * apex)
    else:
        gravity = velocity / time_to_apex
    return gravity, velocity, velocity * velocity / (2.0 * gravity), velocity / gravity


def fall_time(drop, fall_gravity, max_fall_speed):
    """Seconds to fall `drop` units from rest, with an optional terminal speed."""
    if drop <= 0:
        return 0.0
    if max_fall_speed:
        to_terminal = max_fall_speed * max_fall_speed / (2.0 * fall_gravity)
        if drop > to_terminal:
            return max_fall_speed / fall_gravity + (drop - to_terminal) / max_fall_speed
    return math.sqrt(2.0 * drop / fall_gravity)


def classify(value, reach, margin):
    if value > reach + 1e-9:
        return "unreachable"
    if value > reach * margin + 1e-9:
        return "tight"
    return "ok"


def r(x):
    return round(x, 3)


def compute(args):
    gravity, velocity, apex_exact, t_up = derive(args.gravity, args.jump_velocity, args.apex,
                                                 args.time_to_apex)
    if args.run_speed <= 0:
        raise ValueError("--run-speed must be greater than zero")
    if args.fall_multiplier <= 0:
        raise ValueError("--fall-multiplier must be greater than zero")
    if not 0 < args.margin <= 1:
        raise ValueError("--margin is a fraction of reach, in (0, 1]")
    if args.unit <= 0:
        raise ValueError("--unit must be greater than zero")

    # A fixed-step integrator does not land on the analytic apex. Velocity-then-position
    # (what the built-in bodies do) falls short by v0·dt/2; position-then-velocity overshoots
    # by the same amount.
    correction = {"semi-implicit": -0.5, "explicit": 0.5, "exact": 0.0}[args.integrator]
    apex = apex_exact + correction * velocity * args.fixed_dt
    if apex <= 0:
        raise ValueError("the jump has no height at this fixed step: v0=%g dt=%g"
                         % (velocity, args.fixed_dt))
    fall_gravity = gravity * args.fall_multiplier

    def air_time(rise):
        return t_up + fall_time(apex - rise, fall_gravity, args.max_fall_speed)

    def distance(rise):
        return args.run_speed * (air_time(rise) + args.coyote)

    flat_air = air_time(0.0)
    derived = {
        "gravity": r(gravity), "jump_velocity": r(velocity),
        "apex": r(apex), "apex_analytic": r(apex_exact),
        "time_to_apex": r(t_up), "fall_gravity": r(fall_gravity),
        "air_time_flat": r(flat_air),
        "jump_distance_flat": r(distance(0.0)),
        "landing_speed_flat": r(min(fall_gravity * (flat_air - t_up),
                                    args.max_fall_speed or float("inf"))),
    }

    # The reach table: one row per level unit of rise, from a three-unit drop up to the
    # highest whole unit the jump can land on.
    reach = []
    highest = int(math.floor(apex / args.unit + 1e-9))
    for steps in range(-3, highest + 1):
        rise = steps * args.unit
        d = distance(rise)
        reach.append({"rise": r(rise), "air_time": r(air_time(rise)), "max_gap": r(d),
                      "usable_gap": r(d * args.margin)})

    checks = []

    def add(name, value, limit, verdict, note):
        checks.append({"check": name, "value": r(value), "limit": r(limit),
                       "usable": r(limit * args.margin), "verdict": verdict, "note": note})

    rise = args.height if args.height is not None else 0.0
    if args.height is not None:
        if args.height >= 0:
            add("height", args.height, apex, classify(args.height, apex, args.margin),
                "a ledge this far above the take-off point, against the apex")
        else:
            add("height", args.height, apex, "ok", "a drop: always reachable; read max_gap")
    if args.gap is not None:
        if rise > apex + 1e-9:
            add("gap", args.gap, 0.0, "unreachable",
                "the landing is above the apex, so no gap is crossable")
        else:
            limit = distance(rise)
            add("gap", args.gap, limit, classify(args.gap, limit, args.margin),
                "horizontal distance to a landing %g above take-off" % rise)
    if args.step is not None:
        if args.step_offset is not None:
            verdict = "ok" if args.step <= args.step_offset + 1e-9 else "blocks-walking"
            checks.append({"check": "step", "value": r(args.step), "limit": r(args.step_offset),
                           "usable": r(args.step_offset), "verdict": verdict,
                           "note": "a step is walked over, so it is held to the step offset, "
                                   "not to the jump"})
        else:
            verdict = classify(args.step, apex, args.margin)
            add("step", args.step, apex, verdict,
                "no --step-offset given: this is a ledge that needs a jump, checked against "
                "the apex")

    clearance = {}
    if args.body_width is not None:
        clearance["door_min"] = r(args.body_width * 1.5)
        clearance["corridor_min"] = r(args.body_width * 2.0)
        clearance["landing_min"] = r(args.body_width * 2.0)
    if args.body_height is not None:
        clearance["ceiling_walk_min"] = r(args.body_height * 1.1)
        clearance["ceiling_full_jump"] = r(args.body_height + apex)
    if args.door is not None:
        if args.body_width is None:
            raise ValueError("--door needs --body-width to be checked against")
        if args.door < args.body_width - 1e-9:
            verdict = "too-narrow"
        elif args.door < args.body_width * 1.5 - 1e-9:
            verdict = "tight"
        else:
            verdict = "ok"
        checks.append({"check": "door", "value": r(args.door), "limit": r(args.body_width),
                       "usable": clearance["door_min"], "verdict": verdict,
                       "note": "opening width against the collider width; usable is 1.5 x"})
    if args.ceiling is not None:
        if args.body_height is None:
            raise ValueError("--ceiling needs --body-height to be checked against")
        if args.ceiling < args.body_height - 1e-9:
            verdict = "too-narrow"
        elif args.ceiling < args.body_height + apex - 1e-9:
            verdict = "clips-jump"
        else:
            verdict = "ok"
        checks.append({"check": "ceiling", "value": r(args.ceiling), "limit": r(args.body_height),
                       "usable": clearance["ceiling_full_jump"], "verdict": verdict,
                       "note": "below body height + apex the head stops the jump early, which "
                               "shortens every gap under this ceiling"})

    verdicts = [c["verdict"] for c in checks]
    if any(v in FAILING for v in verdicts):
        overall = "fail"
    elif "tight" in verdicts:
        overall = "tight"
    else:
        overall = "ok"

    return {
        "inputs": {"run_speed": args.run_speed, "fall_multiplier": args.fall_multiplier,
                   "max_fall_speed": args.max_fall_speed, "coyote": args.coyote,
                   "fixed_dt": args.fixed_dt, "integrator": args.integrator,
                   "margin": args.margin, "unit": args.unit},
        "derived": derived,
        "reach": reach,
        "clearance": clearance,
        "checks": checks,
        "verdict": overall,
    }


def build_parser():
    p = argparse.ArgumentParser(
        prog="level_metrics.py",
        description="Derive jump reach from controller numbers and check level numbers "
                    "against it.",
        epilog="Exit 0 inside reach, 1 a level number is outside reach, 2 usage error.",
    )
    jump = p.add_argument_group("the jump (give exactly two)")
    jump.add_argument("--gravity", type=float, metavar="G",
                      help="rising gravity, a positive magnitude in units/s^2")
    jump.add_argument("--jump-velocity", type=float, metavar="V0",
                      help="upward speed on the take-off step, units/s")
    jump.add_argument("--apex", type=float, metavar="H", help="designed apex height, units")
    jump.add_argument("--time-to-apex", type=float, metavar="T",
                      help="designed time from take-off to apex, seconds")

    move = p.add_argument_group("the controller")
    move.add_argument("--run-speed", type=float, required=True, metavar="S",
                      help="horizontal speed held through the jump, units/s")
    move.add_argument("--fall-multiplier", type=float, default=1.0, metavar="M",
                      help="gravity multiplier once past the apex (default 1)")
    move.add_argument("--max-fall-speed", type=float, default=None, metavar="S",
                      help="terminal fall speed, units/s (default: none)")
    move.add_argument("--coyote", type=float, default=0.0, metavar="SECONDS",
                      help="coyote time; adds run-speed x coyote to every gap (default 0)")
    move.add_argument("--step-offset", type=float, default=None, metavar="H",
                      help="the tallest step walked over without a jump")
    move.add_argument("--body-width", type=float, default=None, metavar="W",
                      help="collider width (2 x radius for a capsule)")
    move.add_argument("--body-height", type=float, default=None, metavar="H",
                      help="collider height")
    move.add_argument("--fixed-dt", type=float, default=0.02, metavar="SECONDS",
                      help="the fixed timestep the motor integrates at (default 0.02)")
    move.add_argument("--integrator", choices=("semi-implicit", "explicit", "exact"),
                      default="semi-implicit",
                      help="semi-implicit: velocity then position, the built-in bodies "
                           "(default); explicit: position then velocity; exact: no correction")

    level = p.add_argument_group("level numbers to check")
    level.add_argument("--gap", type=float, default=None, metavar="D",
                       help="horizontal gap; with --height, a gap to a landing that much higher")
    level.add_argument("--height", type=float, default=None, metavar="H",
                       help="ledge height above take-off; negative for a drop")
    level.add_argument("--step", type=float, default=None, metavar="H",
                       help="a step height, held to --step-offset")
    level.add_argument("--door", type=float, default=None, metavar="W",
                       help="an opening width, held to --body-width")
    level.add_argument("--ceiling", type=float, default=None, metavar="H",
                       help="a ceiling height, held to --body-height and the apex")

    p.add_argument("--margin", type=float, default=0.9, metavar="FRACTION",
                   help="the fraction of reach a level may use before it reads as tight "
                        "(default 0.9)")
    p.add_argument("--unit", type=float, default=1.0, metavar="U",
                   help="the level unit the reach table steps by: a tile, a kit module "
                        "(default 1)")
    p.add_argument("--strict", action="store_true", help="exit 1 on a tight verdict too")
    p.add_argument("--indent", type=int, default=None, metavar="N",
                   help="pretty-print with this indent (default: one line)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = compute(args)
    except ValueError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 2
    if args.indent is None:
        print(json.dumps(result, separators=(",", ":")))
    else:
        print(json.dumps(result, indent=args.indent))
    if result["verdict"] == "fail":
        return 1
    if result["verdict"] == "tight" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
