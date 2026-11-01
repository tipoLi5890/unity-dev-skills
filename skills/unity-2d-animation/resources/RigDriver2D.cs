// RigDriver2D.cs — procedural motion for a layered character that AutoRig2D rigged: breathing
// idle, blinks, talking, a run cycle drawn for a front or a side view, a poke attack, plus an optional 2D
// spring on hair, bags and tails. Every pose is an offset from the bind pose read at Bind(), and
// a bone the rig does not have is skipped, so a sheet with fewer layers still plays.
//
// Copy into a Runtime assembly that references Unity.2D.Animation.Runtime. AutoRig2D's variant
// adds it with the resolvers and spring bones filled in. Bones are AutoRig2D's joint names: hips,
// chest, neck, face, shoulder_/elbow_/wrist_ and hip_/knee_/ankle_ with _L / _R (front) or
// _near / _far (side).
// Positive degrees turn counter-clockwise; in a front view the screen-left limbs are _R.
//
// Drives the bones in Update, before SpriteSkin deforms. Leave `motion` at None when an Animator
// owns the bones: the blink, the mouth and the springs still run. Tests and captures call
// Evaluate(t) and StepSprings(dt) themselves. The spring borrows SpringSolver's ideas (Verlet,
// rates per 1/60 s converted per substep, carry, a pull to the animated pose, an angle clamp).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.U2D.Animation;

namespace UnityDev.Rig2D
{
    [DisallowMultipleComponent]
    public sealed class RigDriver2D : MonoBehaviour
    {
        public enum View { Front, Side }
        public enum Motion { None, Idle, Talk, Run, Attack }

        public View view = View.Front;
        public Motion motion = Motion.Idle;
        [Tooltip("Side view only: the art faces +x.")] public bool facesRight = true;
        [Min(0f)] public float speed = 1f;
        [Tooltip("Seconds per run cycle (two steps).")] [Min(0.1f)] public float stride = 0.55f;
        [Min(0.1f)] public float breathPeriod = 2.4f;
        [Tooltip("Seconds per attack: wind-up, poke, hold, recover.")] [Min(0.2f)] public float attackPeriod = 1.1f;
        [Tooltip("The arm that pokes: near (side view) or R / L (front view).")] public string attackSide = "near";

        [Header("Face")]
        public bool blink = true;
        [Min(0.3f)] public float blinkInterval = 3f;
        [Tooltip("0..1 from a lip-sync source overrides the talk pattern; below 0 leaves it.")]
        [Range(-1f, 1f)] public float mouthOpen = -1f;
        public SpriteResolver[] eyes = new SpriteResolver[0];
        public SpriteResolver[] mouths = new SpriteResolver[0];
        public string openLabel = "open", closedLabel = "closed";

        [Header("Spring")]
        public bool springs = true;
        public Transform[] springBones = new Transform[0];
        [Tooltip("Pull back to the animated pose, per 1/60 s.")] [Range(0f, 1f)] public float springStiffness = 0.12f;
        [Range(0f, 1f)] public float springDrag = 0.1f;
        [Tooltip("Share of the pivot's motion the tip follows without lag.")] [Range(0f, 1f)] public float springCarry = 0.6f;
        [Min(0f)] public float springGravity = 0.5f;
        [Range(0f, 90f)] public float springMaxAngle = 40f;

        readonly Dictionary<string, Transform> _bones = new Dictionary<string, Transform>();
        readonly Dictionary<Transform, Quaternion> _restRot = new Dictionary<Transform, Quaternion>();
        readonly Dictionary<Transform, Vector3> _restPos = new Dictionary<Transform, Vector3>();
        Vector2[] _tip, _prev, _pivot;
        Quaternion[] _before, _after;
        float _height = 1f, _time;
        int _eyesState = -1, _mouthState = -1;

        /// <summary>Character height in the root's local units, measured at Bind().</summary>
        public float Height => _height;
        public bool Has(string bone) => _bones.ContainsKey(bone);

        void OnEnable() { Bind(); }

        void Update()
        {
            float dt = Time.deltaTime;
            _time += dt * speed;
            Evaluate(_time);
            StepSprings(dt);
        }

        /// <summary>Finds the bones (Transforms under the root that render nothing) and keeps
        /// their bind pose. Call again after the hierarchy changes.</summary>
        public void Bind()
        {
            _bones.Clear(); _restRot.Clear(); _restPos.Clear();
            var renderers = GetComponentsInChildren<SpriteRenderer>(true);
            foreach (Transform t in GetComponentsInChildren<Transform>(true))
            {
                if (t == transform || t.GetComponent<SpriteRenderer>() != null) continue;
                if (!_bones.ContainsKey(t.name)) _bones[t.name] = t;
                _restRot[t] = t.localRotation;
                _restPos[t] = t.localPosition;
            }
            if (renderers.Length > 0)
            {
                Bounds b = renderers[0].bounds;
                foreach (SpriteRenderer r in renderers) b.Encapsulate(r.bounds);
                _height = Mathf.Max(b.size.y / Mathf.Max(Mathf.Abs(transform.lossyScale.y), 1e-6f), 1e-3f);
            }
            _tip = null;
            _eyesState = _mouthState = -1;
        }

        public void ResetPose()
        {
            foreach (var kv in _restRot) kv.Key.localRotation = kv.Value;
            foreach (var kv in _restPos) kv.Key.localPosition = kv.Value;
        }

        /// <summary>Turns a bone by deg from its bind pose. No-op for a bone the rig lacks.</summary>
        public void Rot(string bone, float deg)
        {
            if (_bones.TryGetValue(bone, out Transform t)) t.localRotation = _restRot[t] * Quaternion.Euler(0, 0, deg);
        }

        /// <summary>Moves a bone from its bind pose by d, in character heights, in the parent's space.</summary>
        public void Move(string bone, Vector2 d)
        {
            if (_bones.TryGetValue(bone, out Transform t)) t.localPosition = _restPos[t] + (Vector3)(d * _height);
        }

        public void SetEyes(bool open) => Swap(eyes, open, ref _eyesState);
        public void SetMouth(bool open) => Swap(mouths, open, ref _mouthState);

        void Swap(SpriteResolver[] rs, bool open, ref int state)
        {
            int s = open ? 1 : 0;
            if (s == state || rs == null) return;
            state = s;
            foreach (SpriteResolver r in rs)
                if (r) r.SetCategoryAndLabel(r.GetCategory(), open ? openLabel : closedLabel);
        }

        /// <summary>The pose at time t of the current motion, from the bind pose.</summary>
        public void Evaluate(float t)
        {
            if (motion != Motion.None) ResetPose();
            switch (motion)
            {
                case Motion.Idle: Idle(t); break;
                case Motion.Talk: Idle(t); Talk(t); break;
                case Motion.Run: if (view == View.Side) RunSide(t); else RunFront(t); break;
                case Motion.Attack: Idle(t); Attack(t); break;
            }
            if (mouthOpen >= 0f) SetMouth(mouthOpen > 0.35f);
            else if (motion != Motion.Talk) SetMouth(false);
            SetEyes(!blink || !Blinking(t));
        }

        bool Blinking(float t)
        {
            int k = Mathf.FloorToInt(t / blinkInterval);
            float jitter = Mathf.Repeat(Mathf.Sin(k * 12.9898f) * 43758.547f, 1f);     // a fixed, uneven rhythm
            float at = (k + 0.55f + 0.35f * jitter) * blinkInterval;
            return t >= at && t < at + 0.12f;
        }

        public void Idle(float t)
        {
            float b = Mathf.Sin(t * Mathf.PI * 2f / breathPeriod);
            Rot("chest", 1.2f * b);
            Move("hips", new Vector2(0, 0.002f * b));
            Rot("neck", -2f * Mathf.Sin(t * Mathf.PI * 2f / (breathPeriod * 1.3f)));
            if (view == View.Side)
            {
                // both arms sway together, a little forward on the in-breath
                float f = facesRight ? 1f : -1f;
                foreach (string s in SideKeys()) { Rot("shoulder_" + s, 2f * f * b); Rot("elbow_" + s, 3f * f * b); }
            }
            else
            {
                // the arms open and close with the breath
                Rot("shoulder_R", -2f * b); Rot("shoulder_L", 2f * b);
                Rot("elbow_R", -3f * b); Rot("elbow_L", 3f * b);
            }
            if (!springs) foreach (Transform s in springBones) if (s) Rot(s.name, 2.5f * Mathf.Sin(t * Mathf.PI * 2f / 1.7f));
        }

        public void Talk(float t)
        {
            if (mouthOpen < 0f)
            {
                int k = Mathf.FloorToInt(t * 8f);
                int[] pattern = { 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0 };
                SetMouth(pattern[k % pattern.Length] == 1);
            }
            Rot("neck", 2.5f * Mathf.Sin(t * 5f));
        }

        /// <summary>A run in place seen from the front: knees lift, arms pump, the body bobs.</summary>
        public void RunFront(float t)
        {
            float w = Mathf.PI * 2f / stride;
            float s = Mathf.Sin(t * w), c = Mathf.Cos(t * w);
            Move("hips", new Vector2(0, 0.012f * Mathf.Abs(c) - 0.007f));
            Rot("chest", 3f * s);
            Rot("neck", -2f * s);
            Rot("hip_R", -14f * Mathf.Max(s, 0)); Rot("knee_R", 26f * Mathf.Max(s, 0));
            Rot("hip_L", 14f * Mathf.Max(-s, 0)); Rot("knee_L", -26f * Mathf.Max(-s, 0));
            Rot("ankle_R", -10f * Mathf.Max(s, 0)); Rot("ankle_L", 10f * Mathf.Max(-s, 0));
            Rot("shoulder_R", 18f + 14f * s); Rot("elbow_R", 55f + 20f * s);
            Rot("shoulder_L", -18f + 14f * s); Rot("elbow_L", -55f + 20f * s);
        }

        /// <summary>A side-view run: thighs swing about the hip, the knee folds on the forward swing,
        /// the foot stays near level, each arm swings against its leg, the body leans and bobs.</summary>
        public void RunSide(float t)
        {
            float f = facesRight ? 1f : -1f;
            float ph = t * Mathf.PI * 2f / stride;
            Move("hips", new Vector2(0, 0.02f * Mathf.Abs(Mathf.Sin(ph)) - 0.012f));
            Rot("chest", -f * (6f + 1.5f * Mathf.Sin(2f * ph)));
            Rot("neck", f * 4f);
            string[] k = SideKeys();
            Leg(k[0], ph, f);
            Leg(k[1], ph + Mathf.PI, f);
        }

        /// <summary>A side view's two sides: near / far when the rig has them, else L / R.</summary>
        string[] SideKeys() => Has("hip_near") || Has("shoulder_near") ? new[] { "near", "far" } : new[] { "L", "R" };

        // One leg and the arm on its side, at phase ph (0: the thigh passes under the hip moving
        // forward). The knee folds most just after that, in mid-swing, and is nearly straight
        // while the thigh is behind, so the trailing leg pushes off instead of kicking out flat.
        void Leg(string side, float ph, float f)
        {
            float thigh = 30f * Mathf.Sin(ph) + 4f;
            float swing = Mathf.Max(0f, Mathf.Cos(ph - 0.5f));
            float bend = 12f + 85f * swing * Mathf.Sqrt(swing);
            Rot("hip_" + side, f * thigh);
            Rot("knee_" + side, -f * bend);
            Rot("ankle_" + side, -0.6f * f * (thigh - bend));
            // the upper arm swings a little behind the body, the forearm stays folded up
            Rot("shoulder_" + side, -f * (18f * Mathf.Sin(ph) + 6f));
            Rot("elbow_" + side, f * (65f - 10f * Mathf.Sin(ph)));
        }

        /// <summary>A poke with whatever the attacking hand holds (a prop layer bound to it moves
        /// with it): the arm draws back with the elbow folding, then thrusts forward with the body
        /// leaning in, holds, and recovers; the wrist turns against the arm so the held prop keeps
        /// its angle. Phase 0..1 per attackPeriod; 0.52..0.65 is the hit.</summary>
        public void Attack(float t)
        {
            float f = view == View.Side ? (facesRight ? 1f : -1f) : 1f;
            float a = AttackCurve(Mathf.Repeat(t / attackPeriod, 1f));
            string s = attackSide;
            float sh = f * (a > 0f ? 20f : 16f) * a, el = f * 32f * Mathf.Max(-a, 0f);
            Rot("shoulder_" + s, sh);
            Rot("elbow_" + s, el);
            Rot("wrist_" + s, -0.85f * (sh + el));     // the hand keeps its angle: a thrust, not a swing
            Rot("chest", -f * 5f * a);
            Rot("neck", f * 2.5f * a);
            Move("hips", new Vector2(f * 0.025f * a, -0.006f * Mathf.Abs(a)));
            foreach (string k in SideKeys())               // the off arm tucks in a little on the poke
                if (k != s) { Rot("shoulder_" + k, f * 6f * a); Rot("elbow_" + k, f * 4f * Mathf.Max(a, 0f)); }
        }

        /// <summary>-1 drawn back .. +1 extended: ease back to -1 by 0.4, snap to +1 by 0.52, hold to
        /// 0.65, ease home by 1.</summary>
        public static float AttackCurve(float p)
        {
            if (p < 0.4f) return -Mathf.SmoothStep(0f, 1f, p / 0.4f);
            if (p < 0.52f) { float u = (p - 0.4f) / 0.12f; return -1f + 2f * (1f - (1f - u) * (1f - u)); }
            if (p < 0.65f) return 1f;
            return 1f - Mathf.SmoothStep(0f, 1f, (p - 0.65f) / 0.35f);
        }

        // Extreme poses for judging weights (front view).
        public void PoseArmUp() { Rot("shoulder_L", 125f); Rot("elbow_L", 20f); Rot("wrist_L", 10f); }
        public void PoseHeadTurn() { Rot("neck", 9f); Move("face", new Vector2(-0.012f, 0)); }
        public void PoseCrouch() { Rot("hip_R", -30f); Rot("knee_R", 55f); Rot("hip_L", 30f); Rot("knee_L", -55f); Rot("shoulder_R", -60f); Rot("elbow_R", -70f); }

        // ------------------------------------------------------------------ spring

        /// <summary>Turns each spring bone toward a simulated tip that lags its animated one.
        /// Call after the pose for this frame is set.</summary>
        public void StepSprings(float dt)
        {
            if (!springs || springBones == null || springBones.Length == 0 || dt <= 0f) return;
            int n = springBones.Length;
            float tall = _height * Mathf.Abs(transform.lossyScale.y), len = 0.12f * tall;
            if (_tip == null || _tip.Length != n)
            {
                _tip = new Vector2[n]; _prev = new Vector2[n]; _pivot = new Vector2[n];
                _before = new Quaternion[n]; _after = new Quaternion[n];
                for (int i = 0; i < n; i++) if (springBones[i]) { ResetSpring(i, len); _after[i] = new Quaternion(0, 0, 0, 0); }
            }
            int steps = Mathf.Clamp(Mathf.CeilToInt(dt * 60f), 1, 4);
            float h = Mathf.Min(dt, 0.1f) / steps;
            float stiff = PerSubstep(springStiffness, h), drag = PerSubstep(springDrag, h);
            Vector2 g = Vector2.down * springGravity * 9.81f * len;
            for (int i = 0; i < n; i++)
            {
                Transform b = springBones[i];
                if (!b) continue;
                // nothing re-posed this bone since our last turn (motion None, no Animator on it):
                // start from the pose it had before that turn, or the turn would add up
                if (b.localRotation == _after[i]) b.localRotation = _before[i];
                _before[i] = b.localRotation;
                Vector2 pivot = b.position;
                if ((pivot - _pivot[i]).magnitude > 0.5f * tall) { ResetSpring(i, len); _after[i] = b.localRotation; continue; }   // teleported
                Vector2 animDir = ((Vector2)(b.rotation * Vector3.right)).normalized;
                Vector2 carry = (pivot - _pivot[i]) * springCarry / steps;
                for (int k = 0; k < steps; k++)
                {
                    Vector2 v = (_tip[i] - _prev[i]) * (1f - drag);
                    _prev[i] = _tip[i] + carry;
                    _tip[i] = _tip[i] + carry + v + g * (h * h);
                    Vector2 target = pivot + animDir * len;
                    _tip[i] += (target - _tip[i]) * stiff;
                    Vector2 d = _tip[i] - pivot;
                    float m = d.magnitude;
                    d = m < 1e-6f ? animDir : d / m;
                    float ang = Vector2.SignedAngle(animDir, d);
                    if (Mathf.Abs(ang) > springMaxAngle) d = Quaternion.Euler(0, 0, Mathf.Sign(ang) * springMaxAngle) * animDir;
                    _tip[i] = pivot + d * len;
                }
                _pivot[i] = pivot;
                float turn = Vector2.SignedAngle(animDir, _tip[i] - pivot);
                if (!float.IsNaN(turn)) b.rotation = Quaternion.Euler(0, 0, turn) * b.rotation;
                _after[i] = b.localRotation;
            }
        }

        void ResetSpring(int i, float len)
        {
            Transform b = springBones[i];
            _pivot[i] = b.position;
            _tip[i] = _prev[i] = _pivot[i] + (Vector2)(b.rotation * Vector3.right).normalized * len;
        }

        /// <summary>A fraction per 1/60 s as the same fraction per substep of h seconds.</summary>
        public static float PerSubstep(float perSixtieth, float h)
        {
            float x = Mathf.Clamp01(perSixtieth);
            return x >= 1f ? 1f : 1f - Mathf.Pow(1f - x, h * 60f);
        }
    }
}
