using System.Collections.Generic;
using System.Globalization;
using System.Text;
#if PERF_PROFILING_CORE
using Unity.Profiling;
using Unity.Profiling.LowLevel;   // ProfilerMarkerDataUnit
#endif

namespace UnityDev.Perf
{
    /// <summary>
    /// WorkCounter — count the work a system was asked to do, finished, and threw away.
    ///
    /// Frame time says a frame was slow. It never says the streamer loaded the same lane mesh
    /// four times because a selector flipped across a lane boundary. Three integers do:
    ///
    ///   scheduled  — the decision point said "do this"
    ///   completed  — the work finished and its result was used
    ///   discarded  — the work finished or was cancelled and the result was thrown away
    ///
    /// discarded climbing while scheduled climbs is churn: the frame cost is real and the
    /// player sees none of it. in-flight (scheduled - completed - discarded) sitting high and
    /// flat is a queue that never drains.
    ///
    /// Call the three methods at the decision points, not inside the worker. Then the numbers
    /// describe the policy, which is the thing you are about to change.
    ///
    ///   WorkCounter.Get("pickup-pool").Scheduled();
    ///   WorkCounter.Get("pickup-pool").Completed(bytes);
    ///   WorkCounter.Get("pickup-pool").Discarded();
    ///
    /// FrameSampler writes every registered counter into the window as
    /// "Game/&lt;system&gt;.scheduled" / ".completed" / ".discarded" with start, end and delta.
    ///
    /// Define PERF_PROFILING_CORE to also mirror the totals into ProfilerCounterValue&lt;long&gt;,
    /// which makes them visible in the Profiler window. That needs the profiling-core package;
    /// without the define this file has no package dependency at all.
    ///
    /// Main thread only. Call the methods from a job and the totals are wrong quietly.
    /// </summary>
    public sealed class WorkCounter
    {
        private static readonly Dictionary<string, WorkCounter> Registry =
            new Dictionary<string, WorkCounter>();
        private static readonly List<WorkCounter> Ordered = new List<WorkCounter>();

        public string System { get; private set; }

        public long ScheduledTotal { get; private set; }
        public long CompletedTotal { get; private set; }
        public long DiscardedTotal { get; private set; }
        public long BytesScheduled { get; private set; }
        public long BytesCompleted { get; private set; }

        /// <summary>Asked for but neither finished nor thrown away yet.</summary>
        public long InFlight { get { return ScheduledTotal - CompletedTotal - DiscardedTotal; } }

#if PERF_PROFILING_CORE
        private ProfilerCounterValue<long> _scheduled;
        private ProfilerCounterValue<long> _completed;
        private ProfilerCounterValue<long> _discarded;
#endif

        private WorkCounter(string system)
        {
            System = system;
#if PERF_PROFILING_CORE
            _scheduled = new ProfilerCounterValue<long>(
                ProfilerCategory.Scripts, system + ".scheduled",
                ProfilerMarkerDataUnit.Count, ProfilerCounterOptions.FlushOnEndOfFrame);
            _completed = new ProfilerCounterValue<long>(
                ProfilerCategory.Scripts, system + ".completed",
                ProfilerMarkerDataUnit.Count, ProfilerCounterOptions.FlushOnEndOfFrame);
            _discarded = new ProfilerCounterValue<long>(
                ProfilerCategory.Scripts, system + ".discarded",
                ProfilerMarkerDataUnit.Count, ProfilerCounterOptions.FlushOnEndOfFrame);
#endif
        }

        /// <summary>Get or create the counter for one system. Names become JSON keys, so keep
        /// them kebab-case and stable across changes — a renamed system compares as missing.</summary>
        public static WorkCounter Get(string system)
        {
            if (string.IsNullOrEmpty(system)) system = "unnamed";
            WorkCounter c;
            if (Registry.TryGetValue(system, out c)) return c;
            c = new WorkCounter(system);
            Registry.Add(system, c);
            Ordered.Add(c);
            return c;
        }

        /// <summary>Every counter created so far, in creation order.</summary>
        public static IList<WorkCounter> All { get { return Ordered; } }

        /// <summary>Zero every total. Call in a test [SetUp], or when entering a situation, so a
        /// window measures one run rather than the whole session.</summary>
        public static void ResetAll()
        {
            for (int i = 0; i < Ordered.Count; i++) Ordered[i].Reset();
        }

        public void Reset()
        {
            ScheduledTotal = 0;
            CompletedTotal = 0;
            DiscardedTotal = 0;
            BytesScheduled = 0;
            BytesCompleted = 0;
#if PERF_PROFILING_CORE
            _scheduled.Value = 0;
            _completed.Value = 0;
            _discarded.Value = 0;
#endif
        }

        /// <summary>The decision point chose to do this work. bytes is the size you expect to
        /// move, when the system knows it; 0 when it does not.</summary>
        public void Scheduled(long bytes = 0)
        {
            ScheduledTotal++;
            BytesScheduled += bytes;
#if PERF_PROFILING_CORE
            _scheduled.Value = ScheduledTotal;
#endif
        }

        /// <summary>The work finished and something used the result.</summary>
        public void Completed(long bytes = 0)
        {
            CompletedTotal++;
            BytesCompleted += bytes;
#if PERF_PROFILING_CORE
            _completed.Value = CompletedTotal;
#endif
        }

        /// <summary>The work was cancelled, superseded, or finished into a bin. Count it here
        /// even when it cost nothing — a cheap discard repeated every frame is still churn.</summary>
        public void Discarded()
        {
            DiscardedTotal++;
#if PERF_PROFILING_CORE
            _discarded.Value = DiscardedTotal;
#endif
        }

        public override string ToString()
        {
            return string.Format(CultureInfo.InvariantCulture,
                "{0} scheduled={1} completed={2} discarded={3} inFlight={4} bytesScheduled={5} bytesCompleted={6}",
                System, ScheduledTotal, CompletedTotal, DiscardedTotal, InFlight,
                BytesScheduled, BytesCompleted);
        }

        /// <summary>One line per system — cheap enough to log next to a [PERF] line, and the
        /// fastest way to see churn without opening a window.</summary>
        public static string Report()
        {
            var sb = new StringBuilder();
            for (int i = 0; i < Ordered.Count; i++)
            {
                if (i > 0) sb.Append('\n');
                sb.Append("[WORK] ").Append(Ordered[i].ToString());
            }
            return Ordered.Count == 0 ? "[WORK] no counters registered" : sb.ToString();
        }
    }
}
