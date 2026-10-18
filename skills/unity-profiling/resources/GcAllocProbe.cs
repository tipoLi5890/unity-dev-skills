using UnityEngine;
using UnityEngine.Profiling;

namespace UnityDev.Perf
{
    /// <summary>
    /// GcAllocProbe — which frames allocate in the Update phase, and which in the LateUpdate phase,
    /// on the main thread, counted by the Profiler's own "GC.Alloc" sample. No Profiler window, no
    /// package; works in the Editor, in PlayMode tests and in a development player.
    ///
    /// Why not GC.GetAllocatedBytesForCurrentThread: under Unity's Mono it is not implemented and
    /// returns 0 for ever, so a test built on it passes while measuring nothing. The "GC Allocated
    /// In Frame" counter (CounterCatalog) gives bytes for the whole frame but cannot say which phase
    /// allocated. This probe answers the phase question, which is the one that names the owner:
    /// in a game whose presentation runs in LateUpdate, "LateUpdate allocates" is the view's bug,
    /// "Update allocates" is the simulation's or the input's.
    ///
    /// How: a Recorder on the "GC.Alloc" marker, filtered to the main thread, is enabled only inside
    /// one phase per frame. Odd frames gate the Update phase, even frames the LateUpdate phase: the
    /// opener runs at execution order −32000, the closer at +32000. A Recorder reports the previous
    /// frame, so each frame's count is read at the start of the next. Coroutines and test code that
    /// run between Update and LateUpdate are outside both windows.
    ///
    /// Copy GcAllocProbeOpener.cs with it: Unity takes [DefaultExecutionOrder] from the script asset,
    /// so each MonoBehaviour lives in a file of its own name.
    ///
    /// Prove it can see an allocation before trusting a zero: Calibrate() makes the probe allocate
    /// 64 bytes inside its own next window; CalibrationSeen must come back ≥ 1. Arrays are allocated
    /// once in Attach; recording allocates nothing.
    ///
    ///   var probe = GcAllocProbe.Attach();          // before entering the situation
    ///   probe.Calibrate();  yield return null; yield return null; yield return null;
    ///   Assert.GreaterOrEqual(probe.CalibrationSeen, 1, "GC.Alloc recorder is blind");
    ///   probe.ResetSamples(); probe.Recording = true;
    ///   yield return new WaitForSeconds(8);
    ///   probe.Recording = false;
    ///   Debug.Log(probe.Summary());                  // [GC] LateUpdate frames with alloc 3/420 …
    ///   Assert.LessOrEqual(probe.LateFramesWithAlloc, probe.LateFrames / 20);
    ///
    /// Worked numbers: a tennis game's presentation layer went from allocating in 419 of 419
    /// LateUpdate frames (per-frame string building in the HUD, new lists in the effects) to 3 or 4
    /// of about 420; its test allows 5%.
    /// </summary>
    [DefaultExecutionOrder(32000)]
    public sealed class GcAllocProbe : MonoBehaviour
    {
        public const int Capacity = 8192;

        /// <summary>Allocation calls in the gated phase of frame i; −1 when that frame gated the other phase.</summary>
        public readonly int[] UpdateAllocs = new int[Capacity];
        public readonly int[] LateAllocs = new int[Capacity];
        public int Count;
        public bool Recording;

        /// <summary>Allocation calls seen in the calibration window; −1 until it has been read.</summary>
        public int CalibrationSeen = -1;

        public int UpdateFrames, UpdateFramesWithAlloc, UpdateTotal;
        public int LateFrames, LateFramesWithAlloc, LateTotal, LateMax;

        Recorder rec;
        bool gateLate, lastGateLate;
        bool calibrateNext;
        int calibFrame = -1;
        GcAllocProbeOpener opener;

        public static GcAllocProbe Attach()
        {
            var go = new GameObject("GcAllocProbe");
            DontDestroyOnLoad(go);
            var p = go.AddComponent<GcAllocProbe>();
            p.opener = go.AddComponent<GcAllocProbeOpener>();
            p.opener.Probe = p;
            return p;
        }

        public void Calibrate() { calibrateNext = true; CalibrationSeen = -1; }

        public void ResetSamples()
        {
            Count = 0;
            UpdateFrames = UpdateFramesWithAlloc = UpdateTotal = 0;
            LateFrames = LateFramesWithAlloc = LateTotal = LateMax = 0;
        }

        public string Summary() =>
            $"[GC] LateUpdate frames with alloc {LateFramesWithAlloc}/{LateFrames} (calls {LateTotal}, max {LateMax}/frame); " +
            $"Update frames with alloc {UpdateFramesWithAlloc}/{UpdateFrames} (calls {UpdateTotal}); calibration seen {CalibrationSeen}";

        internal void Open(bool late)
        {
            if (rec == null)
            {
                rec = Recorder.Get("GC.Alloc");
                rec.FilterToCurrentThread();
                rec.enabled = false;
            }
            if (!late)
            {
                // Start of a frame: the recorder now reports the previous frame's gated window.
                int seen = rec.isValid ? rec.sampleBlockCount : -1;
                if (calibFrame >= 0 && Time.frameCount == calibFrame + 1) { CalibrationSeen = seen; calibFrame = -1; }
                else if (Recording && seen >= 0 && Count > 0) Store(Count - 1, seen, lastGateLate);
                if (Recording && Count < Capacity) { UpdateAllocs[Count] = -1; LateAllocs[Count] = -1; Count++; }
                lastGateLate = gateLate = (Time.frameCount & 1) == 0;
            }
            if (late != gateLate) return;
            rec.enabled = true;
            if (calibrateNext) { calibrateNext = false; calibFrame = Time.frameCount; System.GC.KeepAlive(new byte[64]); }
        }

        void Store(int i, int seen, bool late)
        {
            if (late)
            {
                LateAllocs[i] = seen; LateFrames++; LateTotal += seen;
                if (seen > 0) LateFramesWithAlloc++;
                if (seen > LateMax) LateMax = seen;
            }
            else
            {
                UpdateAllocs[i] = seen; UpdateFrames++; UpdateTotal += seen;
                if (seen > 0) UpdateFramesWithAlloc++;
            }
        }

        void Close(bool late) { if (rec != null && late == gateLate) rec.enabled = false; }

        void Update() => Close(false);
        void LateUpdate() => Close(true);

        void OnDestroy() { if (rec != null) rec.enabled = false; }
    }
}
