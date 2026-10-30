// GameProbeReporter.cs — the [PROBE] log line for a run with no live Editor and no test. Lives in
// the same Runtime assembly as GameProbe.cs, whose state it writes. Attach to a boot object.
using UnityEngine;

/// <summary>
/// Writes one [PROBE] line to the log every N frames, so a run with no live Editor and no
/// test still leaves a readable trail. Attach to a boot object.
///
/// Gated on a development build: a release player logs nothing.
/// </summary>
public sealed class GameProbeReporter : MonoBehaviour
{
    [Tooltip("0 disables periodic logging; the reporter still answers Log() on demand.")]
    public int logEveryNFrames = 30;

    [Tooltip("Also log one line the frame the readiness set flips to complete.")]
    public bool logReadyTransition = true;

    bool _enabledHere;
    bool _wasReady;

    void Awake()
    {
        _enabledHere = Debug.isDebugBuild || Application.isEditor;
        if (!_enabledHere) enabled = false;
    }

    void Update()
    {
        if (!_enabledHere) return;

        if (logReadyTransition)
        {
            bool now = GameProbe.AllReady;
            if (now && !_wasReady) GameProbe.Log("PROBE");
            _wasReady = now;
        }

        if (logEveryNFrames > 0 && Time.frameCount % logEveryNFrames == 0)
            GameProbe.Log("PROBE");
    }
}
