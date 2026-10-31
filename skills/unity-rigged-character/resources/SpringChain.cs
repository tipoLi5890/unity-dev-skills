// SpringChain — one hanging chain of bones (a hood, a bag, a hem flap, a hair spike) that lags,
// swings and settles behind the animated body. SecondaryMotionSystem on the model steps every
// chain after the Animator; this component holds the bones, the parameters and the particle state.
//
// bones runs root to tip. bones[0] hangs from an animated parent and is pinned to it; the last is
// the unweighted tip bone (an FBX carries no bone tails, so the rig side adds one). Each bone but
// the tip is turned along its simulated segment (read between the last two substeps, so a frame
// with no substep still moves); twist stays the animation's.
//
// The animated pose each frame: a bone the Animator wrote this frame keeps that rotation; a bone
// still holding what the spring wrote last frame (the clip has no curve for it) goes back to its
// rest rotation first. So one component works under Generic and Humanoid, and with clips that do
// or do not carry the chain bones.
using UnityEngine;

namespace UnityDev.SecondaryMotion
{
    public sealed class SpringChain : MonoBehaviour
    {
        [Tooltip("Root to tip. The first hangs from an animated parent; the last is the unweighted tip.")]
        public Transform[] bones;

        [Tooltip("Pull back to the animated pose, per 1/60 s. Higher holds the shape: hair 0.75, hood 0.35.")]
        [Range(0f, 1f)] public float stiffness = 0.4f;

        [Tooltip("Velocity lost per 1/60 s. Raise it when a chain jitters or keeps swinging.")]
        [Range(0f, 1f)] public float drag = 0.4f;

        [Tooltip("Multiple of the system's gravity.")]
        public float gravity = 0.5f;

        [Tooltip("Multiple of the system's wind.")]
        public float wind;

        [Tooltip("Particle radius against colliders, in model units.")]
        public float radius = 0.03f;

        [Tooltip("1: lags the whole-body motion fully. Lower: carried along with the model's travel (calms lane snaps).")]
        [Range(0f, 1f)] public float inertia = 1f;

        [Tooltip("Largest angle, in degrees, between a simulated segment and its animated direction.")]
        [Range(1f, 180f)] public float maxAngle = 40f;

        [Tooltip("On: every SpringCollider under the system. Off: only the list below.")]
        public bool useAllColliders = true;
        public SpringCollider[] colliders;

        [SerializeField, HideInInspector] Quaternion[] restLocal;

        // Particle state, sized in Init. No allocation per frame.
        Vector3[] _p, _prev, _last, _target, _simTarget;
        Quaternion[] _lastWritten;
        bool[] _written;
        int[] _colliderIndex;
        bool _valid;

        public bool IsValid => _valid;
        public int ParticleCount => _valid ? _p.Length : 0;

        /// <summary>World position of particle i (0 is pinned to the animated first bone).</summary>
        public Vector3 GetParticle(int i) => _p[i];

        /// <summary>The animated (target) position of joint i this frame.</summary>
        public Vector3 GetTarget(int i) => _target[i];

        /// <summary>Stores every bone's current local rotation as its rest. SecondaryMotionSetup
        /// calls it on the prefab's bind pose; Init calls it once when nothing is stored.</summary>
        public void CaptureRest()
        {
            if (bones == null) return;
            restLocal = new Quaternion[bones.Length];
            for (int i = 0; i < bones.Length; i++)
                restLocal[i] = bones[i] != null ? bones[i].localRotation : Quaternion.identity;
        }

        /// <summary>Validates the bones and sizes the state. Returns an error, or null.</summary>
        internal string Init(SpringCollider[] all)
        {
            RestoreWritten();
            _valid = false;
            if (bones == null || bones.Length < 2) return name + ": a chain needs at least a bone and its tip";
            for (int i = 0; i < bones.Length; i++)
            {
                if (bones[i] == null) return name + ": bone " + i + " is missing";
                if (i > 0 && (bones[i] == bones[i - 1] || !bones[i].IsChildOf(bones[i - 1])))
                    return name + ": " + bones[i].name + " is not under " + bones[i - 1].name;
            }
            if (bones[0].parent == null) return name + ": " + bones[0].name + " has no parent to hang from";
            if (restLocal == null || restLocal.Length != bones.Length) CaptureRest();

            int n = bones.Length;
            _p = new Vector3[n];
            _prev = new Vector3[n];
            _last = new Vector3[n];
            _target = new Vector3[n];
            _simTarget = new Vector3[n];
            _lastWritten = new Quaternion[n];
            _written = new bool[n];

            int count = 0;
            var picked = new int[all.Length];
            for (int c = 0; c < all.Length; c++)
            {
                if (all[c] == null) continue;
                if (!useAllColliders && System.Array.IndexOf(colliders ?? new SpringCollider[0], all[c]) < 0) continue;
                picked[count++] = c;
            }
            _colliderIndex = new int[count];
            System.Array.Copy(picked, _colliderIndex, count);
            _valid = true;
            return null;
        }

        /// <summary>Puts back the rest rotation on every bone that still holds what the spring
        /// wrote, so a disabled or rebuilt system leaves the plain animated pose.</summary>
        internal void RestoreWritten()
        {
            if (_written == null || bones == null || restLocal == null) return;
            for (int i = 0; i < _written.Length && i < bones.Length; i++)
            {
                if (_written[i] && bones[i] != null && SameBits(bones[i].localRotation, _lastWritten[i]))
                    bones[i].localRotation = restLocal[i];
                _written[i] = false;
            }
        }

        /// <summary>The animated pose: restore the bones the Animator did not write, read the targets.</summary>
        internal void Capture()
        {
            int n = bones.Length;
            for (int i = 0; i < n - 1; i++)
            {
                Transform b = bones[i];
                // Float-exact on purpose: Quaternion == is approximate and would take a near-rest
                // animated write for the spring's own.
                if (_written[i] && SameBits(b.localRotation, _lastWritten[i])) b.localRotation = restLocal[i];
            }
            for (int i = 0; i < n; i++) _target[i] = bones[i].position;
        }

        /// <summary>Particles onto the animated pose, at rest.</summary>
        internal void ResetParticles()
        {
            for (int i = 0; i < _p.Length; i++)
            {
                _p[i] = _prev[i] = _last[i] = _simTarget[i] = _target[i];
            }
        }

        /// <summary>One substep. a is the fraction of the way from the last simulated pose to this
        /// frame's animated pose; the system interpolates the colliders the same way and passes
        /// this substep's ends at colA/colB[colOffset + collider index].</summary>
        internal void Step(float h, float a, Vector3 accel, Vector3 rootCarry, float scale,
                           Vector3[] colA, Vector3[] colB, float[] colR, int colOffset)
        {
            System.Array.Copy(_p, _last, _p.Length);
            float stiffH = SpringSolver.PerSubstep(stiffness, h);
            float dragH = SpringSolver.PerSubstep(drag, h);
            float maxRad = Mathf.Clamp(maxAngle, 1f, 180f) * Mathf.Deg2Rad;
            float pr = radius * scale;
            Vector3 carry = rootCarry * (1f - Mathf.Clamp01(inertia));

            Vector3 parentT = Vector3.Lerp(_simTarget[0], _target[0], a);
            _p[0] = _prev[0] = parentT;
            for (int i = 1; i < _p.Length; i++)
            {
                Vector3 t = Vector3.Lerp(_simTarget[i], _target[i], a);
                Vector3 seg = t - parentT;
                parentT = t;
                float len = seg.magnitude;

                Vector3 p = _p[i];
                SpringSolver.Integrate(ref p, ref _prev[i], accel, h, dragH, carry);
                p = SpringSolver.Pull(p, _p[i - 1], seg, stiffH);
                // Collide, clamp, then length last so bones never stretch; up to two more collide
                // and length passes settle a particle pressed between a collider and its parent.
                Collide(ref p, pr, colA, colB, colR, colOffset);
                p = SpringSolver.ClampAngle(_p[i - 1], p, seg, maxRad);
                p = SpringSolver.KeepLength(_p[i - 1], p, len, seg);
                for (int pass = 0; pass < 2 && Collide(ref p, pr, colA, colB, colR, colOffset); pass++)
                    p = SpringSolver.KeepLength(_p[i - 1], p, len, seg);
                if (!SpringSolver.IsFinite(p)) { p = t; _prev[i] = t; }
                _p[i] = p;
            }
        }

        bool Collide(ref Vector3 p, float pr, Vector3[] colA, Vector3[] colB, float[] colR, int colOffset)
        {
            bool moved = false;
            for (int k = 0; k < _colliderIndex.Length; k++)
            {
                int c = _colliderIndex[k];
                if (colR[c] <= 0f) continue;
                moved |= SpringSolver.PushOut(ref p, colA[colOffset + c], colB[colOffset + c], colR[c] + pr);
            }
            return moved;
        }

        /// <summary>Called after the last substep of a frame that ran any.</summary>
        internal void EndSubsteps()
        {
            System.Array.Copy(_target, _simTarget, _target.Length);
        }

        /// <summary>Turns each bone, root to tip, so its child lies along the simulated segment.
        /// alpha (0..1) is how far the frame's time runs past the last substep: the segment is read
        /// between the last two substeps, so a frame with no substep still moves.</summary>
        internal void Write(float alpha)
        {
            for (int i = 0; i < bones.Length - 1; i++)
            {
                Transform b = bones[i];
                Vector3 now = bones[i + 1].position - b.position;
                Vector3 want = Vector3.LerpUnclamped(_last[i + 1], _p[i + 1], alpha) - Vector3.LerpUnclamped(_last[i], _p[i], alpha);
                if (now.sqrMagnitude > 1e-12f && want.sqrMagnitude > 1e-12f)
                {
                    Quaternion r = Quaternion.FromToRotation(now, want) * b.rotation;
                    if (SpringSolver.IsFinite(new Vector3(r.x, r.y, r.z)) && !float.IsNaN(r.w)) b.rotation = r;
                }
                _lastWritten[i] = b.localRotation;     // read back: what the next Capture compares
                _written[i] = true;
            }
        }

        static bool SameBits(Quaternion a, Quaternion b)
        {
            return a.x == b.x && a.y == b.y && a.z == b.z && a.w == b.w;
        }

        void OnDrawGizmosSelected()
        {
            if (bones == null) return;
            Gizmos.color = new Color(1f, 0.6f, 0.1f, 0.9f);
            for (int i = 0; i < bones.Length; i++)
            {
                if (bones[i] == null) continue;
                Gizmos.DrawWireSphere(bones[i].position, Mathf.Max(0.005f, radius));
                if (i > 0 && bones[i - 1] != null) Gizmos.DrawLine(bones[i - 1].position, bones[i].position);
            }
        }
    }
}
