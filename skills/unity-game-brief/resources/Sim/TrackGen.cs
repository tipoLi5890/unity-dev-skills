// Seeded track generation. It lives in the simulation assembly because "the same seed
// gives the same run" is an invariant (INV-4) and an invariant has to be testable without
// opening a scene. Nothing here touches UnityEngine.
using System;
using System.Collections.Generic;

namespace Game.Sim
{
    public static class TrackGen
    {
        /// <summary>
        /// Fill <paramref name="hazards"/> and <paramref name="pickups"/> for one run.
        /// Every row leaves at least one lane open (INV-5), so the run is always winnable.
        /// </summary>
        public static void Generate(RunConfig cfg, int seed, List<Hazard> hazards, List<Pickup> pickups)
        {
            if (cfg == null) throw new ArgumentNullException(nameof(cfg));
            if (hazards == null) throw new ArgumentNullException(nameof(hazards));
            if (pickups == null) throw new ArgumentNullException(nameof(pickups));

            hazards.Clear();
            pickups.Clear();

            // System.Random is deterministic for a given seed within one runtime. If you need
            // the same track across runtimes or across editor versions, swap this for a small
            // explicit generator and keep the same call shape.
            Random rng = new Random(seed);
            var others = new List<int>(cfg.LaneCount);
            int rows = (int)(cfg.GateDistance / cfg.RowSpacing);

            for (int row = 1; row < rows; row++)
            {
                float distance = row * cfg.RowSpacing;

                // Pick the lane this row is guaranteed to leave open, then block up to all
                // of the others. Choosing the open lane FIRST is what makes INV-5 structural
                // rather than something a later check has to repair.
                int openLane = rng.Next(cfg.LaneCount);
                others.Clear();
                for (int lane = 0; lane < cfg.LaneCount; lane++)
                    if (lane != openLane) others.Add(lane);

                for (int i = others.Count - 1; i > 0; i--)
                {
                    int j = rng.Next(i + 1);
                    int swap = others[i];
                    others[i] = others[j];
                    others[j] = swap;
                }

                int blocked = others.Count == 0 ? 0 : 1 + rng.Next(others.Count);
                for (int i = 0; i < blocked; i++)
                    hazards.Add(new Hazard(row, others[i], distance));

                // A pickup always sits in the open lane, so collecting one never forces a crash.
                if (rng.NextDouble() < 0.35) pickups.Add(new Pickup(row, openLane, distance));
            }
        }

        /// <summary>INV-5 as a function: no row blocks every lane.</summary>
        public static bool EveryRowLeavesALane(RunConfig cfg, IReadOnlyList<Hazard> hazards)
        {
            if (cfg == null) throw new ArgumentNullException(nameof(cfg));
            if (hazards == null) throw new ArgumentNullException(nameof(hazards));

            var blockedByRow = new Dictionary<int, HashSet<int>>();
            foreach (Hazard hazard in hazards)
            {
                if (!blockedByRow.TryGetValue(hazard.Row, out HashSet<int> lanes))
                {
                    lanes = new HashSet<int>();
                    blockedByRow[hazard.Row] = lanes;
                }
                lanes.Add(hazard.Lane);
            }

            foreach (KeyValuePair<int, HashSet<int>> row in blockedByRow)
                if (row.Value.Count >= cfg.LaneCount) return false;
            return true;
        }

        /// <summary>The first lane clear of hazards within <paramref name="lookAhead"/>, or -1.</summary>
        public static int FirstClearLane(RunSimulation sim, float lookAhead)
        {
            if (sim == null) throw new ArgumentNullException(nameof(sim));
            if (!sim.LaneBlockedWithin(sim.State.Lane, lookAhead)) return sim.State.Lane;
            for (int lane = 0; lane < sim.Config.LaneCount; lane++)
                if (!sim.LaneBlockedWithin(lane, lookAhead)) return lane;
            return -1;
        }
    }
}
