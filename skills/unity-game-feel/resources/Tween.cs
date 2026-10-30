// Tween.cs — a small tween runner with easing, a squash-and-stretch helper and a spring. No
// third-party library, and no allocation after start-up: tweens are structs in a fixed array.
//
// Drop into a Runtime assembly. No package needed. Nothing has to be placed in a scene: the
// first tween creates a hidden runner. Place one Tween component in the boot scene only to
// change the capacity.
//
//   Tween.Scale(visual, Vector3.one, 0.12f, Ease.OutBack);
//   Tween.MoveLocal(visual, Vector3.zero, 0.12f, Ease.OutCubic);
//   Tween.Squash(visual, restScale, 0.8f, 0.12f, false);         // land: 80 % tall, then back
//   Tween.Value(light, 2f, 0f, 0.2f, Ease.OutQuad, (target, v) => ((Light)target).intensity = v);
//
// Tween a child that only draws — the sprite or the mesh — never the object that carries the
// body or the collider: scaling a collider changes what the runner can stand on.
//
// Value() takes its target as an argument so the lambda captures nothing; a lambda that
// captures a local allocates a closure on every call.
//
// Everything here is in namespace UnityDev.GameFeel (`using UnityDev.GameFeel;`), so `Tween` and
// `Ease` never collide with a tween library's types of the same name in the same project.
using System;
using UnityEngine;

namespace UnityDev.GameFeel
{
    public enum Ease
    {
        Linear,
        InQuad, OutQuad, InOutQuad,
        InCubic, OutCubic, InOutCubic,
        OutBack,        // overshoots the end by about 10 % and settles: arrivals, pop-ins
        OutElastic,     // rings past the end three times: a pickup counter, never a character
        OutBounce,
    }

    public static class Easing
    {
        /// <summary>t in 0..1 to a progress that starts at 0 and ends at 1. OutBack and OutElastic pass 1 on the way.</summary>
        public static float Evaluate(Ease ease, float t)
        {
            t = Mathf.Clamp01(t);
            switch (ease)
            {
                case Ease.InQuad: return t * t;
                case Ease.OutQuad: return 1f - (1f - t) * (1f - t);
                case Ease.InOutQuad: return t < 0.5f ? 2f * t * t : 1f - 2f * (1f - t) * (1f - t);
                case Ease.InCubic: return t * t * t;
                case Ease.OutCubic: { float u = 1f - t; return 1f - u * u * u; }
                case Ease.InOutCubic: { float u = 1f - t; return t < 0.5f ? 4f * t * t * t : 1f - 4f * u * u * u; }
                case Ease.OutBack:
                {
                    const float c1 = 1.70158f, c3 = c1 + 1f;
                    float u = t - 1f;
                    return 1f + c3 * u * u * u + c1 * u * u;
                }
                case Ease.OutElastic:
                {
                    if (t <= 0f) return 0f;
                    if (t >= 1f) return 1f;
                    return Mathf.Pow(2f, -10f * t) * Mathf.Sin((t * 10f - 0.75f) * (2f * Mathf.PI / 3f)) + 1f;
                }
                case Ease.OutBounce:
                {
                    const float n = 7.5625f, d = 2.75f;
                    if (t < 1f / d) return n * t * t;
                    if (t < 2f / d) { t -= 1.5f / d; return n * t * t + 0.75f; }
                    if (t < 2.5f / d) { t -= 2.25f / d; return n * t * t + 0.9375f; }
                    t -= 2.625f / d;
                    return n * t * t + 0.984375f;
                }
                default: return t;
            }
        }
    }

    /// <summary>A tween that may already be over. Safe to keep, copy and call after the tween has gone.</summary>
    public struct TweenHandle
    {
        internal int slot;
        internal int id;

        public bool IsAlive => Tween.Alive(this);
        /// <summary>Stop where it is.</summary>
        public void Cancel() => Tween.Stop(this, false);
        /// <summary>Jump to the end value, then stop.</summary>
        public void Complete() => Tween.Stop(this, true);
    }

    /// <summary>
    /// A damped spring for motion that has to react to a moving target — a follow offset, a recoil,
    /// a bar that chases its value. Frequency in oscillations per second; damping 1 arrives without
    /// overshoot, 0.5 overshoots once, 0.2 rings. The integrator is implicit, so a long frame cannot
    /// make it explode.
    /// </summary>
    [Serializable]
    public struct Spring
    {
        public float value;
        public float velocity;

        public float Step(float target, float frequency, float damping, float dt)
        {
            if (dt <= 0f) return value;
            float w = frequency * 2f * Mathf.PI;
            float f = 1f + 2f * dt * damping * w;
            float hww = dt * w * w;
            float hhww = dt * hww;
            float inv = 1f / (f + hhww);
            float x = (f * value + dt * velocity + hhww * target) * inv;
            velocity = (velocity + hww * (target - value)) * inv;
            value = x;
            return value;
        }

        /// <summary>Kick it: a hit adds velocity and the spring brings the value back by itself.</summary>
        public void Push(float impulse) => velocity += impulse;
    }

    [AddComponentMenu("Courier/Tween Runner")]
    public sealed class Tween : MonoBehaviour
    {
        [Tooltip("Tweens alive at once. One over this is refused and counted in Dropped, never allocated.")]
        public int capacity = 64;

        enum Kind { Free, Scale, LocalPosition, Position, Value }

        struct Slot
        {
            public int id;
            public Kind kind;
            public Transform transform;
            public object target;
            public Action<object, float> apply;
            public Vector3 from, to;
            public float elapsed, duration;
            public Ease ease;
            public bool unscaled;
            public bool hasTarget;
        }

        static Tween _instance;
        static bool _quitting;
        static int _nextId = 1;

        Slot[] _slots;

        /// <summary>Tweens running now.</summary>
        public static int Running { get; private set; }

        /// <summary>Tweens refused because every slot was in use.</summary>
        public static int Dropped { get; private set; }

        // ------------------------------------------------------------------------------ the API

        public static TweenHandle Scale(Transform t, Vector3 to, float seconds, Ease ease = Ease.OutQuad, bool unscaled = false)
            => t != null ? Begin(Kind.Scale, t, t.localScale, to, seconds, ease, unscaled) : default;

        public static TweenHandle MoveLocal(Transform t, Vector3 to, float seconds, Ease ease = Ease.OutQuad, bool unscaled = false)
            => t != null ? Begin(Kind.LocalPosition, t, t.localPosition, to, seconds, ease, unscaled) : default;

        public static TweenHandle Move(Transform t, Vector3 to, float seconds, Ease ease = Ease.OutQuad, bool unscaled = false)
            => t != null ? Begin(Kind.Position, t, t.position, to, seconds, ease, unscaled) : default;

        /// <summary>
        /// Set the scale to a squashed (y under 1) or stretched (y over 1) shape now and ease back to
        /// <paramref name="rest"/>. Volume is kept: in 3D the other two axes take 1/sqrt(y), in 2D
        /// the one visible axis takes 1/y. The transform's pivot must be at the feet, or the
        /// squash lifts the soles off the ground.
        /// </summary>
        public static TweenHandle Squash(Transform t, Vector3 rest, float y, float seconds, bool is2D,
                                         Ease ease = Ease.OutBack, bool unscaled = false)
        {
            if (t == null) return default;
            y = Mathf.Max(0.05f, y);
            float side = is2D ? 1f / y : 1f / Mathf.Sqrt(y);
            t.localScale = new Vector3(rest.x * side, rest.y * y, is2D ? rest.z : rest.z * side);
            return Begin(Kind.Scale, t, t.localScale, rest, seconds, ease, unscaled);
        }

        /// <summary>
        /// Any float on anything. <paramref name="apply"/> receives <paramref name="target"/> back,
        /// so it needs no capture. When <paramref name="target"/> is a UnityEngine.Object the tween
        /// ends by itself once that object is destroyed.
        /// </summary>
        public static TweenHandle Value(object target, float from, float to, float seconds, Ease ease,
                                        Action<object, float> apply, bool unscaled = false)
        {
            if (apply == null) return default;
            Tween runner = Runner();
            if (runner == null) return default;
            int i = runner.Take();
            if (i < 0) return default;
            runner._slots[i] = new Slot
            {
                id = _nextId++, kind = Kind.Value, target = target, hasTarget = target != null, apply = apply,
                from = new Vector3(from, 0f, 0f), to = new Vector3(to, 0f, 0f),
                duration = Mathf.Max(0f, seconds), ease = ease, unscaled = unscaled,
            };
            Running++;
            return new TweenHandle { slot = i, id = runner._slots[i].id };
        }

        /// <summary>Stop every tween on this transform, where it is.</summary>
        public static void CancelAll(Transform t)
        {
            if (_instance == null || t == null) return;
            Slot[] slots = _instance._slots;
            for (int i = 0; i < slots.Length; i++)
                if (slots[i].kind != Kind.Free && slots[i].transform == t) _instance.Free(i);
        }

        internal static bool Alive(TweenHandle h)
            => _instance != null && h.id != 0 && h.slot < _instance._slots.Length &&
               _instance._slots[h.slot].id == h.id && _instance._slots[h.slot].kind != Kind.Free;

        internal static void Stop(TweenHandle h, bool complete)
        {
            if (!Alive(h)) return;
            if (complete) _instance.Write(ref _instance._slots[h.slot], 1f);
            _instance.Free(h.slot);
        }

        // --------------------------------------------------------------------------- the runner

        static Tween Runner()
        {
            if (_instance != null) return _instance;
            if (_quitting) return null;
            _instance = FindAnyObjectByType<Tween>();
            if (_instance != null) return _instance;
            var go = new GameObject("Tween") { hideFlags = HideFlags.HideAndDontSave };
            DontDestroyOnLoad(go);
            return go.AddComponent<Tween>();
        }

        void Awake()
        {
            if (_instance != null && _instance != this) { Destroy(this); return; }
            _instance = this;
            _slots = new Slot[Mathf.Max(1, capacity)];
        }

        void OnDestroy()
        {
            if (_instance != this) return;
            _instance = null;
            Running = 0;
        }

        void OnApplicationQuit() => _quitting = true;

        static TweenHandle Begin(Kind kind, Transform t, Vector3 from, Vector3 to, float seconds, Ease ease, bool unscaled)
        {
            Tween runner = Runner();
            if (runner == null) return default;

            // One writer per property: a new tween on the same transform and property replaces the
            // old one. Two tweens on one scale fight every frame and the later slot wins by accident.
            Slot[] slots = runner._slots;
            for (int k = 0; k < slots.Length; k++)
                if (slots[k].kind == kind && slots[k].transform == t) runner.Free(k);

            int i = runner.Take();
            if (i < 0) return default;
            slots[i] = new Slot
            {
                id = _nextId++, kind = kind, transform = t, from = from, to = to,
                duration = Mathf.Max(0f, seconds), ease = ease, unscaled = unscaled,
            };
            Running++;
            return new TweenHandle { slot = i, id = slots[i].id };
        }

        int Take()
        {
            for (int i = 0; i < _slots.Length; i++)
                if (_slots[i].kind == Kind.Free) return i;
            Dropped++;
            return -1;
        }

        void Free(int i)
        {
            if (_slots[i].kind == Kind.Free) return;
            _slots[i] = default;        // drops the references, so a finished tween keeps nothing alive
            Running--;
        }

        // LateUpdate: after gameplay and the Animator have written this frame's pose, so the tween
        // is what is drawn.
        void LateUpdate()
        {
            float dt = Time.deltaTime, udt = Time.unscaledDeltaTime;
            for (int i = 0; i < _slots.Length; i++)
            {
                if (_slots[i].kind == Kind.Free) continue;
                ref Slot s = ref _slots[i];

                bool gone = s.kind == Kind.Value
                    ? s.hasTarget && (s.target == null || (s.target is UnityEngine.Object o && o == null))
                    : s.transform == null;
                if (gone) { Free(i); continue; }

                s.elapsed += s.unscaled ? udt : dt;
                float t = s.duration > 0f ? Mathf.Clamp01(s.elapsed / s.duration) : 1f;
                int id = s.id;
                Write(ref s, t);
                // The callback may have started or stopped tweens; only free the one this was.
                if (t >= 1f && _slots[i].id == id) Free(i);
            }
        }

        void Write(ref Slot s, float t)
        {
            if (s.kind != Kind.Value && s.transform == null) return;
            float k = Easing.Evaluate(s.ease, t);
            switch (s.kind)
            {
                case Kind.Scale: s.transform.localScale = Vector3.LerpUnclamped(s.from, s.to, k); break;
                case Kind.LocalPosition: s.transform.localPosition = Vector3.LerpUnclamped(s.from, s.to, k); break;
                case Kind.Position: s.transform.position = Vector3.LerpUnclamped(s.from, s.to, k); break;
                case Kind.Value: s.apply(s.target, Mathf.LerpUnclamped(s.from.x, s.to.x, k)); break;
            }
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            _instance = null;
            _quitting = false;
            _nextId = 1;
            Running = 0;
            Dropped = 0;
        }
    }
}
