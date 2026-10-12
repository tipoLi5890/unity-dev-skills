#!/usr/bin/env python3
"""level_validate.py — hold a level file to its invariants: every pickup and the gate are reachable.

Reads the level JSON described in `reference/level-data.md` and searches it from the spawn cell.
A side-view level is searched over standable cells joined by walks, drops and jumps; a top-down
level is flood-filled over floor cells. The jump comes from three numbers — apex height, flat
jump distance, fall multiplier — given as flags or read from the JSON that unity-gameplay's
level_metrics.py prints. The rule is written out in `reference/procedural.md`.

Prints ONE JSON object: the rule in cells, how many cells were reached, a verdict for the gate
and for each pickup, and a list of violations. Lengths on the command line are world units.

Exit codes: 0 the level holds every invariant · 1 at least one violation (an unreachable pickup
or gate, a spawn with no floor, a malformed layer) · 2 usage error, unreadable file, or a file
that is not a level in this format.

Examples:
  level_validate.py templates/sample-level.json --jump-height 2.85 --jump-distance 5.17 \\
      --fall-multiplier 1.5
  level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 --fall-multiplier 1.5 > metrics.json
  level_validate.py Assets/Levels/side-run-01.json --metrics metrics.json --indent 2
  level_validate.py Assets/Levels/depot-01.json          # "view": "topdown" needs no jump
"""
import argparse
import json
import math
import sys

FORMAT = "courier-level"
VERSION = 1
SOLID_LAYERS = ("Ground", "Walls")      # side view: both stop the runner
EPS = 1e-6
HOP = 0.15                              # the smallest hop tried, in cells


class LevelError(Exception):
    """The file is not a level this script can read (exit 2)."""


# ------------------------------------------------------------------ the level


class Level:
    def __init__(self, data):
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise LevelError('not a level file: "format" is not "%s"' % FORMAT)
        if data.get("version") != VERSION:
            raise LevelError("level version %r; this script reads version %d"
                             % (data.get("version"), VERSION))
        self.id = str(data.get("id") or "")
        self.view = data.get("view") or "side"
        if self.view not in ("side", "topdown"):
            raise LevelError('view "%s": only "side" and "topdown" are searched here; a cell '
                             'board is checked by a search over board states' % self.view)
        try:
            self.w, self.h = int(data["width"]), int(data["height"])
            self.cell = float(data.get("cellSize") or 1.0)
        except (KeyError, TypeError, ValueError):
            raise LevelError('"width", "height" and "cellSize" must be numbers')
        if self.w <= 0 or self.h <= 0 or self.cell <= 0:
            raise LevelError("width, height and cellSize must be greater than zero")

        self.violations = []
        known = {t.get("id") for t in data.get("tiles") or [] if isinstance(t, dict)}
        self.layers = {}
        for layer in data.get("layers") or []:
            name, cells = layer.get("name"), layer.get("cells") or []
            if len(cells) != self.w * self.h:
                self.violate("layer-size", name, None, "layer '%s' has %d cells, expected %d x %d = %d"
                             % (name, len(cells), self.w, self.h, self.w * self.h))
                continue
            unknown = sorted({c for c in cells if c != 0 and c not in known})
            if unknown:
                self.violate("unknown-tile-id", name, None,
                             "layer '%s' uses tile ids missing from \"tiles\": %s"
                             % (name, unknown[:8]))
            self.layers[name] = cells

        self.spawn = self.cell_of(data.get("spawn"), "spawn")
        self.gate = self.cell_of(data.get("gate"), "gate")
        self.pickups = list(data.get("pickups") or [])
        self.entities = list(data.get("entities") or [])
        seen = set()
        for e in self.pickups + self.entities:
            if e.get("id") in seen:
                self.violate("duplicate-id", e.get("id"), None, "two entities share this id")
            seen.add(e.get("id"))
            x, y = int(e.get("x", 0)), int(e.get("y", 0))
            if not (0 <= x < self.w and 0 <= y < self.h):
                self.violate("out-of-bounds", e.get("id"), [x, y], "entity is outside the level")

        self.hazards = set()
        self.launch = {}
        for e in self.entities:
            x, y = int(e.get("x", 0)), int(e.get("y", 0))
            if e.get("type") == "hazard":
                for dx in range(max(1, int(e.get("w") or 1))):
                    for dy in range(max(1, int(e.get("h") or 1))):
                        self.hazards.add((x + dx, y + dy))
            elif e.get("type") == "launch":
                apex = field(e, "apex")
                try:
                    self.launch[(x, y)] = float(apex) / self.cell
                except (TypeError, ValueError):
                    self.violate("bad-field", e.get("id"), [x, y],
                                 'a launch needs a numeric "apex" field, in world units')

    def violate(self, rule, ident, cell, detail):
        self.violations.append({"rule": rule, "id": ident, "cell": cell, "detail": detail})

    def cell_of(self, value, what):
        if not isinstance(value, dict) or "x" not in value or "y" not in value:
            raise LevelError('"%s" must be an object with x and y' % what)
        x, y = int(value["x"]), int(value["y"])
        if not (0 <= x < self.w and 0 <= y < self.h):
            self.violate("out-of-bounds", what, [x, y], "%s is outside the level" % what)
        return (x, y)

    def tile(self, layer, x, y):
        cells = self.layers.get(layer)
        if cells is None or not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        return cells[x + y * self.w]


def field(entity, key):
    for f in entity.get("fields") or []:
        if f.get("key") == key:
            return f.get("value")
    return None


# ------------------------------------------------------------------ side view


class SideSearch:
    """Standable cells joined by walks, drops and jumps. Positions are in cells."""

    def __init__(self, level, apex, distance, fall_multiplier, step, body_w, body_h):
        self.lv = level
        self.apex, self.dist, self.m = apex, distance, fall_multiplier
        self.step = int(math.floor(step + EPS))
        self.bw, self.bh = body_w, body_h
        self.body_cells = max(1, int(math.ceil(body_h - EPS)))
        # Horizontal speed in cells per unit of normalised time, in which rising gravity is 1:
        # a jump of apex h rises for sqrt(h) and falls d cells in sqrt(d / m).
        self.speed = distance / (math.sqrt(apex) * (1.0 + 1.0 / math.sqrt(fall_multiplier)))
        self._blocked = {}

    # -- cells

    def solid(self, x, y):
        if x < 0 or x >= self.lv.w:
            return True                              # the level's side edges are walls
        return any(self.lv.tile(n, x, y) for n in SOLID_LAYERS)

    def one_way(self, x, y):
        return bool(self.lv.tile("OneWay", x, y)) and not self.solid(x, y)

    def lethal(self, x, y):
        return (x, y) in self.lv.hazards

    def supports(self, x, y):
        return self.solid(x, y) or self.one_way(x, y)

    def standable(self, x, y):
        if not (0 <= x < self.lv.w and 0 <= y < self.lv.h) or not self.supports(x, y - 1):
            return False
        return all(not self.solid(x, y + k) and not self.lethal(x, y + k)
                   for k in range(self.body_cells))

    # -- the body as a set of intervals of its centre x

    def blocked(self, r0, r1):
        """Open spans of centre x in which the body, covering rows r0..r1, touches something."""
        key = (r0, r1)
        if key not in self._blocked:
            half = self.bw / 2.0
            spans = [(-math.inf, half)]
            for x in range(self.lv.w):
                if any(self.solid(x, r) or self.lethal(x, r) for r in range(r0, r1 + 1)):
                    if spans[-1][1] >= x - half:     # touching spans merge into one
                        spans[-1] = (spans[-1][0], x + 1 + half)
                    else:
                        spans.append((x - half, x + 1 + half))
            if spans[-1][1] >= self.lv.w - half:
                spans[-1] = (spans[-1][0], math.inf)
            else:
                spans.append((self.lv.w - half, math.inf))
            self._blocked[key] = spans
        return self._blocked[key]

    @staticmethod
    def subtract(intervals, spans):
        for lo, hi in spans:
            kept = []
            for a, b in intervals:
                if b <= lo or a >= hi:
                    kept.append((a, b))
                    continue
                if a <= lo:
                    kept.append((a, lo))
                if b >= hi:
                    kept.append((hi, b))
            intervals = kept
            if not intervals:
                break
        return intervals

    def fly(self, x, y, h, falling_from_here=False):
        """Leave cell (x, y) on an arc of apex h; return the standable cells it can land on.

        The arc's height is fixed by h; the horizontal position is anything the runner can
        steer to at run speed, kept as intervals of the body's centre. With falling_from_here
        the feet start at the bottom of (x, y) with no floor: a walk off an edge, or a drop
        through a one-way platform.
        """
        m, rise = self.m, math.sqrt(h)
        # Events: every quarter cell of height on the way up, the apex, every quarter cell
        # on the way down. A whole cell on the way down is a row the feet can land on.
        events = [(rise - math.sqrt(h - k / 4.0), k / 4.0, False)
                  for k in range(1, int(math.floor(h * 4.0 + EPS)) + 1) if k / 4.0 < h - EPS]
        if h > 0:
            events.append((rise, h, False))
        k = -1 if falling_from_here else int(math.floor(h * 4.0 + EPS))
        while k / 4.0 >= -(y + self.bh + 1.0):
            z = k / 4.0
            if z < h - EPS or falling_from_here:
                events.append((rise + math.sqrt((h - z) / m), z, k % 4 == 0))
            k -= 1

        half = self.bw / 2.0
        where = self.subtract([(float(x), float(x + 1))],
                              self.blocked(y, y + self.body_cells - 1))
        landed, t_prev, z_prev = set(), 0.0, 0.0
        for t, z, lands in events:
            if not where:
                break
            r0 = int(math.floor(y + min(z, z_prev) + EPS))
            r1 = int(math.floor(y + max(z, z_prev) + self.bh - EPS))
            spans = self.blocked(max(r0, 0), r1)
            reach = self.speed * (t - t_prev)
            where = self.subtract(where, spans)
            where = self.subtract([(a - reach, b + reach) for a, b in where], spans)
            if lands:
                row = int(round(y + z))              # the feet arrive at the top of row - 1
                under = []
                for a, b in where:
                    for c in range(int(math.ceil(a - EPS)) - 1, int(math.floor(b + EPS)) + 1):
                        if self.supports(c, row - 1):
                            under.append((c - half, c + 1 + half))
                            if self.standable(c, row):
                                landed.add((c, row))
                where = self.subtract(where, under)
            t_prev, z_prev = t, z
        landed.discard((x, y))
        return landed

    def moves(self, x, y):
        out = set()
        for d in (-1, 1):
            nx = x + d
            for up in range(0, self.step + 1):       # a walked step, never taller than --step
                clear = all(not self.solid(x, y + self.body_cells + k) for k in range(up))
                if clear and self.standable(nx, y + up):
                    out.add((nx, y + up))
                    break
            if not self.supports(nx, y - 1) and all(
                    not self.solid(nx, y + k) and not self.lethal(nx, y + k)
                    for k in range(self.body_cells)):
                out |= self.fly(nx, y, 0.0, True)    # walking off the edge
        if self.one_way(x, y - 1):
            out |= self.fly(x, y, 0.0, True)         # dropping through the platform
        h = self.apex
        while h > HOP:                               # the full jump and every shorter hop
            out |= self.fly(x, y, h)
            h -= 0.5
        out |= self.fly(x, y, HOP)                   # the hop that fits under a low ceiling
        if (x, y) in self.lv.launch:
            out |= self.fly(x, y, self.lv.launch[(x, y)])
        return out

    def search(self, start):
        seen, queue = {start}, [start]
        while queue:
            cell = queue.pop()
            for nxt in self.moves(*cell):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def touches(self, seen, x, y, jump):
        """Can the body overlap cell (x, y) from a reached cell in the same column?"""
        span = self.body_cells - 1 + (int(math.floor(self.apex + EPS)) if jump else 0)
        for below in range(0, span + 1):
            yy = y - below
            if self.solid(x, yy):
                return False
            if (x, yy) in seen:
                return True
        return False


# ------------------------------------------------------------------ top-down view


def flood(level):
    def walkable(x, y):
        return (level.tile("Ground", x, y) != 0 and level.tile("Walls", x, y) == 0
                and (x, y) not in level.hazards)
    seen, queue = set(), []
    if walkable(*level.spawn):
        seen.add(level.spawn)
        queue.append(level.spawn)
    while queue:
        x, y = queue.pop()
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nxt not in seen and walkable(*nxt):
                seen.add(nxt)
                queue.append(nxt)
    return seen, sum(walkable(x, y) for y in range(level.h) for x in range(level.w))


# ------------------------------------------------------------------ the check


def jump_numbers(args, cell):
    """Apex, flat distance (both in cells) and fall multiplier, from flags or a metrics file."""
    if args.metrics:
        try:
            with open(args.metrics, encoding="utf-8") as f:
                metrics = json.load(f)
            apex = float(metrics["derived"]["apex"])
            distance = float(metrics["derived"]["jump_distance_flat"])
            fall = float(metrics["inputs"]["fall_multiplier"])
            margin = 1.0 if args.full_reach else float(metrics["inputs"].get("margin", 1.0))
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise LevelError("cannot read jump numbers from %s: %s" % (args.metrics, e))
        distance *= margin
    else:
        if args.jump_height is None or args.jump_distance is None:
            raise LevelError("a side-view level needs --metrics FILE, or both --jump-height "
                             "and --jump-distance")
        apex, distance, fall = args.jump_height, args.jump_distance, args.fall_multiplier
    if apex <= 0 or distance <= 0 or fall <= 0:
        raise LevelError("jump height, jump distance and fall multiplier must be greater than zero")
    return apex / cell, distance / cell, fall


def validate(level, args):
    result = {"level": level.id, "view": level.view, "size": [level.w, level.h]}
    if any(v["rule"] in ("layer-size", "out-of-bounds") for v in level.violations):
        result.update({"violations": level.violations, "verdict": "fail"})
        return result                                # nothing sound to search

    if level.view == "side":
        apex, distance, fall = jump_numbers(args, level.cell)
        search = SideSearch(level, apex, distance, fall, args.step / level.cell,
                            args.body_width / level.cell, args.body_height / level.cell)
        result["rule"] = {"unit": "cells", "jump_height": round(apex, 3),
                          "jump_distance": round(distance, 3), "fall_multiplier": fall,
                          "step": search.step, "body": [round(search.bw, 3), round(search.bh, 3)]}
        total = sum(search.standable(x, y) for y in range(level.h) for x in range(level.w))
        if search.standable(*level.spawn):
            seen = search.search(level.spawn)
        else:
            seen = set()
            level.violate("spawn-not-standable", "spawn", list(level.spawn),
                          "the spawn cell has no floor under it, or the body does not fit")
        gate_ok = search.touches(seen, level.gate[0], level.gate[1], False)

        def pickup_ok(x, y):
            return search.touches(seen, x, y, True)
    else:
        seen, total = flood(level)
        if not seen:
            level.violate("spawn-not-standable", "spawn", list(level.spawn),
                          "the spawn cell is not floor: Ground is empty there, or Walls is not")
        gate_ok = level.gate in seen

        def pickup_ok(x, y):
            return (x, y) in seen

    result["standable"], result["reached"] = total, len(seen)
    if seen:
        result["reached_bounds"] = {"min": [min(c[0] for c in seen), min(c[1] for c in seen)],
                                    "max": [max(c[0] for c in seen), max(c[1] for c in seen)]}
    result["gate"] = {"cell": list(level.gate), "reachable": gate_ok}
    if not gate_ok:
        level.violate("gate-unreachable", "gate", list(level.gate),
                      "no reached cell lets the runner stand in the gate")
    result["pickups"] = []
    for p in level.pickups:
        x, y = int(p.get("x", 0)), int(p.get("y", 0))
        ok = pickup_ok(x, y)
        result["pickups"].append({"id": p.get("id"), "cell": [x, y], "reachable": ok})
        if not ok:
            level.violate("pickup-unreachable", p.get("id"), [x, y],
                          "no reached cell lets the runner touch this pickup")
    result["violations"] = level.violations
    result["verdict"] = "fail" if level.violations else "ok"
    return result


def build_parser():
    p = argparse.ArgumentParser(
        prog="level_validate.py",
        description="Search a level file from its spawn and report unreachable pickups and gate.",
        epilog="Exit 0 every invariant holds, 1 a violation, 2 usage or file error.",
    )
    p.add_argument("level", help="the level JSON (reference/level-data.md)")
    jump = p.add_argument_group("the jump, for a side-view level (world units)")
    jump.add_argument("--metrics", metavar="FILE",
                      help="JSON printed by unity-gameplay's level_metrics.py: apex, flat jump "
                           "distance times its margin, fall multiplier")
    jump.add_argument("--full-reach", action="store_true",
                      help="with --metrics, use 100%% of reach instead of the usable margin")
    jump.add_argument("--jump-height", type=float, metavar="H",
                      help="apex height the runner's feet reach, on the fixed step")
    jump.add_argument("--jump-distance", type=float, metavar="D",
                      help="widest gap crossed on level ground")
    jump.add_argument("--fall-multiplier", type=float, default=1.0, metavar="M",
                      help="gravity multiplier past the apex (default 1)")
    body = p.add_argument_group("the body (world units)")
    body.add_argument("--step", type=float, default=0.0, metavar="H",
                      help="tallest step walked up without a jump (default 0)")
    body.add_argument("--body-width", type=float, default=0.8, metavar="W",
                      help="collider width (default 0.8)")
    body.add_argument("--body-height", type=float, default=1.8, metavar="H",
                      help="collider height (default 1.8)")
    p.add_argument("--indent", type=int, default=None, metavar="N",
                   help="pretty-print with this indent (default: one line)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        with open(args.level, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print("ERROR cannot read %s: %s" % (args.level, e), file=sys.stderr)
        return 2
    try:
        if args.body_width <= 0 or args.body_height <= 0 or args.step < 0:
            raise LevelError("--body-width and --body-height must be greater than zero, "
                             "--step zero or more")
        result = validate(Level(data), args)
    except LevelError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 2
    if args.indent is None:
        print(json.dumps(result, separators=(",", ":")))
    else:
        print(json.dumps(result, indent=args.indent))
    return 1 if result["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
