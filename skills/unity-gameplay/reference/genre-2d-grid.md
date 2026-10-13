# 2D by the cell — tactics, tile puzzle, isometric and hexagonal boards

> Part of the `unity-gameplay` skill. Types where position is a cell index and time is a move or
> a turn. Worked setting: the **sorting yard** — the runner steps cell to cell and pushes pickups
> onto gate cells, on a rectangular, isometric or hexagonal board.

## The constraints

| Constraint | Tile puzzle | Tactics | The same on isometric or hexagonal cells |
|---|---|---|---|
| View · projection | Top-down · orthographic | Top-down or isometric · orthographic | Isometric is a drawing convention; hexagonal is a neighbour rule. Neither changes the rules engine |
| Movement model | One cell per input | A path of cells per action, limited by a range | Unchanged |
| Transform owner | **The board.** The transform is tweened to where the board already says the piece is | The same | The same |
| Time | A move; fully undoable | A turn made of actions; an order of actors | Unchanged |
| Camera | Fixed if the board fits; otherwise pans inside bounds | Pans and zooms inside bounds; recentres on the acting unit | Bounds are a diamond or a staggered rectangle in world space |
| Level unit | Cell | Cell, with height or terrain cost per cell | Cell |
| Level is | A board state plus a goal; must be solvable | A board plus spawn cells; must be connected | — |

Underneath all of them: **the board is the fact and the scene is its animation.** Every rule is
evaluated on cell coordinates, instantly; nothing in the rules waits for a tween, reads a
`transform.position`, or asks a collider. This is the simulation/presentation split in its purest
form — `unity-game-brief` → `reference/sim-presentation-split.md` — and it is what makes undo,
solvers and EditMode tests free.

## Numbers to decide first

| Number | Sorting-yard start | Decides |
|---|---|---|
| Cell layout · cell size | Rectangle `(1, 1)` · isometric `(1, 0.5)` · hexagon point-top `(0.866, 1)` | Art dimensions; set once, in the `Grid` |
| Board size | 9 × 7 cells — fits a 16:9 screen at orthographic size 4 with a HUD margin | Whether the camera ever moves |
| Step tween | 0.12 s per cell, eased out | Feel; input arriving during a tween is buffered one deep |
| Hold-to-repeat | first repeat after 0.25 s, then every 0.12 s | Whether crossing the board is one hold or nine presses |
| Neighbour rule | 4 (rectangle), 6 (hexagon); 8 only if diagonals cost the same or you price them | Range shapes, heuristics, line of sight |
| Tactics: move range · turn order | 4 cells · fixed order by initiative | Board size relative to range: about 3 × range across |
| Undo depth | Unlimited within a level | Memory is trivial: a move is two cells and a flag |

## Build order for the 3C prototype

1. **The board, with no scene.** A plain C# class holding walls, gates, pickups and the runner as
   cells, with `Step(direction)` returning what changed. Test it in EditMode before a single
   sprite exists. Cell types, neighbours and occupancy come from `unity-2d-grid`, below.
2. **The grid in the scene.** One `Grid` with the chosen layout; a floor Tilemap and a wall
   Tilemap — `unity-tilemap`. Load the board *from* the Tilemaps once at start, or load both from
   one data file — `unity-2d-level` → `reference/level-data.md`; never let them be edited
   independently.
3. **Controls.** A struct with one `step` direction per press and `undo` — `unity-input`. For a
   pointer: `unity-2d-grid` → `reference/picking.md`.
4. **Presentation.** On each successful move, tween the affected transforms to the cell centre —
   `unity-2d-controller` → `reference/grid-step.md`. Register the *logical* state with the probe:
   `GameProbe.Register("cell", () => { var c = _board.Cells.CellOf(YardBoard.RunnerId); return $"{c.x},{c.y}"; });` and
   `GameProbe.Count("pickupsOnGates", () => _board.PickupsOnGates);`
5. **Journey 1 — the step.** Enter the yard-step situation, feed a scripted move list, and
   assert after each tween settles that the transform is at the centre of the cell the probe
   reports, and that a move into a wall changed neither.
6. **Camera.** Fixed, or panning inside bounds — `unity-camera` → `reference/follow-2d.md`.
7. **Journey 2 — solve it.** Feed the known solution; assert `pickupsOnGates` reaches the gate
   count and the state becomes `Solved`.

### The board — which file

The rules engine is plain C# with no `MonoBehaviour`, so an EditMode test runs it with no scene.
Its parts are `unity-2d-grid`:

| Part | Read |
|---|---|
| Rectangular, isometric and hexagonal cells; offset, axial and cube; which rows shift | `unity-2d-grid` → `reference/coordinates.md` |
| Neighbours per layout, distance, movement range as a flood | `unity-2d-grid` → `reference/neighbours-and-range.md` |
| A path, the heuristic that matches the neighbour rule, a fixed visiting order | `unity-2d-grid` → `reference/pathfinding.md` |
| A line between two cells; what a corner blocks | `unity-2d-grid` → `reference/line-of-sight.md` |
| Who stands where; turn order; actors leaving mid-round | `unity-2d-grid` → `reference/occupancy-and-turns.md` |
| The cell under the pointer, tall isometric tiles included | `unity-2d-grid` → `reference/picking.md` |

What this genre adds on top is the rule set, and it is one class that owns the occupancy map
and returns what each command changed. The sorting yard's `YardBoard` — step or push, one pickup
one cell and never into anything, an undo stack of step records, `PickupsOnGates` and `Solved` —
is written out in `unity-2d-grid`, §3, on `GridOccupancy.StepOrPush` and `Revert`: copy it and
change the rule, not the plumbing. **Solvability** is a breadth-first search over board states,
run in an EditMode test or an Editor menu and never at runtime: `unity-2d-grid` →
`reference/pathfinding.md`.

## Traps

- **Reading `transform.position` in a rule.** Mid-tween it names a cell the piece is not in. The
  rules read the board; only the presenter reads transforms.
- **Accepting input during a tween without a buffer** drops moves; accepting it without a limit
  queues six moves the player cannot see. One deep — `unity-2d-controller` →
  `reference/grid-step.md`.
- **Isometric tiles drawn inside out, or pieces and tall tiles sorting separately.** The palette
  needs a custom sort axis — `unity-tilemap` → `reference/palette-and-grid.md`; the scene needs
  its own — `unity-2d-rendering` → `reference/y-sort.md`.
- **Hexagon neighbours hard-coded for even rows, or diagonals mixed with Manhattan range.** Every
  neighbour lookup goes through one function — `unity-2d-grid` →
  `reference/neighbours-and-range.md`.
- **An isometric D-pad nobody decided.** Screen-up is cell `(+1, +1)`, two cells away and not a
  neighbour. Map up to one neighbour deliberately and write it in the recipe.
- **A board edited in the Tilemap and a level file that disagree.** One source: the Tilemap is
  either the authoring tool that exports the data, or a view built from the data. Never both.
- **Tactics: animating a whole enemy turn in sequence at 0.12 s a cell** makes a ten-unit turn
  take half a minute. Resolve the turn on the board at once, then play the animations
  overlapped or at a multiple — `unity-game-ai` → `reference/tactics-ai.md` §6.

## Where each need is answered

| Need | Answer |
|---|---|
| Step and undo actions, hold-to-repeat, pointer position | `unity-input` → `reference/reading-input.md` |
| Tap and drag on a phone | `unity-input` → `reference/touch-and-on-screen.md` |
| Coordinates, neighbours, range, paths, sight, occupancy, turn order, picking | `unity-2d-grid` → `reference/coordinates.md` and the table above |
| A pick-only collider for tall isometric tiles; the rules themselves ask no collider | `unity-2d-grid` → `reference/picking.md`, then `unity-physics-2d` → `reference/queries-2d.md` |
| The mover that tweens a transform to the board's cell | `unity-2d-controller` → `reference/grid-step.md` |
| A fixed or panning camera with bounds | `unity-camera` → `reference/follow-2d.md` |
| Palettes for rectangular, hexagonal and isometric grids | `unity-tilemap` → `reference/palette-and-grid.md` |
| Rule tiles on a hexagonal grid | `unity-tilemap` → `reference/hexagonal-rule-set.md` |
| Boards from a data file; validating a board before it loads | `unity-2d-level` → `reference/level-data.md` |
| Writing tiles at runtime: highlights, opened gates | `unity-2d-level` → `reference/runtime-tilemap.md` |
| Generated boards | `unity-2d-level` → `reference/procedural.md` |
| The scene sort axis on an isometric board; pieces against tall tiles | `unity-2d-rendering` → `reference/y-sort.md` |
| Isometric sheets, per-cell pivots | `unity-2d-sprites` |
| A step and a push as animation states | `unity-animation` → `reference/sprite-state-graph.md` |
| Rules in an engine-free assembly, EditMode tests | `unity-game-brief` → `reference/sim-presentation-split.md` |
| Enemy turns: enumerate reachable cells, score each, pick with a fixed tie-break, then animate | `unity-game-ai` → `reference/tactics-ai.md` |
| A gate cell a switch opens; using the cell in front | `unity-interaction` → `reference/doors-and-switches.md`, then `unity-interaction` → `reference/detection-choice.md` §6 |
| Pickups taken on a cell; an inventory as data | `unity-interaction` → `reference/pickups.md` |
| Health and one damage event per attack; range stays on the board | `unity-combat` → `reference/damage-contract.md` |
| Level select, the persistent Boot scene, boards loaded and unloaded | `unity-scene-flow` → `reference/bootstrap.md`, then `unity-scene-flow` → `reference/additive-scenes.md` |
| Solved levels and a mid-level board across a quit; a version bump | `unity-scene-flow` → `reference/save-format.md` (`templates/SaveRoundTripTests.cs`) |
| Board rules and level lists as assets | `unity-scene-flow` → `reference/scriptable-objects.md` |
| A step that lands, a push that settles, a gate that opens: squash, easing, sound | `unity-game-feel` → `reference/flash-and-squash.md`, then `unity-game-feel` → `reference/sfx-events.md` |
| Which events get which feedback, within one budget | `unity-game-feel` → `reference/feedback-stack.md` |
| Journeys over a scripted move list | `unity-play-harness` → `reference/journeys.md` |
| Move and action menus, range highlights | `unity-game-ui`; highlights are tiles on a third Tilemap, cleared and refilled per selection |
