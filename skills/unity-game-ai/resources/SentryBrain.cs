// SentryBrain — the worked sentry: Patrol → Suspicious → Chase → Return. It perceives on a
// budget, decides on a 10 Hz tick, and never writes its own transform: every move is a request
// to an IMover, which is whoever owns the transform.
//
// Drop into a Runtime assembly beside StateMachine.cs and Perception.cs, and add it to the sentry
// together with exactly one IMover component: NavMeshAgentMover.cs on a NavMesh, or an adapter
// over the game's own 2D motor.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json) for the 3D cast.
// 3D: leave plane on XZ; cover is tested with Physics.Linecast against 'blockers'.
// 2D: set plane to XY, eyeHeight and targetHeight to 0, and add Perception2D.cs, which replaces
// the 3D cast with a 2D one.
//
// What it does not do: damage. InAttackRange and AttackRangeEntered are the hand-off; what an
// attack is belongs to the game's combat code.
//
// Register with the probe where the game wires its harness:
//   GameProbe.Register("sentry", () => sentry.StateName);
//   GameProbe.Register("sentryAlert", () => sentry.Alert);
using System;
using UnityEngine;

/// <summary>
/// The seam between deciding and moving. The brain says where and how fast; the mover owns the
/// transform and says where it is. A NavMeshAgent, a 2D motor and a cell stepper all fit behind it.
/// </summary>
public interface IMover
{
    Vector3 Position { get; }
    Vector3 Velocity { get; }
    /// <summary>True when the last MoveTo has been reached, or nothing was asked for.</summary>
    bool Arrived { get; }
    /// <summary>Head for a point. Called at a re-path interval, never every step.</summary>
    void MoveTo(Vector3 destination, float speed, float stoppingDistance);
    void Stop();
    /// <summary>Show this facing while standing still. A mover that turns itself while moving ignores it then.</summary>
    void Face(Vector3 direction);
}

/// <summary>The plane the sentry lives on: XZ for 3D ground, XY for a 2D view.</summary>
public enum SentryPlane { XZ, XY }

/// <summary>
/// Everything the sentry's states and transitions read. Perception writes it on the decision tick;
/// states read it. Typed fields, not a string dictionary: a misspelt key is a compile error.
/// </summary>
public sealed class SentryBlackboard
{
    public float now;
    public Vector3 home;
    public Vector3 homeFacing;
    public int waypoint;

    public SightResult sight = SightResult.NoTarget;
    public bool sees;
    public float targetDistance = float.PositiveInfinity;
    /// <summary>0..1. Fills while the target is seen, drains while it is not. 1 means chase.</summary>
    public float alert;
    public TargetMemory memory;
    /// <summary>Where Suspicious looks: the last sighting or the last noise.</summary>
    public Vector3 interest;
    public bool returned;
}

[DisallowMultipleComponent]
public sealed class SentryBrain : MonoBehaviour
{
    public const string Patrol = "Patrol", Suspicious = "Suspicious", Chase = "Chase", Return = "Return";

    [Header("Target")]
    public Transform target;
    [Tooltip("Height above the target's pivot that sight is tested against. 0 in 2D.")]
    public float targetHeight = 1f;
    [Tooltip("Noise from this team is ignored. The runner emits as team 0.")]
    public int team = 1;

    [Header("Sight")]
    public SentryPlane plane = SentryPlane.XZ;
    public SightCone sight = new SightCone();
    [Tooltip("Height of the eye above the pivot. 0 in 2D.")]
    public float eyeHeight = 1.6f;
    [Tooltip("Layers that hide the target, for the 3D cast. In 2D the mask is on Perception2D.")]
    public LayerMask blockers = 1;

    [Header("Decisions")]
    [Tooltip("Seconds between decisions. 0.1 is 10 Hz; perception and transitions run here, not per frame.")]
    public float decisionInterval = 0.1f;
    [Tooltip("Seconds of continuous sight before the sentry chases.")]
    public float reactionSeconds = 0.4f;
    [Tooltip("Seconds for a full alert to drain once the target is out of sight.")]
    public float calmSeconds = 1.5f;
    [Tooltip("Seconds the last-seen position is trusted. The chase ends when it is older than this.")]
    public float memorySeconds = 3f;
    [Tooltip("Scales the radius of every noise. 0 is deaf.")]
    public float hearingScale = 1f;
    [Tooltip("Alert a heard noise raises to. Below 1: a noise makes the sentry look, only sight makes it chase.")]
    public float heardAlert = 0.5f;

    [Header("Patrol")]
    [Tooltip("Visited in order, looping. Empty: the sentry holds its post.")]
    public Transform[] waypoints;
    public float waitSeconds = 1f;
    public float patrolSpeed = 2f;

    [Header("Chase")]
    [Tooltip("Slower than the runner's 5, so a seen runner can still get away.")]
    public float chaseSpeed = 4f;
    [Tooltip("Seconds between destinations issued while chasing.")]
    public float repathInterval = 0.25f;
    [Tooltip("The sentry stops this far from the target.")]
    public float stoppingDistance = 1f;
    [Tooltip("InAttackRange is true inside this, while the target is seen. Larger than stoppingDistance.")]
    public float attackRange = 1.5f;
    [Tooltip("Units from home. A target beyond it is not chased; one inside 90% of it can be noticed. 0 means no leash.")]
    public float leashDistance = 15f;
    [Tooltip("Degrees per second the facing turns while standing: looking at a noise, searching.")]
    public float turnSpeed = 360f;
    [Tooltip("Degrees per second the sentry sweeps its facing at the last-seen position.")]
    public float searchTurnSpeed = 90f;

    /// <summary>The blackboard, for transitions, tests and a debugger.</summary>
    public SentryBlackboard Board { get; } = new SentryBlackboard();
    /// <summary>Patrol · Suspicious · Chase · Return, or null before the first step.</summary>
    public string StateName => _machine != null ? _machine.Current : null;
    public float Alert => Board.alert;
    public bool Sees => Board.sees;
    /// <summary>Unit vector on the play plane. Set from intent and motion; the cone is tested along it.</summary>
    public Vector3 Facing { get; private set; } = Vector3.forward;
    /// <summary>The hand-off to combat: seen, and no farther than attackRange.</summary>
    public bool InAttackRange { get; private set; }
    /// <summary>Decision ticks completed. Compare with elapsed time to read the real decision rate.</summary>
    public int Decisions { get; private set; }

    /// <summary>The transform owner. Found on this object in Start; assign to replace it.</summary>
    public IMover Mover { get; set; }
    /// <summary>The cover test. Found on this object in Start; null means Physics.Linecast against 'blockers'.</summary>
    public ILineOfSight LineOfSight { get; set; }

    /// <summary>(from, to) after every state change.</summary>
    public event Action<string, string> StateChanged;
    /// <summary>Raised on the decision tick the target first comes inside attackRange.</summary>
    public event Action<Transform> AttackRangeEntered;

    static int s_Created;

    StateMachine<SentryBrain> _machine;
    DecisionClock _clock;
    bool _decisionDue;
    bool _heard;
    Vector3 _heardAt;

    Vector3 Up => plane == SentryPlane.XZ ? Vector3.up : Vector3.forward;
    Vector3 Position => Mover != null ? Mover.Position : transform.position;
    Vector3 Eye => plane == SentryPlane.XZ ? Position + Vector3.up * eyeHeight : Position;
    Vector3 TargetPoint => plane == SentryPlane.XZ ? target.position + Vector3.up * targetHeight : target.position;

    Vector3 Flat(Vector3 v) => v - Up * Vector3.Dot(v, Up);

    void OnEnable() => NoiseEvents.Emitted += OnNoise;
    void OnDisable() => NoiseEvents.Emitted -= OnNoise;

    // Start, not Awake: a spawner or a test sets fields after AddComponent and before the first step.
    void Start()
    {
        if (Mover == null && TryGetComponent(out IMover mover)) Mover = mover;
        if (LineOfSight == null && TryGetComponent(out ILineOfSight los)) LineOfSight = los;
        if (Mover == null)
        {
            Debug.LogError("SentryBrain on '" + name + "' has no IMover component: nothing owns its transform.", this);
            enabled = false;
            return;
        }

        Board.home = Mover.Position;
        Vector3 forward = Flat(plane == SentryPlane.XZ ? transform.forward : transform.up);
        Facing = forward.sqrMagnitude > 1e-6f ? forward.normalized : (plane == SentryPlane.XZ ? Vector3.forward : Vector3.up);
        Board.homeFacing = Facing;

        // Five slots across the interval: sentries placed together decide on different steps.
        _clock = new DecisionClock(decisionInterval, (s_Created++ % 5) / 5f);

        _machine = new StateMachine<SentryBrain>(this);
        _machine.Add(Patrol, new PatrolState());
        _machine.Add(Suspicious, new SuspiciousState());
        _machine.Add(Chase, new ChaseState());
        _machine.Add(Return, new ReturnState());

        // Order is priority. Every condition reads the blackboard; none of them casts.
        _machine.AddTransition(Patrol, Suspicious, c => c.Board.alert > 0f);
        _machine.AddTransition(Return, Suspicious, c => c.Board.alert > 0f);
        _machine.AddTransition(Suspicious, Chase, c => c.Board.sees && c.Board.alert >= 1f - 1e-4f);
        _machine.AddTransition(Suspicious, Return, c => c.Board.alert <= 0f);
        _machine.AddTransition(Chase, Return, c => c.Board.memory.Expired(c.Board.now, c.memorySeconds)
                                                  || !c.InTerritory(c.Board.memory.position, true));
        _machine.AddTransition(Return, Patrol, c => c.Board.returned);
        _machine.Changed += (from, to) => StateChanged?.Invoke(from, to);
        _machine.Start(Patrol);
    }

    void FixedUpdate()
    {
        if (_machine == null) return;
        float dt = Time.fixedDeltaTime;
        Board.now = Time.time;
        _clock.Interval = decisionInterval;

        // While moving, the sentry looks where it goes. Standing, a state turns it deliberately.
        Vector3 velocity = Flat(Mover.Velocity);
        if (velocity.sqrMagnitude > 0.01f) Facing = velocity.normalized;

        if (_clock.Due(dt)) _decisionDue = true;
        // A decision refused by the cast budget is retried on the next step, not dropped.
        if (_decisionDue && Perceive())
        {
            _decisionDue = false;
            Decisions++;
            _machine.Decide();
        }

        _machine.Tick(dt);
        Mover.Face(Facing);
    }

    /// <summary>Point the sentry at a new target, or at none.</summary>
    public void SetTarget(Transform newTarget)
    {
        target = newTarget;
        Board.memory.Forget();
    }

    /// <summary>
    /// Start again from where the sentry now stands: home, facing, alert, memory and state. For a
    /// pooled sentry taken out for a new wave. Before the first Start it does nothing — Start
    /// does the same work.
    /// </summary>
    public void Restart()
    {
        if (_machine == null) return;
        Board.home = Mover.Position;
        Board.homeFacing = Facing;
        Board.waypoint = 0;
        Board.alert = 0f;
        Board.sees = false;
        Board.returned = false;
        Board.memory.Forget();
        _heard = false;
        _decisionDue = false;
        InAttackRange = false;
        _machine.Restart(Patrol);
    }

    /// <summary>
    /// The decision tick's perception: range and angle first, then at most one cast. False when
    /// the cast budget is spent — the blackboard is left as it was.
    /// </summary>
    bool Perceive()
    {
        SentryBlackboard b = Board;
        SightResult result = SightResult.NoTarget;
        float distance = float.PositiveInfinity;

        if (target != null && target.gameObject.activeInHierarchy)
        {
            Vector3 eye = Eye, point = TargetPoint;
            bool tracking = _machine.Is(Chase) || _machine.Is(Suspicious);
            result = sight.Covers(eye, Facing, point, Up, tracking);
            if (result == SightResult.Seen && !InTerritory(target.position, tracking))
                result = SightResult.OutOfTerritory;
            if (result == SightResult.Seen)
            {
                if (!PerceptionBudget.TryTake()) return false;
                if (!Clear(eye, point)) result = SightResult.Blocked;
            }
            distance = Flat(point - eye).magnitude;
        }

        b.sight = result;
        b.sees = result == SightResult.Seen;
        b.targetDistance = distance;

        float interval = Mathf.Max(decisionInterval, Time.fixedDeltaTime);
        if (b.sees)
        {
            b.alert = Mathf.Min(1f, b.alert + interval / Mathf.Max(reactionSeconds, interval));
            b.memory.Remember(target.position, b.now);
            b.interest = target.position;
        }
        else
        {
            b.alert = Mathf.Max(0f, b.alert - interval / Mathf.Max(calmSeconds, interval));
        }

        if (_heard)
        {
            _heard = false;
            b.alert = Mathf.Max(b.alert, heardAlert);
            if (!b.sees) b.interest = _heardAt;
        }

        bool inRange = b.sees && distance <= attackRange;
        if (inRange && !InAttackRange) AttackRangeEntered?.Invoke(target);
        InAttackRange = inRange;
        return true;
    }

    bool Clear(Vector3 from, Vector3 to)
    {
        if (LineOfSight != null) return LineOfSight.Clear(from, to);
        return !Physics.Linecast(from, to, blockers, QueryTriggerInteraction.Ignore);
    }

    /// <summary>Inside the leash. Noticing uses 90% of it and keeping uses all of it, so a target on the boundary does not flip the sentry back and forth.</summary>
    bool InTerritory(Vector3 point, bool tracking)
    {
        if (leashDistance <= 0f) return true;
        float limit = tracking ? leashDistance : leashDistance * 0.9f;
        return Flat(point - Board.home).sqrMagnitude <= limit * limit;
    }

    void OnNoise(NoiseEvent noise)
    {
        if (noise.team == team || hearingScale <= 0f) return;
        float radius = noise.radius * hearingScale;
        if (Flat(noise.position - Position).sqrMagnitude > radius * radius) return;
        // Stored, not acted on: the decision tick is the only place the state may change.
        _heard = true;
        _heardAt = noise.position;
    }

    /// <summary>Turn the facing towards a direction at a rate, staying on the play plane.</summary>
    void TurnTowards(Vector3 direction, float degrees)
    {
        direction = Flat(direction);
        if (direction.sqrMagnitude < 1e-6f) return;
        float angle = Vector3.SignedAngle(Facing, direction, Up);
        Facing = (Quaternion.AngleAxis(Mathf.Clamp(angle, -degrees, degrees), Up) * Facing).normalized;
    }

    Vector3 PatrolPoint()
    {
        if (waypoints == null || waypoints.Length == 0) return Board.home;
        Transform point = waypoints[Board.waypoint % waypoints.Length];
        return point != null ? point.position : Board.home;
    }

    // ------------------------------------------------------------------------------ states

    sealed class PatrolState : IState<SentryBrain>
    {
        float _waited;
        bool _waiting;

        public void Enter(SentryBrain c)
        {
            _waiting = false;
            _waited = 0f;
            c.Mover.MoveTo(c.PatrolPoint(), c.patrolSpeed, 0f);
        }

        public void Tick(SentryBrain c, float dt)
        {
            if (!c.Mover.Arrived) return;
            bool holdsPost = c.waypoints == null || c.waypoints.Length == 0;
            if (holdsPost)
            {
                c.TurnTowards(c.Board.homeFacing, c.turnSpeed * dt);
                return;
            }
            if (!_waiting) { _waiting = true; _waited = 0f; }
            _waited += dt;
            if (_waited < c.waitSeconds) return;
            _waiting = false;
            c.Board.waypoint = (c.Board.waypoint + 1) % c.waypoints.Length;
            c.Mover.MoveTo(c.PatrolPoint(), c.patrolSpeed, 0f);
        }

        public void Exit(SentryBrain c) { }
    }

    sealed class SuspiciousState : IState<SentryBrain>
    {
        public void Enter(SentryBrain c) => c.Mover.Stop();

        public void Tick(SentryBrain c, float dt)
            => c.TurnTowards(c.Board.interest - c.Position, c.turnSpeed * dt);

        public void Exit(SentryBrain c) { }
    }

    sealed class ChaseState : IState<SentryBrain>
    {
        float _untilRepath;

        public void Enter(SentryBrain c) => _untilRepath = 0f;

        public void Tick(SentryBrain c, float dt)
        {
            _untilRepath -= dt;
            if (_untilRepath <= 0f)
            {
                // The last place the runner was seen, never its live position: a sentry that
                // steers at a target it cannot see is reading the player's mind.
                _untilRepath = c.repathInterval;
                c.Mover.MoveTo(c.Board.memory.position, c.chaseSpeed, c.stoppingDistance);
            }

            if (c.Board.sees) c.TurnTowards(c.Board.memory.position - c.Position, c.turnSpeed * dt);
            else if (c.Mover.Arrived) c.TurnTowards(Quaternion.AngleAxis(90f, c.Up) * c.Facing, c.searchTurnSpeed * dt);
        }

        public void Exit(SentryBrain c)
        {
            c.Mover.Stop();
            // The chase is over: start the walk home calm, so only a fresh sighting interrupts it.
            c.Board.alert = 0f;
            c.Board.memory.Forget();
        }
    }

    sealed class ReturnState : IState<SentryBrain>
    {
        public void Enter(SentryBrain c)
        {
            c.Board.returned = false;
            c.Mover.MoveTo(c.PatrolPoint(), c.patrolSpeed, 0f);
        }

        public void Tick(SentryBrain c, float dt)
        {
            if (c.Mover.Arrived) c.Board.returned = true;
        }

        public void Exit(SentryBrain c) => c.Board.returned = false;
    }

    // The cone drawn from the numbers the test uses, so what is seen in the Scene view is what is tested.
    void OnDrawGizmosSelected()
    {
        Vector3 up = Up;
        Vector3 eye = plane == SentryPlane.XZ ? transform.position + Vector3.up * eyeHeight : transform.position;
        Vector3 forward = Application.isPlaying ? Facing : Flat(plane == SentryPlane.XZ ? transform.forward : transform.up).normalized;
        if (forward.sqrMagnitude < 1e-6f) return;
        Gizmos.color = Board.sees ? Color.red : Color.yellow;
        const int segments = 12;
        Vector3 previous = eye;
        for (int i = 0; i <= segments; i++)
        {
            float a = Mathf.Lerp(-sight.angle * 0.5f, sight.angle * 0.5f, i / (float)segments);
            Vector3 rim = eye + Quaternion.AngleAxis(a, up) * forward * sight.range;
            Gizmos.DrawLine(previous, rim);
            previous = rim;
        }
        Gizmos.DrawLine(previous, eye);
    }
}
