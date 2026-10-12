// RunInput — the one struct gameplay reads, and the funnel every source of input goes through.
//
// Drop into a Runtime assembly beside the game. This file names no device and needs no package:
// RunInputReader.cs (the Input System) and ScriptedRunInput.cs (a journey test) both derive from
// RunInputSource here, so a key, a stick, a finger and a test all arrive through the same Press().
//
// The rule it exists to enforce: gameplay asks "was Launch pressed", never "is Space down".
//
//   Update        sources write: SetMove, SetAim, Press, SetHeld          (once per rendered frame)
//   FixedUpdate   gameplay reads: Peek for levels, TryUse for a press     (0..n times per frame)
//
// A press is latched with its time and stays pending until gameplay uses it or it ages out, so it
// survives a frame with no FixedUpdate and is spent once in a frame with four.
using System;
using System.Collections.Generic;
using UnityEngine;

public enum RunButton { Launch = 0, Interact = 1, Pause = 2 }

/// <summary>Which world plane the play field lies on: XY for a side or top-down 2D view, XZ for 3D ground.</summary>
public enum AimPlane { XY, XZ }

/// <summary>
/// One snapshot of intent. Levels (move, aim, held) describe now; the pressed flags describe a
/// press that is still pending — see <see cref="IRunInputSource"/> for who clears them.
/// </summary>
[Serializable]
public struct RunInput
{
    /// <summary>Movement on the play plane, magnitude 0..1. x is right; y is up (XY) or forward (XZ).</summary>
    public Vector2 move;
    /// <summary>Unit aim direction on the play plane, or zero when nothing is aiming — keep the last facing.</summary>
    public Vector2 aim;
    /// <summary>True when a pointer produced the aim, and <see cref="aimPoint"/> is the world point under it.</summary>
    public bool hasAimPoint;
    public Vector3 aimPoint;

    public bool launchPressed;
    public bool launchHeld;
    public bool interactPressed;
    public bool pausePressed;

    public bool Pressed(RunButton button)
    {
        switch (button)
        {
            case RunButton.Launch: return launchPressed;
            case RunButton.Interact: return interactPressed;
            default: return pausePressed;
        }
    }
}

public interface IRunInputSource
{
    /// <summary>False once the source is disabled or destroyed — the cue to resolve again.</summary>
    bool IsActive { get; }

    /// <summary>Levels plus pending presses. Clears nothing — for cameras, UI and anything in Update.</summary>
    RunInput Peek();

    /// <summary>
    /// The same snapshot, and every press in it is spent: the next call returns it false. For a
    /// consumer that acts on a press now or not at all.
    /// </summary>
    RunInput Consume();

    /// <summary>
    /// Spend one pending press. True exactly once per press, and only while the press is younger
    /// than the buffer — the form to use when gameplay may have to wait: <c>grounded &amp;&amp; TryUse(Launch)</c>.
    /// </summary>
    bool TryUse(RunButton button);

    /// <summary>Drop every pending press. Call it when a pause or a menu closes.</summary>
    void ClearPresses();
}

/// <summary>
/// Pending presses with the time each one happened. Plain C#, clock passed in, so it is testable
/// without a scene. Two presses of one button before the first is used collapse into one.
/// </summary>
public sealed class RunPressLatch
{
    const int Buttons = 3;
    readonly bool[] _pending = new bool[Buttons];
    readonly float[] _pressedAt = new float[Buttons];
    readonly bool[] _held = new bool[Buttons];

    public void Press(RunButton button, float now)
    {
        int i = (int)button;
        _pending[i] = true;
        _pressedAt[i] = now;
        _held[i] = true;
    }

    public void SetHeld(RunButton button, bool held) => _held[(int)button] = held;
    public bool Held(RunButton button) => _held[(int)button];

    /// <summary>A press exists and is no older than <paramref name="window"/> seconds.</summary>
    public bool Pending(RunButton button, float now, float window)
    {
        int i = (int)button;
        if (!_pending[i]) return false;
        if (now - _pressedAt[i] <= window) return true;
        _pending[i] = false;   // aged out: a late landing must not fire a stale press
        return false;
    }

    public bool TryUse(RunButton button, float now, float window)
    {
        if (!Pending(button, now, window)) return false;
        _pending[(int)button] = false;
        return true;
    }

    public void Clear()
    {
        for (int i = 0; i < Buttons; i++) _pending[i] = false;
    }
}

/// <summary>
/// The funnel. A source derives from this and only ever calls the protected and public writers
/// below; gameplay holds it as an <see cref="IRunInputSource"/>.
/// </summary>
public abstract class RunInputSource : MonoBehaviour, IRunInputSource
{
    [Tooltip("How long a press stays usable, in game seconds. 0.10–0.15 forgives an early jump; 0 means 'this fixed step or never'.")]
    public float bufferSeconds = 0.12f;

    readonly RunPressLatch _latch = new RunPressLatch();
    readonly int[] _sent = new int[3];
    RunInput _levels;

    public bool IsActive => this != null && isActiveAndEnabled;

    /// <summary>How many presses this source has latched since it was enabled — a probe count.</summary>
    public int Sent(RunButton button) => _sent[(int)button];

    // Game time, not unscaled: the consumer runs in FixedUpdate, which slows with timeScale, and a
    // buffer on the wall clock would expire between two slow-motion steps. In FixedUpdate this
    // reads fixedTime, which is what the press is compared against.
    static float Now => Time.time;

    // Never shorter than one fixed step, or a press could age out before any FixedUpdate saw it.
    float Window => Mathf.Max(bufferSeconds, Time.fixedDeltaTime) + 1e-4f;

    public void Press(RunButton button)
    {
        _latch.Press(button, Now);
        _sent[(int)button]++;
    }

    public void SetHeld(RunButton button, bool held) => _latch.SetHeld(button, held);

    public void SetMove(Vector2 move) => _levels.move = Vector2.ClampMagnitude(move, 1f);

    /// <summary>Aim from a stick: a direction, no world point.</summary>
    public void SetAim(Vector2 direction)
    {
        _levels.aim = direction.sqrMagnitude > 1e-6f ? direction.normalized : Vector2.zero;
        _levels.hasAimPoint = false;
    }

    /// <summary>Aim from a pointer: the world point under it, and the direction from the origin to it.</summary>
    public void SetAimPoint(Vector3 worldPoint, Vector3 origin, AimPlane plane)
    {
        Vector3 d = worldPoint - origin;
        Vector2 onPlane = plane == AimPlane.XY ? new Vector2(d.x, d.y) : new Vector2(d.x, d.z);
        _levels.aim = onPlane.sqrMagnitude > 1e-6f ? onPlane.normalized : Vector2.zero;
        _levels.aimPoint = worldPoint;
        _levels.hasAimPoint = true;
    }

    public RunInput Peek()
    {
        RunInput s = _levels;
        float now = Now, window = Window;
        s.launchPressed = _latch.Pending(RunButton.Launch, now, window);
        s.interactPressed = _latch.Pending(RunButton.Interact, now, window);
        s.pausePressed = _latch.Pending(RunButton.Pause, now, window);
        s.launchHeld = _latch.Held(RunButton.Launch);
        return s;
    }

    public RunInput Consume()
    {
        RunInput s = Peek();
        _latch.Clear();
        return s;
    }

    public bool TryUse(RunButton button) => _latch.TryUse(button, Now, Window);

    public void ClearPresses() => _latch.Clear();

    protected virtual void OnDisable()
    {
        // A disabled source must not leave a held button or a pending press behind for whoever
        // reads it next — that is how a jump fires on the frame a menu closes.
        _latch.Clear();
        _latch.SetHeld(RunButton.Launch, false);
        _latch.SetHeld(RunButton.Interact, false);
        _latch.SetHeld(RunButton.Pause, false);
        _levels = default;
    }

    static readonly List<RunInputSource> s_Found = new List<RunInputSource>();

    /// <summary>The enabled source on a GameObject, or null.</summary>
    public static IRunInputSource On(GameObject host)
    {
        host.GetComponents(s_Found);
        foreach (RunInputSource s in s_Found)
            if (s.isActiveAndEnabled) return s;
        return null;
    }

    /// <summary>
    /// Keep <paramref name="source"/> pointing at the enabled source on <paramref name="host"/>.
    /// Gameplay calls this at the top of its fixed step instead of caching once in Awake: a
    /// journey that adds a ScriptedRunInput to a live runner and disables the reader is then
    /// picked up on the next step, and the controller never learns which one it got. False when
    /// no source is enabled — there is nothing to read.
    /// </summary>
    public static bool Resolve(GameObject host, ref IRunInputSource source)
    {
        if (source != null && source.IsActive) return true;
        source = On(host);
        return source != null;
    }
}

/// <summary>Pointer position to a point on the play plane. No physics: a plane, not a collider.</summary>
public static class RunAim
{
    /// <param name="planeOffset">The plane's position along its normal: z for XY, y for XZ.</param>
    public static bool PointOnPlane(Camera camera, Vector2 screen, AimPlane plane, float planeOffset,
                                    out Vector3 world)
    {
        world = default;
        if (camera == null) return false;
        Vector3 normal = plane == AimPlane.XY ? Vector3.forward : Vector3.up;
        var surface = new Plane(normal, normal * planeOffset);
        Ray ray = camera.ScreenPointToRay(new Vector3(screen.x, screen.y, 0f));
        // Enter is negative when the plane is behind the camera, and the ray is parallel when an
        // orthographic camera looks along the plane — both mean there is no point to aim at.
        if (!surface.Raycast(ray, out float enter)) return false;
        world = ray.GetPoint(enter);
        return true;
    }
}

/// <summary>
/// Turns a held direction into discrete steps: one at once, a pause, then a steady repeat. For a
/// cell-stepped mover in the sorting yard. Plain C#; feed it <see cref="RunInput.move"/> each
/// fixed step with the same clock.
/// </summary>
public sealed class StepRepeater
{
    public float initialDelay = 0.25f;
    public float interval = 0.10f;
    /// <summary>Below this the stick is resting. High on purpose: a diagonal must not flicker between two axes.</summary>
    public float threshold = 0.5f;

    Vector2Int _last;
    float _nextAt;

    public bool Step(Vector2 move, float now, out Vector2Int direction)
    {
        direction = Quantise(move);
        if (direction == Vector2Int.zero) { _last = direction; return false; }
        if (direction != _last)
        {
            _last = direction;
            _nextAt = now + initialDelay;
            return true;
        }
        if (now < _nextAt) return false;
        _nextAt = now + interval;
        return true;
    }

    public void Reset() => _last = Vector2Int.zero;

    Vector2Int Quantise(Vector2 move)
    {
        float ax = Mathf.Abs(move.x), ay = Mathf.Abs(move.y);
        if (Mathf.Max(ax, ay) < threshold) return Vector2Int.zero;
        // The dominant axis wins; four directions, never a diagonal step.
        return ax >= ay ? new Vector2Int(move.x > 0f ? 1 : -1, 0) : new Vector2Int(0, move.y > 0f ? 1 : -1);
    }
}
