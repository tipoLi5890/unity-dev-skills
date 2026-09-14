// The presentation half. It owns the clock, the scene objects and the logging, and it
// owns NO rules: there is no Random here, no lane arithmetic, no collision test, no
// score. Every frame it reads RunState and draws it.
//
// Scene setup: an empty GameObject with this component, a runner Transform (a capsule
// will do), a gate Transform (a stretched cube), and two primitive prefabs. Nothing here
// needs a package.
using Game.Sim;
using UnityEngine;

namespace Game.Presentation
{
    [AddComponentMenu("Courier/Run Presenter")]
    public sealed class RunPresenter : MonoBehaviour
    {
        [Header("Run")]
        [SerializeField] int seed = 1;

        [Header("Scene")]
        [SerializeField] Transform runner;
        [SerializeField] Transform gate;
        [SerializeField] GameObject hazardPrefab;
        [SerializeField] GameObject pickupPrefab;

        [Header("Presentation only")]
        [Tooltip("Units per second the drawn runner glides toward its lane centre. Changing " +
                 "this changes how the shift looks and nothing about the run.")]
        [SerializeField] float laneGlide = 9f;
        [SerializeField] int maxStepsPerFrame = 8;

        RunSimulation _sim;
        Transform _spawnRoot;
        float _accumulator;
        float _drawnX;
        RunPhase _lastPhase;

        public RunSimulation Simulation => _sim;
        public RunState State => _sim?.State;

        void Awake()
        {
            _sim = new RunSimulation(RunConfig.Courier(), seed);
            _lastPhase = _sim.State.Phase;
            _drawnX = _sim.LaneWorldX(_sim.State.Lane);

            // INV-1: the track exists before anything is drawn. The simulation guarantees it
            // in its constructor; the presenter refuses to spawn if that ever stops being true.
            if (!_sim.State.TrackReady)
            {
                Debug.LogError("[RUN] track not ready — nothing spawned");
                enabled = false;
                return;
            }

            SpawnTrack();
            Debug.Log($"[RUN] ready seed={seed} hazards={_sim.Hazards.Count} " +
                      $"pickups={_sim.Pickups.Count} gate={_sim.Config.GateDistance:F1}");
        }

        void SpawnTrack()
        {
            _spawnRoot = new GameObject("Track").transform;
            _spawnRoot.SetParent(transform, false);

            if (hazardPrefab != null)
                foreach (Hazard hazard in _sim.Hazards)
                    Instantiate(hazardPrefab, WorldOf(hazard.Lane, hazard.Distance), Quaternion.identity, _spawnRoot);

            if (pickupPrefab != null)
                foreach (Pickup pickup in _sim.Pickups)
                    Instantiate(pickupPrefab, WorldOf(pickup.Lane, pickup.Distance), Quaternion.identity, _spawnRoot);

            if (gate != null) gate.position = WorldOf(_sim.Config.LaneCount / 2, _sim.Config.GateDistance);
        }

        Vector3 WorldOf(int lane, float distance) =>
            transform.position + new Vector3(_sim.LaneWorldX(lane), 0f, distance);

        // The simulation is stepped at a fixed dt regardless of the frame rate, so a slow
        // frame produces the same run as a fast one.
        void Update()
        {
            if (_sim == null) return;
            float step = _sim.Config.TickSeconds;
            _accumulator += Time.deltaTime;
            int steps = 0;
            while (_accumulator >= step && steps < maxStepsPerFrame)
            {
                _sim.Tick(step);
                _accumulator -= step;
                steps++;
            }
            // A frame that fell far behind drops the backlog rather than spiralling.
            if (_accumulator > step * maxStepsPerFrame) _accumulator = 0f;
        }

        void LateUpdate()
        {
            if (_sim == null) return;
            RunState state = _sim.State;

            if (runner != null)
            {
                _drawnX = Mathf.MoveTowards(_drawnX, _sim.LaneWorldX(state.Lane), laneGlide * Time.deltaTime);
                runner.position = transform.position + new Vector3(_drawnX, 0f, state.Distance);
            }

            if (state.Phase != _lastPhase)
            {
                Debug.Log($"[RUN] phase={state.Phase} lane={state.Lane} dist={state.Distance:F2} " +
                          $"speed={state.Speed:F2} pickups={state.Pickups} ticks={state.Ticks}");
                _lastPhase = state.Phase;
            }
        }

        // The only three ways into the run. Input, a test, a situation and a debug key all
        // arrive here, so there is exactly one funnel to instrument.
        public void Launch() => _sim?.Enqueue(RunCommand.Launch);
        public void LaneLeft() => _sim?.Enqueue(RunCommand.LaneLeft);
        public void LaneRight() => _sim?.Enqueue(RunCommand.LaneRight);
    }
}
