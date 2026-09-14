// The simulation half of the courier-run skeleton. This assembly has
// "noEngineReferences": true, so nothing here may touch UnityEngine — no Transform,
// no Time, no Debug, no Random, no JsonUtility. Everything the player sees is derived
// from RunState by the presentation assembly.
//
// Contract with the rest of the game:
//   commands in   -> Enqueue(RunCommand)
//   state out     -> State (the ONLY type that crosses the assembly boundary)
//   time in       -> Tick(dt), called with a fixed dt by whoever owns the clock
using System;
using System.Collections.Generic;
using System.Globalization;

namespace Game.Sim
{
    public enum RunPhase { Idle, Launched, AtGate, Crashed }

    public enum CommandKind { Launch, LaneLeft, LaneRight }

    /// <summary>One press of one of the three physical buttons, already de-deviced.</summary>
    public readonly struct RunCommand
    {
        public readonly CommandKind Kind;

        public RunCommand(CommandKind kind) { Kind = kind; }

        public static RunCommand Launch => new RunCommand(CommandKind.Launch);
        public static RunCommand LaneLeft => new RunCommand(CommandKind.LaneLeft);
        public static RunCommand LaneRight => new RunCommand(CommandKind.LaneRight);

        public override string ToString() => Kind.ToString();
    }

    /// <summary>
    /// Every number the run is tuned by. Each one traces back to a line of the brief;
    /// change them here, never inside the presenter.
    /// </summary>
    public sealed class RunConfig
    {
        public int LaneCount = 3;          // three lanes, three buttons
        public float LaneSpacing = 1.3f;   // units between lane centres
        public float GateDistance = 120f;  // units from launch to the gate
        public float LaunchSpeed = 4.4f;   // cruise speed, units/second
        public float Acceleration = 6f;    // units/second^2 up to LaunchSpeed
        public float ShiftSpeedFactor = 0.9f; // a lane shift scrubs 10% of the speed
        public float RowSpacing = 6f;      // units between hazard rows
        public float LookAhead = 5f;       // how far ahead a lane is judged clear
        public float TickSeconds = 1f / 60f; // the fixed step Tick() expects

        /// <summary>Defaults that satisfy the courier-run brief (INV-3: 20-40 s per run).</summary>
        public static RunConfig Courier() => new RunConfig();
    }

    public readonly struct Hazard
    {
        public readonly int Row;
        public readonly int Lane;
        public readonly float Distance;

        public Hazard(int row, int lane, float distance) { Row = row; Lane = lane; Distance = distance; }
    }

    public readonly struct Pickup
    {
        public readonly int Row;
        public readonly int Lane;
        public readonly float Distance;

        public Pickup(int row, int lane, float distance) { Row = row; Lane = lane; Distance = distance; }
    }

    /// <summary>
    /// The whole observable run. The presenter reads this and draws it; a test reads this
    /// and asserts on it; a probe reads this and prints it. Nothing else crosses the boundary.
    /// </summary>
    public sealed class RunState
    {
        public RunPhase Phase;
        public int Lane;
        public float Distance;
        public float Speed;
        public int Pickups;
        public int Ticks;
        public bool TrackReady;

        public RunState Clone() => new RunState
        {
            Phase = Phase, Lane = Lane, Distance = Distance, Speed = Speed,
            Pickups = Pickups, Ticks = Ticks, TrackReady = TrackReady
        };

        /// <summary>One comparable line — used by the determinism test and by a probe hook.</summary>
        public string Signature() => string.Format(CultureInfo.InvariantCulture,
            "phase={0} lane={1} dist={2:F4} speed={3:F4} pickups={4} ticks={5} ready={6}",
            Phase, Lane, Distance, Speed, Pickups, Ticks, TrackReady);

        public override string ToString() => Signature();
    }

    public sealed class RunSimulation
    {
        readonly Queue<RunCommand> _commands = new Queue<RunCommand>();
        readonly List<Hazard> _hazards = new List<Hazard>();
        readonly List<Pickup> _pickups = new List<Pickup>();
        int _nextHazard;
        int _nextPickup;

        public RunConfig Config { get; }
        public RunState State { get; }
        public int Seed { get; }
        public IReadOnlyList<Hazard> Hazards => _hazards;
        public IReadOnlyList<Pickup> Pickups => _pickups;

        /// <summary>
        /// The track is generated in the constructor, so TrackReady is true before the first
        /// Tick and before anything is drawn (INV-1).
        /// </summary>
        public RunSimulation(RunConfig config, int seed)
        {
            if (config == null) throw new ArgumentNullException(nameof(config));
            if (config.LaneCount < 1) throw new ArgumentOutOfRangeException(nameof(config), "LaneCount must be >= 1");
            Config = config;
            Seed = seed;
            State = new RunState { Lane = config.LaneCount / 2 };
            TrackGen.Generate(config, seed, _hazards, _pickups);
            State.TrackReady = true;
        }

        public float DistanceToGate => Math.Max(0f, Config.GateDistance - State.Distance);

        /// <summary>World X of a lane centre. The presenter multiplies nothing of its own.</summary>
        public float LaneWorldX(int lane) => (lane - (Config.LaneCount - 1) * 0.5f) * Config.LaneSpacing;

        public void Enqueue(RunCommand command) => _commands.Enqueue(command);

        /// <summary>True when a hazard sits in that lane within <paramref name="lookAhead"/> units.</summary>
        public bool LaneBlockedWithin(int lane, float lookAhead)
        {
            float limit = State.Distance + lookAhead;
            for (int i = _nextHazard; i < _hazards.Count && _hazards[i].Distance <= limit; i++)
                if (_hazards[i].Lane == lane) return true;
            return false;
        }

        /// <summary>
        /// Advance by exactly <paramref name="dt"/>. Determinism is the caller's fixed dt plus
        /// this method having no other input: same seed and same command sequence, same result.
        /// </summary>
        public void Tick(float dt)
        {
            State.Ticks++;
            DrainCommands();
            if (State.Phase != RunPhase.Launched) return;

            if (State.Speed < Config.LaunchSpeed)
                State.Speed = Math.Min(Config.LaunchSpeed, State.Speed + Config.Acceleration * dt);

            float from = State.Distance;
            float to = from + State.Speed * dt;
            to = ResolveHazards(from, to);
            ResolvePickups(from, to);
            State.Distance = to;

            if (State.Phase == RunPhase.Launched && State.Distance >= Config.GateDistance)
            {
                State.Distance = Config.GateDistance;
                State.Phase = RunPhase.AtGate;
            }
        }

        void DrainCommands()
        {
            while (_commands.Count > 0)
            {
                RunCommand command = _commands.Dequeue();
                switch (command.Kind)
                {
                    case CommandKind.Launch:
                        if (State.Phase == RunPhase.Idle) State.Phase = RunPhase.Launched;
                        break;
                    case CommandKind.LaneLeft:
                        Shift(-1);
                        break;
                    case CommandKind.LaneRight:
                        Shift(+1);
                        break;
                }
            }
        }

        // INV-2 lives here: a shift off the track is dropped, never clamped silently elsewhere.
        void Shift(int delta)
        {
            if (State.Phase != RunPhase.Idle && State.Phase != RunPhase.Launched) return;
            int next = State.Lane + delta;
            if (next < 0 || next >= Config.LaneCount) return;
            State.Lane = next;
            State.Speed *= Config.ShiftSpeedFactor;
        }

        // Returns the distance actually reached: a crash stops the runner at the hazard.
        float ResolveHazards(float from, float to)
        {
            while (_nextHazard < _hazards.Count && _hazards[_nextHazard].Distance <= to)
            {
                Hazard hazard = _hazards[_nextHazard];
                if (hazard.Distance > from && hazard.Lane == State.Lane)
                {
                    State.Phase = RunPhase.Crashed;
                    State.Speed = 0f;
                    return hazard.Distance;
                }
                _nextHazard++;
            }
            return to;
        }

        void ResolvePickups(float from, float to)
        {
            while (_nextPickup < _pickups.Count && _pickups[_nextPickup].Distance <= to)
            {
                Pickup pickup = _pickups[_nextPickup++];
                if (pickup.Distance > from && pickup.Lane == State.Lane) State.Pickups++;
            }
        }
    }
}
