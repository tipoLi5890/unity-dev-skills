// CameraProbe.cs — three camera facts on GameProbe: is the player on screen, is the
// camera inside its bounds, and where the camera sits relative to the player.
//
// Drop into the Runtime assembly that holds GameProbe.cs (unity-play-harness →
// resources/GameProbe.cs) and attach to any object in the scene.
//
// REQUIRES nothing beyond the engine. No Cinemachine type is referenced, so it reads a
// 2.x rig, a 3.x rig and a hand-written follow script alike.
//
//   custom.camViewport   bool      the player is inside the viewport, margin applied
//   custom.camInBounds   bool|null every corner of the view is inside the bounds; null with no bounds set
//   custom.camOffset     [x,y,z]   camera position minus player position, world units
//
// scripts/camera_jitter.py reads camOffset from a recorded timeline; CameraAsserts.FlipRate
// below is the same measure inside a PlayMode test.
using System;
using System.Collections.Generic;
using UnityEngine;

// Latches after every camera driver has run. The Cinemachine Brain sits at execution order
// 100; a journey samples from a coroutine, which resumes before LateUpdate. Reading the
// two transforms at sample time would pair this frame's player with last frame's camera —
// the probe itself would be the second clock, and it would report jitter in a clean rig.
[DefaultExecutionOrder(10000)]
public sealed class CameraProbe : MonoBehaviour
{
    [Tooltip("The object the camera is meant to keep on screen.")]
    public Transform player;

    [Tooltip("The output camera. Empty means Camera.main, resolved every frame.")]
    public Camera outputCamera;

    [Tooltip("Fraction of the viewport, per edge, that still counts as off screen. 0.02 = 2 %.")]
    [Range(0f, 0.45f)] public float viewportMargin = 0f;

    [Tooltip("World units the view may poke past the bounds before camInBounds reads false.")]
    public float boundsTolerance = 0.05f;

    /// <summary>The player was inside the viewport at the end of the last frame.</summary>
    public bool PlayerInViewport { get; private set; }

    /// <summary>Null until bounds are set; then whether the whole view was inside them.</summary>
    public bool? InBounds { get; private set; }

    /// <summary>Camera position minus player position at the end of the last frame.</summary>
    public Vector3 Offset { get; private set; }

    Func<Vector3, bool> _contains;
    int _latchedFrame = -1;

    /// <summary>
    /// The room test, as a delegate so the probe needs no physics module and cannot go stale:
    ///   probe.SetBounds(p => confiner.BoundingShape2D.OverlapPoint(p));   // 2D room
    ///   probe.SetBounds(p => volume.ClosestPoint(p) == p);                // 3D volume
    /// Pass null to drop the bounds; camInBounds then reads null.
    /// </summary>
    public void SetBounds(Func<Vector3, bool> contains) { _contains = contains; }

    void OnEnable()
    {
        GameProbe.Register("camViewport", () => { EnsureLatched(); return PlayerInViewport; });
        GameProbe.Register("camInBounds", () => { EnsureLatched(); return InBounds.HasValue ? (object)InBounds.Value : null; });
        GameProbe.Register("camOffset", () => { EnsureLatched(); return Offset; });
    }

    void OnDisable()
    {
        // Unregister rather than keep answering: a key that disappears is visible in the
        // timeline, a key frozen at its last value is not.
        GameProbe.Unregister("camViewport");
        GameProbe.Unregister("camInBounds");
        GameProbe.Unregister("camOffset");
    }

    void LateUpdate() { Latch(); }

    // Only the first read after enabling can arrive before a LateUpdate has run.
    void EnsureLatched() { if (_latchedFrame < 0) Latch(); }

    void Latch()
    {
        _latchedFrame = Time.frameCount;
        Camera cam = outputCamera != null ? outputCamera : Camera.main;
        if (cam == null || player == null)
        {
            PlayerInViewport = false;
            InBounds = null;
            Offset = Vector3.zero;
            return;
        }

        Vector3 camPos = cam.transform.position;
        Vector3 playerPos = player.position;
        Offset = camPos - playerPos;

        Vector3 vp = cam.WorldToViewportPoint(playerPos);
        float m = viewportMargin;
        PlayerInViewport = vp.z > 0f && vp.x >= m && vp.x <= 1f - m && vp.y >= m && vp.y <= 1f - m;

        InBounds = _contains == null ? (bool?)null : ViewInside(cam, playerPos);
    }

    bool ViewInside(Camera cam, Vector3 playerPos)
    {
        Transform t = cam.transform;
        if (!cam.orthographic)
            return _contains(t.position);          // a perspective camera is confined as a point

        // The view rectangle on the plane the player stands on, pulled in by the tolerance so
        // a camera resting exactly on the edge does not flicker between true and false.
        float halfH = Mathf.Max(0f, cam.orthographicSize - boundsTolerance);
        float halfW = Mathf.Max(0f, cam.orthographicSize * cam.aspect - boundsTolerance);
        float depth = Vector3.Dot(playerPos - t.position, t.forward);
        Vector3 centre = t.position + t.forward * depth;
        Vector3 right = t.right * halfW;
        Vector3 up = t.up * halfH;
        return _contains(centre - right - up) && _contains(centre + right - up)
            && _contains(centre - right + up) && _contains(centre + right + up);
    }
}

/// <summary>
/// Invariants over a recorded journey that are about the camera. They return numbers and
/// violations rather than asserting, so this file stays in a Runtime assembly.
/// </summary>
public static class CameraAsserts
{
    /// <summary>
    /// How often the camera-to-player offset changes direction from one frame to the next.
    /// A camera easing after its target moves the offset one way for many frames; two update
    /// clocks beating against each other move it back and forth every few frames.
    ///
    /// axis: 0 = x, 1 = y, 2 = z. Deltas smaller than epsilon are rest, not motion, and are
    /// skipped. rate = flips / (moving - 1); fewer than minMoving moving deltas reads as 0,
    /// because three frames of motion cannot show a pattern.
    /// </summary>
    public static float FlipRate(IList<ProbeSnapshot> samples, int axis, out int flips, out int moving,
                                 float epsilon = 0.002f, int minMoving = 10, string key = "camOffset")
    {
        flips = 0;
        moving = 0;
        bool havePrev = false;
        float prev = 0f;
        int lastSign = 0;
        for (int i = 0; i < samples.Count; i++)
        {
            ProbeSnapshot s = samples[i];
            if (!(s.CustomOf(key) is Vector3 v) || s.dt <= 0f) continue;   // paused frames carry no motion
            float value = v[axis];
            if (havePrev)
            {
                float d = value - prev;
                if (Mathf.Abs(d) >= epsilon)
                {
                    int sign = d > 0f ? 1 : -1;
                    if (lastSign != 0 && sign != lastSign) flips++;
                    lastSign = sign;
                    moving++;
                }
            }
            prev = value;
            havePrev = true;
        }
        return moving < Mathf.Max(2, minMoving) ? 0f : flips / (float)(moving - 1);
    }

    /// <summary>Samples where a bool the probe registered was not true. A missing key counts:
    /// a probe that was never attached must not read as a camera that behaved.</summary>
    public static List<JourneyViolation> AlwaysTrue(IList<ProbeSnapshot> samples, string key)
    {
        return JourneyAsserts.Never(samples, s => !(s.CustomOf(key) is bool b) || !b, key);
    }
}
