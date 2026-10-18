// Runs a deterministic fixed-step simulation on a background thread and hands the main thread a
// triple-buffered snapshot. Pure C#: no UnityEngine. Reference: unity-gameplay ->
// reference/sim-host-and-clock.md.
//
// Main thread, per frame, in this order:
//     clock.SyncExternalTime(Time.unscaledTimeAsDouble);
//     host.Pump();                         // no-op when threaded; steps the sim when not
//     var frame = host.SwapInLatest();     // the ONE call per frame; everyone else reads host.Current
//     while (host.TryDequeueEvent(out var e)) Handle(e);   // use e's own tick and position
//     draw at clock.RenderTicks
//
// Why a thread: the tick where something expensive happens (a shot solved, a trajectory predicted)
// can cost tens of milliseconds on a desktop Editor; on the main thread that is a dropped frame.
//
// Before constructing a host: run a throwaway warmup of the same code paths (Mono JITs a method
// the first time it runs, and the first expensive tick otherwise stalls the sim behind the clock),
// THEN clock.Restart(), THEN new SimHost(...). Warming up after the thread has started races it:
// the thread keeps stepping against the old clock while the warmup runs.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;

namespace Game.Sim.Hosting
{
    /// <summary>What the host needs from a simulation. Every member is called on the sim thread only.</summary>
    public interface IHostedSim<TCommand, TEvent, TSnapshot>
    {
        long Tick { get; }
        /// <summary>Apply a command at the current <see cref="Tick"/>. Record it here if you keep replays.</summary>
        void Apply(in TCommand command, long tick);
        /// <summary>Advance exactly one tick; append what happened to <paramref name="events"/>.</summary>
        void Step(List<TEvent> events);
        /// <summary>Copy everything the presentation reads into <paramref name="into"/>. No shared references.</summary>
        void CopyTo(TSnapshot into);
    }

    public sealed class SimHost<TCommand, TEvent, TSnapshot> : IDisposable
        where TSnapshot : class, new()
    {
        sealed class Slot { public readonly TSnapshot Data = new TSnapshot(); public long Tick; }

        readonly IHostedSim<TCommand, TEvent, TSnapshot> sim;
        readonly SimClock clock;
        readonly int maxCatchUpTicks;
        readonly ConcurrentQueue<TCommand> commands = new ConcurrentQueue<TCommand>();
        readonly ConcurrentQueue<TEvent> events = new ConcurrentQueue<TEvent>();
        readonly List<TEvent> stepEvents = new List<TEvent>();
        readonly object swap = new object();
        readonly AutoResetEvent wake = new AutoResetEvent(false);
        readonly Thread thread;
        Slot back = new Slot(), middle = new Slot(), front = new Slot();
        bool fresh;
        volatile bool stop;

        /// <summary>Set by the sim thread when the simulation threw. Stop the match and log it.</summary>
        public Exception Fault { get; private set; }

        /// <summary>The snapshot swapped in by the last <see cref="SwapInLatest"/>. Read this, not the sim.</summary>
        public TSnapshot Current => front.Data;
        /// <summary>The tick <see cref="Current"/> was copied at.</summary>
        public long CurrentTick => front.Tick;

        /// <summary>Largest (clock target − snapshot tick) seen while running.</summary>
        public long MaxLagTicks { get; private set; }
        /// <summary>Frames whose lag exceeded <see cref="LagThresholdTicks"/>: a smoke test asserts on this.</summary>
        public int LagFrames { get; private set; }
        public int LagThresholdTicks = 2;

        /// <param name="maxCatchUpTicks">Ticks one advance may run. After a stall the sim catches up over
        /// several advances instead of jumping a long stretch in one go.</param>
        /// <param name="threaded">false: the caller drives it with <see cref="Pump"/> (tests, single-threaded platforms).</param>
        public SimHost(IHostedSim<TCommand, TEvent, TSnapshot> sim, SimClock clock,
                       bool threaded = true, int maxCatchUpTicks = 16, string threadName = "Sim")
        {
            this.sim = sim ?? throw new ArgumentNullException(nameof(sim));
            this.clock = clock ?? throw new ArgumentNullException(nameof(clock));
            this.maxCatchUpTicks = Math.Max(1, maxCatchUpTicks);
            back.Tick = sim.Tick;
            sim.CopyTo(back.Data);
            Publish();
            SwapInLatest();
            if (!threaded) return;
            thread = new Thread(Run) { IsBackground = true, Name = threadName, Priority = ThreadPriority.AboveNormal };
            thread.Start();
        }

        // ───────────── main thread ─────────────

        /// <summary>Queue a command. It takes effect at the sim's current tick when the sim next drains.</summary>
        public void Post(in TCommand command)
        {
            commands.Enqueue(command);
            wake.Set();
        }

        /// <summary>
        /// Swap in the newest published snapshot and return it. Call it exactly ONCE per frame from one
        /// place: each call may hand the previous front buffer back to the sim thread, so a second caller
        /// in the same frame can get a different snapshot from the first, or invalidate what the first holds.
        /// Also records sim lag for this frame.
        /// </summary>
        public TSnapshot SwapInLatest()
        {
            lock (swap)
            {
                if (fresh)
                {
                    (front, middle) = (middle, front);
                    fresh = false;
                }
            }
            if (!clock.Paused)
            {
                long lag = clock.TargetTick - front.Tick;
                if (lag > MaxLagTicks) MaxLagTicks = lag;
                if (lag > LagThresholdTicks) LagFrames++;
            }
            return front.Data;
        }

        /// <summary>
        /// Events in the order they happened. An event can be up to <c>maxCatchUpTicks</c> older than
        /// <see cref="Current"/>: always use the tick and position the event carries, never the snapshot's.
        /// </summary>
        public bool TryDequeueEvent(out TEvent e) => events.TryDequeue(out e);

        /// <summary>Single-threaded mode: advance to the clock. Does nothing when threaded or stopped.</summary>
        public void Pump()
        {
            if (thread != null || stop) return;
            Advance();
        }

        /// <summary>Stop the sim thread and wait for it. After this the sim may be read (for example to serialise a replay).</summary>
        public void Stop(int joinMs = 500)
        {
            if (stop) return;
            stop = true;
            wake.Set();
            if (thread != null && !thread.Join(joinMs))
                throw new TimeoutException($"sim thread did not stop within {joinMs} ms");
        }

        /// <summary>Stops the thread; a thread that will not stop is reported through <see cref="Fault"/>, not thrown.</summary>
        public void Dispose()
        {
            try { Stop(); }
            catch (TimeoutException e) { Fault = e; return; }   // leave the handle for the stuck thread
            wake.Dispose();
        }

        // ───────────── sim thread ─────────────

        void Run()
        {
            try
            {
                while (!stop)
                {
                    Advance();
                    wake.WaitOne(2);   // a posted command wakes it early
                }
            }
            catch (Exception e)
            {
                Fault = e;
            }
        }

        void Advance()
        {
            long target = clock.TargetTick;
            bool changed = Drain();               // commands land on the current tick, before it steps
            int n = 0;
            while (sim.Tick < target && n < maxCatchUpTicks)
            {
                stepEvents.Clear();
                sim.Step(stepEvents);
                foreach (var e in stepEvents) events.Enqueue(e);
                n++;
                changed = true;
                changed |= Drain();
            }
            if (!changed) return;
            back.Tick = sim.Tick;
            sim.CopyTo(back.Data);
            Publish();
        }

        bool Drain()
        {
            bool any = false;
            while (commands.TryDequeue(out var c))
            {
                any = true;
                sim.Apply(c, sim.Tick);
            }
            return any;
        }

        void Publish()
        {
            lock (swap)
            {
                (back, middle) = (middle, back);
                fresh = true;
            }
        }
    }
}
