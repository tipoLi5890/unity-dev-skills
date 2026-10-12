// ScriptedRunInput — the input source a journey test drives, frame by frame.
//
// Drop into the same Runtime assembly as RunInput.cs. No package needed. Add it to the object
// that carries the game's RunInputReader and disable the reader; gameplay that keeps its source
// through RunInputSource.Resolve(gameObject, ref _input) reads the script from its next fixed
// step. A controller that cached the reader once in Awake keeps reading the disabled reader, and
// the journey then samples a game nobody is playing — assert Sent() moved a probe value.
//
// It goes through the same Press / SetMove / SetAim as the reader, so the latch, the buffer and
// the consume-once rule under test are the ones the player gets. What it skips is the device and
// the action asset — cover those with the Input System's InputTestFixture when a binding is the
// thing in doubt.
using System.Collections.Generic;
using UnityEngine;

[AddComponentMenu("Courier/Scripted Run Input")]
[DefaultExecutionOrder(-100)]   // queued steps land before any gameplay Update reads them
public sealed class ScriptedRunInput : RunInputSource
{
    struct Step
    {
        public int frame;
        public RunButton button;
        public bool hold;
    }

    readonly List<Step> _queue = new List<Step>();
    readonly int[] _rawFrame = { -1, -1, -1 };

    /// <summary>Press and release in this frame — the shortest press a device can make.</summary>
    public void Tap(RunButton button)
    {
        Press(button);
        SetHeld(button, false);
        _rawFrame[(int)button] = Time.frameCount;
    }

    /// <summary>Press and keep holding until <see cref="Release"/>.</summary>
    public void Hold(RunButton button)
    {
        Press(button);
        _rawFrame[(int)button] = Time.frameCount;
    }

    public void Release(RunButton button) => SetHeld(button, false);

    /// <summary>Schedule a tap for the Update that runs <paramref name="framesFromNow"/> frames ahead.</summary>
    public void TapIn(int framesFromNow, RunButton button)
        => _queue.Add(new Step { frame = Time.frameCount + Mathf.Max(1, framesFromNow), button = button });

    public void HoldIn(int framesFromNow, RunButton button)
        => _queue.Add(new Step { frame = Time.frameCount + Mathf.Max(1, framesFromNow), button = button, hold = true });

    public int Queued => _queue.Count;

    /// <summary>
    /// What polling the device would say. The Input System updates once per rendered frame, just
    /// before Update, so a press reads as "this frame" from that Update until the next one — which
    /// includes every FixedUpdate of the following frame, however many or few there are. It is
    /// here so a test can count what a FixedUpdate poll would have seen, next to what the latch
    /// delivered. Gameplay never calls it.
    /// </summary>
    public bool RawPressedThisFrame(RunButton button)
    {
        int pressed = _rawFrame[(int)button];
        return Time.inFixedTimeStep ? pressed == Time.frameCount - 1 : pressed == Time.frameCount;
    }

    void Update()
    {
        for (int i = _queue.Count - 1; i >= 0; i--)
        {
            if (_queue[i].frame > Time.frameCount) continue;
            Step s = _queue[i];
            _queue.RemoveAt(i);
            if (s.hold) Hold(s.button); else Tap(s.button);
        }
    }

    protected override void OnDisable()
    {
        _queue.Clear();
        base.OnDisable();
    }
}
