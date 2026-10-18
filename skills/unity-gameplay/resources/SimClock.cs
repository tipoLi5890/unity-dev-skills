// A match clock for a fixed-step simulation that runs on its own thread.
// Pure C#: no UnityEngine, so it compiles into a "noEngineReferences" assembly and runs in tests
// outside the Editor. Reference: unity-gameplay -> reference/sim-host-and-clock.md.
//
// Three rules it exists to enforce:
//   1. The target tick is computed from ABSOLUTE time: floor((now - start - paused) * rate).
//      Adding up per-frame dt drifts; this cannot.
//   2. It reads Stopwatch, which any thread may read. Time.unscaledTimeAsDouble is main-thread only,
//      so the main thread calls SyncExternalTime(Time.unscaledTimeAsDouble) once per frame and
//      ExternalToMatchUs converts device timestamps (which live on Unity's timeline) through that offset.
//   3. A timestamp is converted by subtracting only the pauses that ENDED BEFORE it. Subtracting the
//      total pause time instead makes a press made before a pause read early by the whole pause.
using System;
using System.Collections.Generic;
using System.Diagnostics;

namespace Game.Sim.Hosting
{
    public sealed class SimClock
    {
        static readonly double StopwatchToSeconds = 1.0 / Stopwatch.Frequency;

        /// <summary>Simulation ticks per second. 120 divides 60 and 30, so frames interpolate cleanly.</summary>
        public readonly int TickRate;

        readonly object gate = new object();
        readonly List<(double start, double end)> pauses = new List<(double, double)>();
        double startHost;
        double pausedTotal;
        double pausedAt = -1;
        double externalMinusHost;

        public SimClock(int tickRate = 120)
        {
            if (tickRate <= 0) throw new ArgumentOutOfRangeException(nameof(tickRate));
            TickRate = tickRate;
            Restart();
        }

        /// <summary>Seconds on the host timeline (Stopwatch). Safe from any thread.</summary>
        public static double HostNow => Stopwatch.GetTimestamp() * StopwatchToSeconds;

        /// <summary>Tick 0 is now. Call it AFTER any warmup, so the warmup's time is not match time.</summary>
        public void Restart()
        {
            lock (gate)
            {
                startHost = HostNow;
                pausedTotal = 0;
                pausedAt = -1;
                pauses.Clear();
            }
        }

        public bool Paused { get { lock (gate) return pausedAt >= 0; } }

        public void Pause()
        {
            lock (gate) if (pausedAt < 0) pausedAt = HostNow;
        }

        public void Resume()
        {
            lock (gate)
            {
                if (pausedAt < 0) return;
                double now = HostNow;
                pausedTotal += now - pausedAt;
                pauses.Add((pausedAt, now));
                pausedAt = -1;
            }
        }

        /// <summary>Match seconds elapsed, pauses excluded. Frozen while paused.</summary>
        public double MatchSeconds
        {
            get
            {
                lock (gate)
                {
                    double now = pausedAt >= 0 ? pausedAt : HostNow;
                    return now - startHost - pausedTotal;
                }
            }
        }

        /// <summary>Fractional ticks elapsed: the clock as the presentation should see it.</summary>
        public double MatchTicks => MatchSeconds * TickRate;

        /// <summary>The tick the simulation should have reached by now.</summary>
        public long TargetTick => (long)Math.Floor(MatchTicks);

        /// <summary>
        /// The tick the presentation draws: one tick behind the clock, so there is always a pair of
        /// states to interpolate between. Do NOT clamp this to the newest snapshot's tick: when the sim
        /// lags, clamping slows every time-based cue (a shrinking ring, a timing bar) and biases every
        /// press late against the real clock. Extrapolate the drawn object by at most a tick instead.
        /// </summary>
        public double RenderTicks => Math.Max(0.0, MatchTicks - 1.0);

        /// <summary>
        /// Main thread, once per frame: pass the timeline your device timestamps live on
        /// (in Unity, Time.unscaledTimeAsDouble). Records the offset to the host timeline.
        /// </summary>
        public void SyncExternalTime(double externalNowSeconds)
        {
            lock (gate) externalMinusHost = externalNowSeconds - HostNow;
        }

        /// <summary>
        /// A device timestamp on the external timeline, as match microseconds. Only pauses that had
        /// ended before the timestamp are subtracted; a timestamp inside a pause is pinned to the moment
        /// that pause began (input is refused while paused anyway). The result is on the same timeline
        /// as <see cref="MatchSeconds"/>, across any number of pauses.
        /// </summary>
        public long ExternalToMatchUs(double externalSeconds)
        {
            lock (gate)
            {
                double host = externalSeconds - externalMinusHost;
                if (pausedAt >= 0 && host > pausedAt) host = pausedAt;
                double before = 0;
                foreach (var (s, e) in pauses)
                {
                    if (e <= host) before += e - s;          // the whole pause happened earlier
                    else if (s < host) before += host - s;   // the stamp falls inside this pause
                }
                return SecondsToUs(host - startHost - before);
            }
        }

        public static long SecondsToUs(double s) => (long)Math.Round(s * 1_000_000.0);
        public long TickToUs(long tick) => (long)Math.Round(tick * 1_000_000.0 / TickRate);
        public long UsToTick(long us) => (long)Math.Floor(us * (double)TickRate / 1_000_000.0);
    }
}
