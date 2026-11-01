// SecondaryMotionSystem — steps every SpringChain under the model after the Animator has posed it:
// hood, bag, hem and hair swing with the run, settle when it stops, and stay outside the body's
// SpringColliders. Plain C#, no package, no allocation per frame.
//
// Put it on the GameObject that holds the Animator (the model, under the prefab's Rig child), not
// on the gameplay root: lengths and radii are in the model's units and scale with it.
// SecondaryMotionSetup (Editor) adds it, the chains and the colliders from a secondary/1 file.
//
// Needs Optimize Game Objects OFF on the model: with it on, the bones are not the transforms
// that skin the mesh, so writing them moves nothing. It checks Animator.hasTransformHierarchy
// and switches itself off with one message.
//
// Each frame (LateUpdate, after the Animator):
//   1. the animated pose: chain bones the clip did not write go back to rest; targets read;
//   2. a reset instead of a step on enable, ResetPose(), a teleport (moved more than
//      teleportDistance or turned more than teleportAngle in one frame) and on coming back on
//      screen after being skipped;
//   3. fixed substeps of 1/substepRate, at most maxSubsteps a frame (the rest of a long frame is
//      dropped): Verlet with drag, gravity and wind; pull to the animated pose; colliders; angle
//      clamp; exact bone length. Fixed, because the sag a pull-to-pose spring settles at depends
//      on the substep length;
//   4. each bone turned along its segment, read between the last two substeps by the time left
//      over, so a frame with no substep (144 Hz, a 60 Hz frame that came in short) still moves.
//
// Cost per frame: substeps x sum over chains of particles x (1 + colliders it tests), plus one
// FromToRotation per bone. Call ResetPose() after a spawn, a respawn, a pooled reuse or a cut.
using UnityEngine;

namespace UnityDev.SecondaryMotion
{
    [DefaultExecutionOrder(1000)]
    public sealed class SecondaryMotionSystem : MonoBehaviour
    {
        [Tooltip("Substeps per second. 60 suits every parameter as written.")]
        public float substepRate = 60f;
        [Tooltip("Most substeps in one frame; a longer frame drops the rest instead of spiralling.")]
        public int maxSubsteps = 4;
        [Tooltip("Longest frame the step accepts, in seconds (a hitch counts as this much).")]
        public float maxFrameDt = 1f / 15f;

        [Tooltip("World units moved in one frame that count as a teleport (reset, no step).")]
        public float teleportDistance = 1f;
        [Tooltip("Degrees turned in one frame that count as a teleport.")]
        public float teleportAngle = 90f;

        [Tooltip("World acceleration the chains' gravity multiplies.")]
        public Vector3 gravity = new Vector3(0f, -9.81f, 0f);

        public Vector3 windDirection = Vector3.right;
        [Tooltip("Wind acceleration; each chain multiplies it by its own wind.")]
        public float windStrength;
        [Tooltip("Gusts per second.")]
        public float windFrequency = 0.6f;

        [Tooltip("Skip the step while no SkinnedMeshRenderer under the model is visible; reset on return.")]
        public bool skipWhenInvisible = true;
        public bool useUnscaledTime;

        SpringChain[] _chains = new SpringChain[0];
        SpringCollider[] _colliders = new SpringCollider[0];
        SkinnedMeshRenderer[] _renderers = new SkinnedMeshRenderer[0];
        Animator _animator;

        Vector3[] _colA0, _colB0, _colA1, _colB1, _colA, _colB;
        float[] _colR;

        Vector3 _simRoot, _lastRootPos;
        Quaternion _lastRootRot;
        bool _hasLastRoot, _needsReset = true, _built, _warned;
        float _accumulator, _time;

        public SpringChain[] Chains => _chains;
        public SpringCollider[] Colliders => _colliders;
        public int ParticleCount
        {
            get { int n = 0; foreach (SpringChain c in _chains) n += c.ParticleCount; return n; }
        }

        void OnEnable()
        {
            Rebuild();
        }

        void OnDisable()
        {
            foreach (SpringChain c in _chains) if (c != null) c.RestoreWritten();
        }

        /// <summary>Collects chains and colliders under this GameObject (inactive ones too), sizes
        /// the state and resets on the next step. Call after adding or removing a chain.</summary>
        public void Rebuild()
        {
            _animator = GetComponent<Animator>();
            if (_animator == null) _animator = GetComponentInChildren<Animator>(true);
            _renderers = GetComponentsInChildren<SkinnedMeshRenderer>(true);
            _colliders = GetComponentsInChildren<SpringCollider>(true);

            SpringChain[] found = GetComponentsInChildren<SpringChain>(true);
            // Parents before children, so a chain hanging from another chain reads it after its write.
            System.Array.Sort(found, (x, y) => Depth(x.transform).CompareTo(Depth(y.transform)));
            int valid = 0;
            for (int i = 0; i < found.Length; i++)
            {
                string error = found[i].Init(_colliders);
                if (error != null) Debug.LogWarning("[SECONDARY] " + error + " — chain skipped", found[i]);
                else found[valid++] = found[i];
            }
            _chains = new SpringChain[valid];
            System.Array.Copy(found, _chains, valid);

            int k = _colliders.Length;
            _colA0 = new Vector3[k]; _colB0 = new Vector3[k];
            _colA1 = new Vector3[k]; _colB1 = new Vector3[k];
            _colA = new Vector3[k * Mathf.Max(1, maxSubsteps)]; _colB = new Vector3[_colA.Length];
            _colR = new float[k];
            _built = true;
            _needsReset = true;
            _hasLastRoot = false;
        }

        /// <summary>Snap every chain to the animated pose on the next step, with no velocity.</summary>
        public void ResetPose()
        {
            _needsReset = true;
        }

        void LateUpdate()
        {
            if (_animator != null && !_animator.hasTransformHierarchy)
            {
                if (!_warned)
                    Debug.LogWarning("[SECONDARY] " + name + ": Optimize Game Objects is on — chain bones are not " +
                                     "the transforms that skin the mesh. Turn it off on the model's Rig tab.", this);
                _warned = true;
                enabled = false;
                return;
            }
            if (!useUnscaledTime && Time.timeScale == 0f) return;
            if (skipWhenInvisible && _renderers.Length > 0)
            {
                bool any = false;
                foreach (SkinnedMeshRenderer r in _renderers) if (r != null && r.isVisible) { any = true; break; }
                if (!any) { _needsReset = true; return; }
            }
            Simulate(useUnscaledTime ? Time.unscaledDeltaTime : Time.deltaTime);
        }

        /// <summary>One frame of dt seconds: animated pose, substeps, write. LateUpdate calls it; a
        /// test or a manual recorder calls it after posing the model (e.g. after Animator.Update).</summary>
        public void Simulate(float dt)
        {
            if (!_built) Rebuild();
            if (_chains.Length == 0 || dt < 0f) return;
            float scale = Mathf.Abs(transform.lossyScale.x);
            if (scale < 1e-6f) return;

            Transform root = transform;
            if (_hasLastRoot &&
                (Vector3.Distance(root.position, _lastRootPos) > teleportDistance ||
                 Quaternion.Angle(root.rotation, _lastRootRot) > teleportAngle))
                _needsReset = true;
            _lastRootPos = root.position;
            _lastRootRot = root.rotation;
            _hasLastRoot = true;

            for (int c = 0; c < _colliders.Length; c++)
            {
                if (_colliders[c] == null) { _colR[c] = 0f; continue; }
                _colliders[c].GetWorld(scale, out _colA1[c], out _colB1[c], out _colR[c]);
            }

            bool reset = _needsReset;
            _needsReset = false;
            float h = 1f / Mathf.Max(1f, substepRate);
            int steps = 0;
            if (reset)
            {
                System.Array.Copy(_colA1, _colA0, _colA1.Length);
                System.Array.Copy(_colB1, _colB0, _colB1.Length);
                _simRoot = root.position;
                _accumulator = 0f;
            }
            else
            {
                _accumulator += Mathf.Min(dt, maxFrameDt);
                steps = Mathf.FloorToInt((_accumulator + h * 1e-3f) / h);
                int cap = Mathf.Max(1, maxSubsteps);
                if (steps > cap) { steps = cap; _accumulator = 0f; }
                else _accumulator = Mathf.Max(0f, _accumulator - steps * h);
            }
            float alpha = Mathf.Clamp01(_accumulator / h);

            // Collider ends at the end of each substep, interpolated from the last simulated pose.
            int k = _colliders.Length;
            if (_colA.Length < steps * k) { _colA = new Vector3[steps * k]; _colB = new Vector3[steps * k]; }
            for (int s = 0; s < steps; s++)
            {
                float a = (s + 1f) / steps;
                for (int c = 0; c < k; c++)
                {
                    _colA[s * k + c] = Vector3.Lerp(_colA0[c], _colA1[c], a);
                    _colB[s * k + c] = Vector3.Lerp(_colB0[c], _colB1[c], a);
                }
            }
            Vector3 rootDelta = steps > 0 ? (root.position - _simRoot) / steps : Vector3.zero;
            Vector3 windDir = windDirection.sqrMagnitude > 1e-12f ? windDirection.normalized : Vector3.zero;

            // Chain by chain, parents first: a chain hanging from another reads it after its write.
            for (int i = 0; i < _chains.Length; i++)
            {
                SpringChain chain = _chains[i];
                chain.Capture();
                if (reset) chain.ResetParticles();
                for (int s = 0; s < steps; s++)
                {
                    float t = _time + (s + 1) * h;
                    float gust = 0.6f + 0.4f * Mathf.Sin(2f * Mathf.PI * windFrequency * t + i * 1.3f);
                    Vector3 accel = gravity * chain.gravity + windDir * (windStrength * chain.wind * gust);
                    chain.Step(h, (s + 1f) / steps, accel, rootDelta, scale, _colA, _colB, _colR, s * k);
                }
                if (steps > 0) chain.EndSubsteps();
                chain.Write(alpha, scale, _colA1, _colB1, _colR);
            }
            if (steps > 0)
            {
                _time += steps * h;
                System.Array.Copy(_colA1, _colA0, _colA1.Length);
                System.Array.Copy(_colB1, _colB0, _colB1.Length);
                _simRoot = root.position;
            }
        }

        static int Depth(Transform t)
        {
            int d = 0;
            for (; t != null; t = t.parent) d++;
            return d;
        }
    }
}
