// GridStepMover — shows a cell move: the cell changes at once, and the transform is tweened from
// the old cell centre to the new one. Held input repeats, one step is buffered, a refused step
// plays a bump and changes nothing.
//
// Drop into a Runtime assembly and add it to the runner. It needs no physics; keep a kinematic
// Rigidbody2D on the runner only if triggers must fire. It reads IRunInputSource and
// StepRepeater from RunInput.cs (skill unity-input) and never a device. No package needed.
//
// It holds no map. Whether a cell may be entered is asked through CanEnter, and where a cell is
// drawn through CellCentre, so the file compiles with no grid code at all:
//
//   mover.CanEnter   = (from, to) => occupancy.CanEnter((Vector3Int)to);         // the map's answer
//   mover.CellCentre = cell => grid.GetCellCenterWorld((Vector3Int)cell);       // rect, iso or hex
//   mover.Committed += (from, to) => occupancy.TryMove(runnerId, (Vector3Int)to);   // the map is told first
//
// Register with the probe where the game wires its harness:
//   GameProbe.SetPlayerVelocity(() => mover.transform, () => (Vector3)mover.Velocity);
//   GameProbe.Register("cellX", () => mover.Cell.x);   GameProbe.Register("cellY", () => mover.Cell.y);
//   GameProbe.Register("stepping", () => mover.Stepping);
using System;
using UnityEngine;

[DisallowMultipleComponent]
public sealed class GridStepMover : MonoBehaviour
{
    [Header("Step")]
    [Tooltip("Seconds to cross one cell. 0.18 walks; under 0.10 reads as a teleport.")]
    public float stepTime = 0.18f;
    [Tooltip("Ease the tween in and out. Off for a constant-speed walk that chains without a stutter.")]
    public bool ease = false;
    [Tooltip("How far into a refused cell the bump goes, as a fraction of the way.")]
    public float bumpDistance = 0.15f;
    public float bumpTime = 0.12f;

    [Header("Input")]
    [Tooltip("Read steps from the RunInputSource on this object. Off when a turn system calls TryStep itself.")]
    public bool driveFromInput = true;
    [Tooltip("Seconds a held direction waits before repeating.")]
    public float repeatDelay = 0.25f;
    [Tooltip("Seconds between repeats. Keep it at or above stepTime, or the buffer is always full.")]
    public float repeatInterval = 0.18f;

    [Header("Default cell layout — used when CellCentre is not assigned")]
    public Vector2 origin = Vector2.zero;
    public float cellSize = 1f;

    /// <summary>May the runner go from the first cell to the second? Unassigned means every step is allowed.</summary>
    public Func<Vector2Int, Vector2Int, bool> CanEnter;
    /// <summary>World position of a cell's centre. Unassigned means a rectangular layout from origin and cellSize.</summary>
    public Func<Vector2Int, Vector3> CellCentre;

    /// <summary>The cell changed (from, to). Raised before the tween starts: update occupancy here.</summary>
    public event Action<Vector2Int, Vector2Int> Committed;
    /// <summary>The picture caught up with the cell. Raise pickups, gates and turn ends from here.</summary>
    public event Action<Vector2Int> Arrived;
    /// <summary>A step was refused (from, to).</summary>
    public event Action<Vector2Int, Vector2Int> Blocked;

    /// <summary>The truth. It is already the target cell while the tween is still running.</summary>
    public Vector2Int Cell { get; private set; }
    public Vector2Int Facing { get; private set; } = Vector2Int.down;
    public bool Stepping => _mode != Mode.Idle;
    /// <summary>The tween's velocity, for a probe or an Animator. Zero between steps.</summary>
    public Vector2 Velocity { get; private set; }
    public int Steps { get; private set; }

    enum Mode { Idle, Step, Bump }

    readonly StepRepeater _repeater = new StepRepeater();
    IRunInputSource _input;
    Mode _mode;
    Vector3 _from, _to;
    float _t, _duration;
    bool _hasBuffered;
    Vector2Int _buffered;

    /// <summary>Put the runner on a cell with no tween: a level start, a situation, an undo.</summary>
    public void PlaceAt(Vector2Int cell)
    {
        Cell = cell;
        _mode = Mode.Idle;
        _hasBuffered = false;
        _repeater.Reset();
        Velocity = Vector2.zero;
        Vector3 c = Centre(cell);
        transform.position = new Vector3(c.x, c.y, transform.position.z);
    }

    /// <summary>
    /// Ask for one step. Returns true when it was taken or buffered. During a step the request
    /// replaces the single buffered one: the last direction asked for is the one that runs.
    /// </summary>
    public bool TryStep(Vector2Int direction)
    {
        if (direction == Vector2Int.zero) return false;
        if (_mode != Mode.Idle)
        {
            _buffered = direction;
            _hasBuffered = true;
            return true;
        }
        Begin(direction);
        return _mode == Mode.Step;
    }

    void FixedUpdate()
    {
        if (!driveFromInput) return;
        if (!RunInputSource.Resolve(gameObject, ref _input)) return;
        _repeater.initialDelay = repeatDelay;
        _repeater.interval = repeatInterval;
        // The repeater and this read share the fixed clock, so the repeat rate does not change
        // with the frame rate.
        if (_repeater.Step(_input.Peek().move, Time.time, out Vector2Int direction)) TryStep(direction);
    }

    void Update()
    {
        if (_mode == Mode.Idle) return;

        _t += Time.deltaTime / Mathf.Max(_duration, 1e-4f);
        float t = Mathf.Clamp01(_t);
        Vector3 before = transform.position;
        Vector3 p;
        if (_mode == Mode.Step)
        {
            float k = ease ? t * t * (3f - 2f * t) : t;
            p = Vector3.LerpUnclamped(_from, _to, k);
        }
        else
        {
            // Out and back: the runner leans into the wall and returns to its own cell.
            float k = Mathf.Sin(t * Mathf.PI) * bumpDistance;
            p = Vector3.LerpUnclamped(_from, _to, k);
        }
        transform.position = new Vector3(p.x, p.y, transform.position.z);
        Velocity = Time.deltaTime > 0f ? (Vector2)(transform.position - before) / Time.deltaTime : Vector2.zero;

        if (_t < 1f) return;

        Mode finished = _mode;
        _mode = Mode.Idle;
        Velocity = Vector2.zero;
        if (finished == Mode.Step) Arrived?.Invoke(Cell);

        // Arrived may have ended the turn or moved the runner; only then look at the buffer.
        if (_mode == Mode.Idle && _hasBuffered)
        {
            _hasBuffered = false;
            Begin(_buffered);
        }
    }

    void Begin(Vector2Int direction)
    {
        Facing = direction;
        Vector2Int target = Cell + direction;
        _from = Centre(Cell);
        _to = Centre(target);
        _t = 0f;

        if (CanEnter != null && !CanEnter(Cell, target))
        {
            _mode = Mode.Bump;
            _duration = bumpTime;
            Blocked?.Invoke(Cell, target);
            return;
        }

        Vector2Int from = Cell;
        Cell = target;                     // the truth moves now; the picture takes stepTime to agree
        Steps++;
        _mode = Mode.Step;
        _duration = stepTime;
        Committed?.Invoke(from, target);
    }

    Vector3 Centre(Vector2Int cell)
    {
        if (CellCentre != null) return CellCentre(cell);
        return new Vector3(origin.x + (cell.x + 0.5f) * cellSize, origin.y + (cell.y + 0.5f) * cellSize, 0f);
    }
}
