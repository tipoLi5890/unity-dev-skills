// RigDriver2D.cs — procedural motion for a layered character that AutoRig2D rigged: breathing
// idle, blinks, talking, a run cycle drawn for a front or a side view, a poke attack, a skateboard
// push and ollie when the rig has a `board` bone (a prop stood on), plus an optional 2D spring on
// hair, bags and tails. Every pose is an offset from the bind pose read at Bind(), and
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
using System.Linq;
using UnityEngine;
using UnityEngine.U2D.Animation;

namespace UnityDev.Rig2D
{
    [DisallowMultipleComponent]
    public sealed class RigDriver2D : MonoBehaviour
    {
        public enum View { Front, Side }
        public enum Motion { None, Idle, Talk, Run, Attack, Push, Ollie }

        public View view = View.Front;
        public Motion motion = Motion.Idle;
        [Tooltip("Side view only: the art faces +x.")] public bool facesRight = true;
        [Min(0f)] public float speed = 1f;
        [Tooltip("Seconds per run cycle (two steps).")] [Min(0.1f)] public float stride = 0.55f;
        [Min(0.1f)] public float breathPeriod = 2.4f;
        [Tooltip("Seconds per attack: wind-up, poke, hold, recover.")] [Min(0.2f)] public float attackPeriod = 1.1f;
        [Tooltip("The arm that pokes: near (side view) or R / L (front view).")] public string attackSide = "near";

        [Header("Board (a `board` bone)")]
        [Tooltip("Seconds per push: off the deck, down beside the front foot, a sweep back along the ground, home.")]
        [Min(0.3f)] public float pushPeriod = 1.4f;
        [Tooltip("Seconds per ollie: crouch, pop, air, land.")] [Min(0.3f)] public float olliePeriod = 1.2f;
        [Tooltip("The foot that pushes; empty: the one behind (over the tail).")] public string pushSide = "";

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
            BindBoard(renderers);
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
            if (_board) ResetContacts();
            switch (motion)
            {
                case Motion.Idle: Idle(t); break;
                case Motion.Talk: Idle(t); Talk(t); break;
                case Motion.Run: if (view == View.Side) RunSide(t); else RunFront(t); break;
                case Motion.Attack: Idle(t); Attack(t); break;
                case Motion.Push: if (_board) Push(t); else Idle(t); break;
                case Motion.Ollie: if (_board) Ollie(t); else Idle(t); break;
            }
            // a board stays on the ground under the feet whatever the body does (not in a run)
            if (_board && motion != Motion.None && motion != Motion.Run && motion != Motion.Push && motion != Motion.Ollie)
            { BoardPose(Vector2.zero, 0f, _boardPos0); PlantOnBoard(SideKeys()); }
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

        // ------------------------------------------------------------------ board

        Transform _board;
        Vector3 _boardPos0;
        Quaternion _boardRot0;
        Vector2[] _boardCorners = new Vector2[0];              // the board's rest bounds, board space
        Vector2[] _boardCorners0 = new Vector2[0];             // ... and in the world at rest
        readonly Dictionary<string, Vector2> _footRest = new Dictionary<string, Vector2>(), _hipRest = new Dictionary<string, Vector2>();
        readonly Dictionary<string, Vector3> _footOnBoard = new Dictionary<string, Vector3>();
        readonly Dictionary<string, Quaternion> _footRotOnBoard = new Dictionary<string, Quaternion>();
        readonly Dictionary<string, Vector2[]> _sole = new Dictionary<string, Vector2[]>(); // ankle space
        readonly Dictionary<string, Vector2> _legLen = new Dictionary<string, Vector2>();
        readonly Dictionary<string, float> _kneeSide = new Dictionary<string, float>();
        readonly List<(SpriteRenderer r, int order)> _pushLayers = new List<(SpriteRenderer, int)>();
        int _boardOrder;
        float _groundY;

        /// <summary>After a pose: how far (in character heights) a planted foot misses its spot on
        /// the deck, how far any sole or the board sinks below the ground, how high the pushing
        /// sole stays above the ground while it should push (NaN outside that phase), and how high
        /// the board's lowest point is above the ground.</summary>
        public float FootMiss { get; private set; }
        public float SinkBelowGround { get; private set; }
        public float PushGap { get; private set; } = float.NaN;
        public float BoardLift { get; private set; }
        public bool HasBoard => _board != null;
        /// <summary>The pushing side in use (pushSide, or the foot over the tail).</summary>
        public string PushKey { get; private set; } = "";

        float Hw => _height * Mathf.Abs(transform.lossyScale.y);

        void BindBoard(SpriteRenderer[] renderers)
        {
            _board = _bones.TryGetValue("board", out Transform b) ? b : null;
            _footOnBoard.Clear(); _footRotOnBoard.Clear(); _sole.Clear(); _legLen.Clear(); _kneeSide.Clear(); _pushLayers.Clear(); _footRest.Clear(); _hipRest.Clear();
            if (!_board) return;
            _boardPos0 = _board.position; _boardRot0 = _board.rotation;
            SpriteRenderer boardR = renderers.FirstOrDefault(r => Skinned(r, _board));
            Bounds bb = boardR ? boardR.bounds : new Bounds(_board.position + Vector3.down * 0.04f * Hw, new Vector3(0.4f * Hw, 0.08f * Hw, 0));
            _boardCorners = Corners(bb).Select(c => (Vector2)_board.InverseTransformPoint(c)).ToArray();
            _boardCorners0 = Corners(bb).Select(c => (Vector2)c).ToArray();
            _groundY = bb.min.y;
            _boardOrder = boardR ? boardR.sortingOrder : 0;
            float f = facesRight ? 1f : -1f;
            string back = "";
            foreach (string s in SideKeys())
            {
                if (!_bones.TryGetValue("hip_" + s, out Transform hip) || !_bones.TryGetValue("knee_" + s, out Transform knee)
                    || !_bones.TryGetValue("ankle_" + s, out Transform ankle)) continue;
                _footOnBoard[s] = _board.InverseTransformPoint(ankle.position);
                _footRest[s] = ankle.position;
                _hipRest[s] = hip.position;
                _footRotOnBoard[s] = Quaternion.Inverse(_board.rotation) * ankle.rotation;
                _legLen[s] = new Vector2(Vector2.Distance(hip.position, knee.position), Vector2.Distance(knee.position, ankle.position));
                Vector2 d = ankle.position - hip.position, k = knee.position - hip.position;
                float cross = d.x * k.y - d.y * k.x;
                _kneeSide[s] = Mathf.Abs(cross) > 1e-6f * Hw * Hw ? Mathf.Sign(cross) : f;    // straight: knee forward
                SpriteRenderer footR = renderers.FirstOrDefault(r => r.name.ToLowerInvariant().StartsWith("foot_") && Skinned(r, ankle));
                Bounds fb = footR ? footR.bounds : new Bounds(ankle.position + Vector3.down * 0.03f * Hw, new Vector3(0.08f * Hw, 0.06f * Hw, 0));
                _sole[s] = new[] { (Vector2)ankle.InverseTransformPoint(new Vector3(fb.min.x, fb.min.y)), (Vector2)ankle.InverseTransformPoint(new Vector3(fb.max.x, fb.min.y)) };
                if (back == "" || f * ankle.position.x < f * _bones["ankle_" + back].position.x) back = s;
            }
            PushKey = !string.IsNullOrEmpty(pushSide) && _footOnBoard.ContainsKey(pushSide) ? pushSide : back;
            // the pushing leg goes behind the board while it is off the deck when it is the far one
            if (PushKey == "far" && boardR)
                foreach (SpriteRenderer r in renderers)
                {
                    string n = r.name.ToLowerInvariant();
                    if ((n.StartsWith("foot_far") || n.StartsWith("leg_far")) && r.sortingOrder >= _boardOrder) _pushLayers.Add((r, r.sortingOrder));
                }
        }

        static bool Skinned(SpriteRenderer r, Transform bone)
        {
            var sk = r.GetComponent<SpriteSkin>();
            return sk != null && sk.boneTransforms != null && sk.boneTransforms.Contains(bone);
        }

        static IEnumerable<Vector3> Corners(Bounds b)
        {
            yield return new Vector3(b.min.x, b.min.y); yield return new Vector3(b.max.x, b.min.y);
            yield return new Vector3(b.min.x, b.max.y); yield return new Vector3(b.max.x, b.max.y);
        }

        /// <summary>The board turned by deg about a world pivot and moved by d (world units).</summary>
        public void BoardPose(Vector2 d, float deg, Vector3 pivot)
        {
            if (!_board) return;
            Quaternion q = Quaternion.Euler(0, 0, deg);
            _board.rotation = q * _boardRot0;
            _board.position = pivot + q * (_boardPos0 - pivot) + (Vector3)d;
        }

        /// <summary>Two-bone IK in the picture plane: turns hip_s and knee_s so ankle_s lands on
        /// target (world), the knee bending to the side it bends at rest; the foot takes footRot.
        /// Returns the miss in world units (the target out of the leg's reach).</summary>
        public float PlantFoot(string s, Vector2 target, Quaternion footRot)
        {
            if (!_legLen.TryGetValue(s, out Vector2 len)) return 0f;
            Transform hip = _bones["hip_" + s], knee = _bones["knee_" + s], ankle = _bones["ankle_" + s];
            Vector2 H = hip.position, d = target - H;
            float dist = d.magnitude, l1 = len.x, l2 = len.y;
            float reach = Mathf.Clamp(dist, Mathf.Abs(l1 - l2) + 1e-5f, l1 + l2 - 1e-5f);
            float a = Mathf.Acos(Mathf.Clamp((l1 * l1 + reach * reach - l2 * l2) / (2f * l1 * reach), -1f, 1f)) * Mathf.Rad2Deg;
            Vector2 dir = dist > 1e-6f ? d / dist : Vector2.down;
            Vector2 kneeAt = H + (Vector2)(Quaternion.Euler(0, 0, _kneeSide[s] * a) * dir) * l1;
            Aim(hip, (Vector2)knee.position - H, kneeAt - H);
            Vector2 K = knee.position;
            Aim(knee, (Vector2)ankle.position - K, target - K);
            ankle.rotation = footRot;
            return Vector2.Distance(ankle.position, target);
        }

        static void Aim(Transform t, Vector2 from, Vector2 to)
        {
            if (from.sqrMagnitude < 1e-12f || to.sqrMagnitude < 1e-12f) return;
            t.rotation = Quaternion.Euler(0, 0, Vector2.SignedAngle(from, to)) * t.rotation;
        }

        Vector2 OnBoard(string s, float slide = 0f)
        {
            Vector3 p = _footOnBoard[s];
            return _board.TransformPoint(p + Vector3.right * slide * Hw / Mathf.Max(Mathf.Abs(_board.lossyScale.x), 1e-6f));
        }

        // plants the feet on their deck spots and measures the contacts
        void PlantOnBoard(IEnumerable<string> feet, float frontSlide = 0f)
        {
            float miss = 0f;
            foreach (string s in feet)
            {
                if (!_footOnBoard.ContainsKey(s)) continue;
                float slide = s == PushKey ? 0f : frontSlide * (facesRight ? 1f : -1f);
                miss = Mathf.Max(miss, PlantFoot(s, OnBoard(s, slide), _board.rotation * _footRotOnBoard[s]));
            }
            FootMiss = Mathf.Max(FootMiss, miss / Hw);
            Measure();
        }

        float SoleY(string s)
        {
            Transform a = _bones["ankle_" + s];
            return Mathf.Min(a.TransformPoint(_sole[s][0]).y, a.TransformPoint(_sole[s][1]).y);
        }

        void Measure()
        {
            float low = float.MaxValue;
            foreach (Vector2 c in _boardCorners) low = Mathf.Min(low, _board.TransformPoint(c).y);
            BoardLift = (low - _groundY) / Hw;
            float sink = Mathf.Max(0f, -BoardLift);
            foreach (string s in _sole.Keys) sink = Mathf.Max(sink, (_groundY - SoleY(s)) / Hw);
            SinkBelowGround = sink;
        }

        void ResetContacts()
        {
            FootMiss = 0f; SinkBelowGround = 0f; PushGap = float.NaN; BoardLift = 0f;
            foreach (var (r, order) in _pushLayers) if (r) r.sortingOrder = order;
        }

        const float MaxPushDip = 0.14f;   // the most the hips drop for a push, in heights

        static float Bump(float u, float a, float b) => u <= a || u >= b ? 0f : Mathf.Sin(Mathf.PI * (u - a) / (b - a));
        static float Ramp(float u, float a, float b) => Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(a, b, u));

        /// <summary>Riding with pushes: the back foot leaves the deck, comes down beside the front
        /// foot (the legs cross), sweeps back along the ground past the tail, and swings home while
        /// the standing knee bends to let it reach; the board stays on the ground. Phase 0..1 per
        /// pushPeriod; the sole is on the ground for 0.32..0.58.</summary>
        public void Push(float t)
        {
            ResetContacts();
            float u = Mathf.Repeat(t / pushPeriod, 1f), f = facesRight ? 1f : -1f, Hh = Hw;
            string ps = PushKey, front = SideKeys().FirstOrDefault(k => k != ps && _footOnBoard.ContainsKey(k));
            if (string.IsNullOrEmpty(ps) || front == null) { Idle(t); BoardPose(Vector2.zero, 0f, _boardPos0); PlantOnBoard(SideKeys()); return; }
            Transform hips = _bones.TryGetValue("hips", out Transform h) ? h : null;
            Vector2 deck = OnBoardRest(ps), frontAt = OnBoardRest(front);
            float soleUp = _bones["ankle_" + ps].position.y - SoleY(ps);               // ankle above its sole
            float gy = _groundY + soleUp;                                              // ankle height on the ground
            float xs = frontAt.x - f * 0.02f * Hh, xe = BoardEnd(-f) - f * 0.12f * Hh; // beside the front foot .. past the tail
            {   // .. as far as the leg reaches on the ground with the hips at their lowest
                Vector2 len = _legLen[ps], hip0 = _hipRest[ps];
                float dy = hip0.y - MaxPushDip * Hh - gy, reach = 0.95f * (len.x + len.y);
                float dx = reach > Mathf.Abs(dy) ? Mathf.Sqrt(reach * reach - dy * dy) : 0f;
                xe = f > 0 ? Mathf.Max(xe, hip0.x - dx) : Mathf.Min(xe, hip0.x + dx);
                xs = f > 0 ? Mathf.Min(xs, hip0.x + dx) : Mathf.Max(xs, hip0.x - dx);
            }
            Vector2 target;
            bool contact = false;
            if (u < 0.1f || u >= 0.86f) target = deck;
            else if (u < 0.32f) { float v = Ramp(u, 0.1f, 0.32f); target = Vector2.Lerp(deck, new Vector2(xs, gy), v) + Vector2.up * 0.05f * Hh * Bump(u, 0.1f, 0.32f); }
            else if (u < 0.58f) { target = new Vector2(Mathf.Lerp(xs, xe, Ramp(u, 0.32f, 0.58f)), gy); contact = true; }
            else { float v = Ramp(u, 0.58f, 0.86f); target = Vector2.Lerp(new Vector2(xe, gy), deck, v) + Vector2.up * 0.07f * Hh * Bump(u, 0.58f, 0.86f); }
            // the body: lean in, arms out for balance; the hips drop as far as the pushing leg needs
            Rot("chest", -f * (4f + 3f * Bump(u, 0.1f, 0.86f)));
            Rot("neck", f * 3f);
            foreach (string k in SideKeys()) { Rot("shoulder_" + k, f * (k == ps ? -14f : 10f) * Bump(u, 0.05f, 0.95f)); Rot("elbow_" + k, f * 12f); }
            if (hips)
            {
                Vector2 len = _legLen[ps];
                float need = 0f;
                for (int i = 0; i < 4; i++)                 // lower the hips until the foot is in reach
                {
                    Move("hips", new Vector2(0f, -need / Hh));
                    float over = Vector2.Distance(_bones["hip_" + ps].position, target) - 0.97f * (len.x + len.y);
                    if (over <= 0f) break;
                    need += over;
                }
                need = Mathf.Min(need, MaxPushDip * Hh);
                Move("hips", new Vector2(0f, -(need + 0.012f * Hh * Bump(u, 0.1f, 0.86f)) / Hh));
            }
            BoardPose(Vector2.zero, 0f, _boardPos0);
            PlantOnBoard(new[] { front });
            bool off = u >= 0.1f && u < 0.86f;
            float miss = PlantFoot(ps, target, off ? _boardRot0 * _footRotOnBoard[ps] : _board.rotation * _footRotOnBoard[ps]);
            if (!off) FootMiss = Mathf.Max(FootMiss, miss / Hh);
            foreach (var (r, order) in _pushLayers) if (r) r.sortingOrder = off ? order - (order - _boardOrder) - 1 - (r.name.ToLowerInvariant().StartsWith("leg_") ? 1 : 0) : order;
            Measure();
            PushGap = contact ? (SoleY(ps) - _groundY) / Hh : float.NaN;
        }

        Vector2 OnBoardRest(string s) => _footRest[s];

        // the board's end at rest toward dir (+1: +x)
        float BoardEnd(float dir) => dir > 0 ? _boardCorners0.Max(c => c.x) : _boardCorners0.Min(c => c.x);

        /// <summary>An ollie: crouch, the tail pops (the board tips nose up about the tail on the
        /// ground) as the body springs, the board rises under the tucked feet and levels, falls,
        /// and the knees take the landing. Both feet stay planted; the front one slides up the
        /// deck on the pop. Phase 0..1 per olliePeriod; in the air 0.36..0.74.</summary>
        public void Ollie(float t)
        {
            ResetContacts();
            float u = Mathf.Repeat(t / olliePeriod, 1f), f = facesRight ? 1f : -1f;
            float crouch = 0.06f * (Ramp(u, 0f, 0.24f) - Ramp(u, 0.24f, 0.34f)) + 0.07f * (Ramp(u, 0.74f, 0.8f) - Ramp(u, 0.84f, 1f));
            float lift = 0.2f * Bump(u, 0.34f, 0.76f);
            float tip = f * (20f * Bump(u, 0.24f, 0.46f) - 5f * Bump(u, 0.52f, 0.74f));
            float body = 0.04f * Bump(u, 0.28f, 0.5f) + 0.75f * lift;           // the knees tuck at the top
            Move("hips", new Vector2(0f, body - crouch));
            Rot("chest", -f * (6f * Ramp(u, 0f, 0.24f) * (1f - Ramp(u, 0.3f, 0.5f)) + 3f));
            foreach (string k in SideKeys()) { Rot("shoulder_" + k, f * (k == PushKey ? -1f : 1f) * 35f * Bump(u, 0.2f, 0.8f)); Rot("elbow_" + k, f * 20f * Bump(u, 0.2f, 0.8f)); }
            // the tail stays on the ground through the pop: the board turns about the tail's lowest corner
            Vector3 pivot = new Vector3(BoardEnd(-f), _groundY, 0f);
            BoardPose(Vector2.up * lift * Hw, tip, pivot);
            PlantOnBoard(SideKeys(), 0.035f * Bump(u, 0.24f, 0.62f));
        }

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
