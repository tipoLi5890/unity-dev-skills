using UnityEngine;

namespace UnityDev.Perf
{
    /// <summary>Opens GcAllocProbe's window at the start of Update and LateUpdate. Added by
    /// GcAllocProbe.Attach; not used on its own. Kept in its own file so the execution order applies.</summary>
    [DefaultExecutionOrder(-32000)]
    public sealed class GcAllocProbeOpener : MonoBehaviour
    {
        internal GcAllocProbe Probe;
        void Update() { if (Probe != null) Probe.Open(false); }
        void LateUpdate() { if (Probe != null) Probe.Open(true); }
    }
}
