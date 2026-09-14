// EditMode tests for the simulation assembly. They open no scene, instantiate no
// GameObject and need no Editor window, because the assembly under test has
// "noEngineReferences": true — which is the whole point of the split.
//
// One test per invariant in the brief, named after it, and every test prints the number it
// asserted on so the log still says WHY it passed after the next change.
using System.Collections.Generic;
using Game.Sim;
using NUnit.Framework;

namespace Game.Sim.Tests
{
    public class RunSimulationTests
    {
        static RunSimulation NewRun(int seed) => new RunSimulation(RunConfig.Courier(), seed);

        [Test]
        public void INV1_TrackIsReadyBeforeFirstTick()
        {
            RunSimulation sim = NewRun(1);

            Assert.IsTrue(sim.State.TrackReady, "track must be ready before the first tick");
            Assert.Greater(sim.Hazards.Count, 0, "a run with no hazards is not the run in the brief");
            Assert.AreEqual(0, sim.State.Ticks, "nothing may have ticked yet");
            TestContext.WriteLine($"INV-1 ready={sim.State.TrackReady} hazards={sim.Hazards.Count} " +
                                  $"pickups={sim.Pickups.Count} ticks={sim.State.Ticks}");
        }

        [Test]
        public void INV2_LaneNeverLeavesTrack()
        {
            RunConfig cfg = RunConfig.Courier();
            RunSimulation sim = NewRun(2);
            sim.Enqueue(RunCommand.Launch);
            int minLane = sim.State.Lane;
            int maxLane = sim.State.Lane;
            int runs = 1;

            // Push hard against both edges: 60 shifts one way, then 60 the other, for 600 ticks.
            // A crashed or arrived run stops accepting shifts, so it is replaced rather than
            // hammered — otherwise most of the loop would be asserting against a frozen lane.
            for (int step = 0; step < 600; step++)
            {
                if (sim.State.Phase == RunPhase.Crashed || sim.State.Phase == RunPhase.AtGate)
                {
                    sim = NewRun(2 + runs);
                    sim.Enqueue(RunCommand.Launch);
                    runs++;
                }

                sim.Enqueue(step % 120 < 60 ? RunCommand.LaneLeft : RunCommand.LaneRight);
                sim.Tick(cfg.TickSeconds);
                minLane = sim.State.Lane < minLane ? sim.State.Lane : minLane;
                maxLane = sim.State.Lane > maxLane ? sim.State.Lane : maxLane;
                Assert.GreaterOrEqual(sim.State.Lane, 0, $"lane went below 0 at step {step}");
                Assert.Less(sim.State.Lane, cfg.LaneCount, $"lane left the track at step {step}");
            }

            Assert.AreEqual(0, minLane, "the hammer never reached the left edge — the test is not testing");
            Assert.AreEqual(cfg.LaneCount - 1, maxLane, "the hammer never reached the right edge");
            TestContext.WriteLine($"INV-2 lanes visited {minLane}..{maxLane} of 0..{cfg.LaneCount - 1} " +
                                  $"over 600 live ticks across {runs} runs");
        }

        [Test]
        public void INV3_LaunchReachesGateWithinBudget()
        {
            const float minSeconds = 20f;
            const float maxSeconds = 40f;
            var times = new List<float>();

            for (int seed = 1; seed <= 5; seed++)
            {
                RunSimulation sim = NewRun(seed);
                RunConfig cfg = sim.Config;
                sim.Enqueue(RunCommand.Launch);

                int maxTicks = (int)(maxSeconds / cfg.TickSeconds) + 1;
                while (sim.State.Phase == RunPhase.Launched || sim.State.Phase == RunPhase.Idle)
                {
                    Autopilot(sim);
                    sim.Tick(cfg.TickSeconds);
                    if (sim.State.Ticks > maxTicks) break;
                }

                float seconds = sim.State.Ticks * cfg.TickSeconds;
                TestContext.WriteLine($"INV-3 seed={seed} phase={sim.State.Phase} " +
                                      $"seconds={seconds:F2} pickups={sim.State.Pickups}");
                Assert.AreEqual(RunPhase.AtGate, sim.State.Phase,
                    $"seed {seed} did not reach the gate — a clear lane exists in every row");
                times.Add(seconds);
            }

            times.Sort();
            float median = times[times.Count / 2];
            float worst = times[times.Count - 1];
            TestContext.WriteLine($"INV-3 median={median:F2}s worst={worst:F2}s budget={minSeconds}-{maxSeconds}s");
            Assert.GreaterOrEqual(median, minSeconds, "a run this short is over before it reads");
            Assert.LessOrEqual(worst, maxSeconds, "a run this long outlasts the moment in the brief");
        }

        [Test]
        public void INV4_SameSeedSameState()
        {
            RunSimulation a = NewRun(7);
            RunSimulation b = NewRun(7);
            a.Enqueue(RunCommand.Launch);
            b.Enqueue(RunCommand.Launch);

            // Drive both all the way to an ending rather than a fixed tick count: a run that
            // crashes in its first seconds proves determinism over almost nothing, and that is
            // exactly the run a fixed count usually lands on.
            int maxTicks = (int)(40f / a.Config.TickSeconds) + 1;
            while (a.State.Phase == RunPhase.Launched || a.State.Phase == RunPhase.Idle)
            {
                Autopilot(a);
                Autopilot(b);
                a.Tick(a.Config.TickSeconds);
                b.Tick(b.Config.TickSeconds);
                if (a.State.Ticks > maxTicks) break;
            }

            TestContext.WriteLine($"INV-4 a: {a.State.Signature()}");
            TestContext.WriteLine($"INV-4 b: {b.State.Signature()}");
            Assert.AreEqual(RunPhase.AtGate, a.State.Phase, "the compared run never finished");
            Assert.AreEqual(a.State.Signature(), b.State.Signature(), "same seed, same commands, same run");
            Assert.AreEqual(a.Hazards.Count, b.Hazards.Count, "same seed, same track");
        }

        [Test]
        public void INV5_EveryRowLeavesALane()
        {
            RunConfig cfg = RunConfig.Courier();
            var hazards = new List<Hazard>();
            var pickups = new List<Pickup>();
            int rowsChecked = 0;

            for (int seed = 1; seed <= 1000; seed++)
            {
                TrackGen.Generate(cfg, seed, hazards, pickups);
                Assert.IsTrue(TrackGen.EveryRowLeavesALane(cfg, hazards),
                    $"seed {seed} generated a row that blocks all {cfg.LaneCount} lanes");
                rowsChecked += hazards.Count;
            }

            TestContext.WriteLine($"INV-5 seeds=1..1000 hazards checked={rowsChecked} lanes={cfg.LaneCount}");
        }

        // Steers away from a hazard in the current lane. It is test-only: shipping this is a
        // design decision nobody has made yet, and the brief says the human drives.
        static void Autopilot(RunSimulation sim)
        {
            if (sim.State.Phase != RunPhase.Launched) return;
            if (!sim.LaneBlockedWithin(sim.State.Lane, sim.Config.LookAhead)) return;

            int target = TrackGen.FirstClearLane(sim, sim.Config.LookAhead);
            if (target < 0 || target == sim.State.Lane) return;

            int steps = target > sim.State.Lane ? target - sim.State.Lane : sim.State.Lane - target;
            for (int i = 0; i < steps; i++)
                sim.Enqueue(target > sim.State.Lane ? RunCommand.LaneRight : RunCommand.LaneLeft);
        }
    }
}
