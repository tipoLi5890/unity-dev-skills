// SecondaryMotionTests — EditMode tests for the spring-bone runtime: a chain hangs under gravity and
// keeps its bone lengths, springs back without it, stays outside sphere and capsule colliders,
// resets instead of exploding on a teleport, settles the same at 30, 144 and jittered frame
// rates, moves on every frame at 144 Hz and at an uneven 60 Hz, respects its angle limit, returns unanimated bones to rest, survives a zero-length bone,
// and the secondary/1 reader accepts the sample and an empty chain list and refuses broken files.
//
// Drop it into an EditMode test assembly that references the assembly holding SpringSolver.cs,
// SpringChain.cs, SpringCollider.cs, SecondaryMotionSystem.cs and SecondarySpec.cs (nunit, no
// scene, no Animator, no play mode). AddComponent in Edit mode runs no OnEnable, so each test calls
// Rebuild() and steps with Simulate(dt).
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace UnityDev.SecondaryMotion.Tests
{
    public class SecondaryMotionTests
    {
        const float Dt = 1f / 60f;
        readonly List<GameObject> _made = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (GameObject go in _made) if (go != null) Object.DestroyImmediate(go);
            _made.Clear();
        }

        // root (system) / parent / b0 / b1 / ... / tip, every segment `segment` long along `dir`.
        SecondaryMotionSystem Rig(int segments, Vector3 dir, float segment, out SpringChain chain)
        {
            var root = new GameObject("Model");
            _made.Add(root);
            var parent = new GameObject("Parent").transform;
            parent.SetParent(root.transform, false);
            parent.localPosition = Vector3.up;
            var bones = new Transform[segments + 1];
            Transform up = parent;
            for (int i = 0; i <= segments; i++)
            {
                var b = new GameObject(i == segments ? "cc_test_end.x" : "cc_test_0" + (i + 1) + ".x").transform;
                b.SetParent(up, false);
                b.localPosition = i == 0 ? Vector3.zero : dir.normalized * segment;
                bones[i] = b;
                up = b;
            }
            chain = bones[0].gameObject.AddComponent<SpringChain>();
            chain.bones = bones;
            chain.stiffness = 0f;
            chain.drag = 0.2f;
            chain.gravity = 1f;
            chain.radius = 0.02f;
            chain.maxAngle = 180f;
            var system = root.AddComponent<SecondaryMotionSystem>();
            system.skipWhenInvisible = false;
            return system;
        }

        SpringCollider AddCollider(SecondaryMotionSystem system, Vector3 a, Vector3? b, float r)
        {
            var go = new GameObject("SM_Collider_test");
            go.transform.SetParent(system.transform, false);
            go.transform.position = a;
            var col = go.AddComponent<SpringCollider>();
            col.radius = r;
            if (b.HasValue)
            {
                var end = new GameObject("end").transform;
                end.SetParent(system.transform, false);
                end.position = b.Value;
                col.shape = SpringCollider.Shape.Capsule;
                col.endB = end;
            }
            else col.shape = SpringCollider.Shape.Sphere;
            return col;
        }

        static void Run(SecondaryMotionSystem system, float seconds, float dt = Dt)
        {
            for (float t = 0f; t < seconds - 1e-5f; t += dt) system.Simulate(dt);
        }

        static float ChainLength(SpringChain chain)
        {
            float len = 0f;
            for (int i = 1; i < chain.bones.Length; i++) len += Vector3.Distance(chain.bones[i - 1].position, chain.bones[i].position);
            return len;
        }

        static void AssertFinite(SpringChain chain)
        {
            foreach (Transform b in chain.bones)
            {
                Assert.IsTrue(SpringSolver.IsFinite(b.position), b.name + " position is not finite");
                Quaternion q = b.rotation;
                Assert.IsFalse(float.IsNaN(q.x) || float.IsNaN(q.y) || float.IsNaN(q.z) || float.IsNaN(q.w), b.name + " rotation is NaN");
            }
        }

        [Test]
        public void Gravity_settles_chain_below_parent()
        {
            SecondaryMotionSystem system = Rig(3, Vector3.right, 0.1f, out SpringChain chain);
            float rest = ChainLength(chain);
            system.Rebuild();
            Run(system, 3f);
            Transform root = chain.bones[0], tip = chain.bones[3];
            Assert.GreaterOrEqual(root.position.y - tip.position.y, 0.9f * rest, "the tip hangs below its root");
            for (int i = 1; i < chain.bones.Length; i++)
                Assert.AreEqual(0.1f, Vector3.Distance(chain.bones[i - 1].position, chain.bones[i].position), 1e-3f, "segment " + i + " keeps its length");
        }

        [Test]
        public void Stiffness_returns_to_rest_without_gravity()
        {
            SecondaryMotionSystem system = Rig(3, Vector3.right, 0.1f, out SpringChain chain);
            Vector3 restTip = chain.bones[3].position;
            chain.stiffness = 0.5f;
            chain.gravity = 2f;
            system.Rebuild();
            Run(system, 1f);
            Assert.Greater(Vector3.Distance(chain.bones[3].position, restTip), 0.01f, "gravity moved the tip first");
            chain.gravity = 0f;
            Run(system, 3f);
            Assert.AreEqual(0f, Vector3.Distance(chain.bones[3].position, restTip), 1e-3f, "the tip is back on the animated tip");
        }

        [Test]
        public void Sphere_collider_keeps_particles_outside()
        {
            SecondaryMotionSystem system = Rig(4, Vector3.right, 0.1f, out SpringChain chain);
            Vector3 c = chain.bones[0].position + new Vector3(0.22f, -0.13f, 0.01f);
            AddCollider(system, c, null, 0.1f);
            system.Rebuild();
            for (int f = 0; f < 180; f++)
            {
                system.Simulate(Dt);
                for (int i = 1; i < chain.ParticleCount; i++)
                    Assert.GreaterOrEqual(Vector3.Distance(chain.GetParticle(i), c), 0.1f + chain.radius - 1e-3f, "frame " + f + " particle " + i);
            }
        }

        [Test]
        public void Capsule_collider_keeps_particles_outside()
        {
            SecondaryMotionSystem system = Rig(4, Vector3.right, 0.1f, out SpringChain chain);
            Vector3 o = chain.bones[0].position;
            Vector3 a = o + new Vector3(0.2f, -0.12f, -0.3f), b = o + new Vector3(0.2f, -0.12f, 0.3f);
            AddCollider(system, a, b, 0.08f);
            system.Rebuild();
            for (int f = 0; f < 180; f++)
            {
                system.Simulate(Dt);
                for (int i = 1; i < chain.ParticleCount; i++)
                {
                    float d = SpringSolver.SurfaceDistance(chain.GetParticle(i), a, b, 0.08f);
                    Assert.GreaterOrEqual(d, chain.radius - 1e-3f, "frame " + f + " particle " + i);
                }
            }
        }

        [Test]
        public void Teleport_does_not_explode()
        {
            SecondaryMotionSystem system = Rig(3, Vector3.right, 0.1f, out SpringChain chain);
            system.Rebuild();
            Run(system, 1f);
            system.transform.position += new Vector3(100f, 0f, 0f);
            system.Simulate(Dt);
            float length = ChainLength(chain);
            for (int i = 0; i < chain.ParticleCount; i++)
            {
                Assert.LessOrEqual(Vector3.Distance(chain.GetParticle(i), chain.bones[0].position), length + 1e-3f, "particle " + i + " near its root");
                Assert.AreEqual(0f, Vector3.Distance(chain.GetParticle(i), chain.GetTarget(i)), 1e-4f, "particle " + i + " on the animated pose");
            }
            Run(system, 0.5f);
            AssertFinite(chain);
        }

        [Test]
        public void Frame_rate_independent()
        {
            Vector3 Tip(float[] dts)
            {
                SecondaryMotionSystem system = Rig(3, Vector3.right, 0.1f, out SpringChain chain);
                chain.drag = 0.3f;
                chain.stiffness = 0.2f;
                system.Rebuild();
                system.Simulate(0f);
                float t = 0f;
                foreach (float dt in dts)
                {
                    t += dt;
                    // Runs at 2 m/s for 0.3 s, then stops: the chain swings and settles.
                    system.transform.position = new Vector3(Mathf.Min(t, 0.3f) * 2f, 0f, 0f);
                    system.Simulate(dt);
                }
                return chain.bones[3].position;
            }
            float[] Even(float dt, int n) { var a = new float[n]; for (int i = 0; i < n; i++) a[i] = dt; return a; }
            var rng = new System.Random(7);
            var jitter = new List<float>();
            for (float sum = 0f; sum < 1.5f - 1e-4f;)
            {
                float dt = Mathf.Min(1.5f - sum, (float)(0.004 + rng.NextDouble() * 0.04));
                jitter.Add(dt);
                sum += dt;
            }
            Vector3 at30 = Tip(Even(1f / 30f, 45)), at144 = Tip(Even(1f / 144f, 216)), atJitter = Tip(jitter.ToArray());
            Assert.AreEqual(0f, Vector3.Distance(at30, at144), 0.01f, "30 fps vs 144 fps");
            Assert.AreEqual(0f, Vector3.Distance(at30, atJitter), 0.01f, "30 fps vs jittered");
        }

        [Test]
        public void Chain_moves_every_frame_at_high_and_uneven_rates()
        {
            // A frame with no substep must not leave the chain where it was while the body turns
            // on (a one-frame stick): at 144 Hz, and on a 60 Hz frame that comes in short, the
            // written tip still moves every frame.
            foreach (bool uneven in new[] { false, true })
            {
                SecondaryMotionSystem system = Rig(2, Vector3.right, 0.1f, out SpringChain chain);
                chain.gravity = 0f;
                chain.stiffness = 0.2f;
                system.Rebuild();
                system.Simulate(0f);
                var rng = new System.Random(3);
                float t = 0f;
                Vector3 last = chain.bones[2].position;
                for (int f = 0; f < 200; f++)
                {
                    float dt = uneven ? (float)(0.0155 + rng.NextDouble() * 0.0023) : 1f / 144f;
                    t += dt;
                    system.transform.rotation = Quaternion.Euler(0f, 90f * t, 0f);
                    system.Simulate(dt);
                    Vector3 now = chain.bones[2].position;
                    if (f > 20)
                        Assert.Greater(Vector3.Distance(now, last), 1e-5f, (uneven ? "uneven 60 Hz" : "144 Hz") + ": frame " + f + " did not move");
                    last = now;
                }
                AssertFinite(chain);
            }
        }

        [Test]
        public void Max_angle_clamps()
        {
            SecondaryMotionSystem system = Rig(3, Vector3.right, 0.1f, out SpringChain chain);
            chain.gravity = 5f;
            chain.maxAngle = 20f;
            system.Rebuild();
            for (int f = 0; f < 120; f++)
            {
                system.Simulate(Dt);
                for (int i = 1; i < chain.bones.Length; i++)
                {
                    Vector3 seg = chain.bones[i].position - chain.bones[i - 1].position;
                    Assert.LessOrEqual(Vector3.Angle(Vector3.right, seg), 20.5f, "frame " + f + " segment " + i);
                }
            }
            Assert.Greater(Vector3.Angle(Vector3.right, chain.bones[1].position - chain.bones[0].position), 15f, "gravity reached the limit");
        }

        [Test]
        public void Unanimated_bone_restores_rest()
        {
            SecondaryMotionSystem system = Rig(3, Vector3.right, 0.1f, out SpringChain chain);
            var rest = new Quaternion[chain.bones.Length];
            for (int i = 0; i < rest.Length; i++) rest[i] = chain.bones[i].localRotation;
            chain.stiffness = 0.1f;
            system.Rebuild();
            Run(system, 1f);
            Assert.Greater(Quaternion.Angle(rest[0], chain.bones[0].localRotation), 5f, "the spring turned the bone");
            // No Animator writes these bones: each frame they must restart from rest, or the sagged
            // pose would become the target and stiffness 1 would hold it there.
            chain.gravity = 0f;
            chain.stiffness = 1f;
            Run(system, 2f);
            for (int i = 0; i < rest.Length - 1; i++)
                Assert.Less(Quaternion.Angle(rest[i], chain.bones[i].localRotation), 0.05f, "bone " + i + " back at rest");
        }

        [Test]
        public void Zero_length_segment_has_no_NaN()
        {
            SecondaryMotionSystem system = Rig(3, Vector3.right, 0.1f, out SpringChain chain);
            chain.bones[1].localPosition = Vector3.zero;      // b1 on b0
            chain.bones[3].localPosition = Vector3.zero;      // tip on b2
            AddCollider(system, chain.bones[0].position, null, 0.05f);
            system.Rebuild();
            Run(system, 1f);
            system.transform.position += Vector3.right * 0.3f;
            Run(system, 1f);
            AssertFinite(chain);
            for (int i = 0; i < chain.ParticleCount; i++) Assert.IsTrue(SpringSolver.IsFinite(chain.GetParticle(i)), "particle " + i);
        }

        const string Sample = @"{
  ""schema"": ""secondary/1"", ""tool"": ""secondary_chains.py"",
  ""producer"": {""skill"": ""character-autorig"", ""script"": ""secondary_chains.py""},
  ""character"": ""Runner"", ""units"": ""m"", ""up"": ""+Z"", ""forward"": ""-Y"",
  ""chains"": [
    {""name"": ""hood"", ""kind"": ""hood"", ""parent"": ""neck.x"", ""parent_role"": ""Neck"",
     ""bones"": [""cc_hood_01.x"", ""cc_hood_02.x"", ""cc_hood_end.x""],
     ""joints"": [[0, 0.10, 1.47], [0, 0.15, 1.40], [0, 0.17, 1.32]],
     ""parent_head"": [-0.0018, 0.0457, 1.4263],
     ""radius"": 0.04, ""stiffness"": 0.35, ""drag"": 0.35, ""gravity"": 0.6, ""wind"": 0.2,
     ""max_angle_deg"": 40, ""colliders"": [""Chest"", ""UpperChest""], ""weighted_vertices"": 1211}
  ],
  ""colliders"": [
    {""name"": ""Chest"", ""shape"": ""capsule"", ""a"": ""spine_02.x"", ""b"": ""spine_03.x"",
     ""a_role"": ""Chest"", ""b_role"": ""UpperChest"", ""radius"": 0.13},
    {""name"": ""UpperChest"", ""shape"": ""capsule"", ""a"": ""spine_03.x"", ""b"": ""neck.x"", ""radius"": 0.12},
    {""name"": ""Head"", ""shape"": ""sphere"", ""a"": ""head.x"", ""a_role"": ""Head"",
     ""center"": [0, -0.01, 1.62], ""radius"": 0.11}
  ]
}";

        [Test]
        public void Spec_parses_and_refuses()
        {
            Assert.IsTrue(SecondarySpec.TryParse(Sample, out SecondarySpec spec, out string error), error);
            Assert.AreEqual("Runner", spec.character);
            Assert.AreEqual(1, spec.chains.Length);
            SecondaryChainSpec hood = spec.chains[0];
            Assert.AreEqual(3, hood.bones.Length);
            Assert.AreEqual(1f, hood.inertia, "inertia defaults to 1 when the file leaves it out");
            Assert.IsTrue(hood.hasColliders);
            Assert.AreEqual(3, hood.joints.Length);
            Assert.AreEqual(new Vector3(0f, 1.32f, -0.17f), SecondarySpec.ToUnity(hood.joints[2]));
            Assert.AreEqual(3, spec.colliders.Length);
            Assert.IsTrue(spec.colliders[2].hasCenter);

            void Refused(string json, string expect)
            {
                Assert.IsFalse(SecondarySpec.TryParse(json, out _, out string why), "accepted: " + expect);
                StringAssert.Contains(expect, why);
            }
            Refused(Sample.Replace("secondary/1", "secondary/2"), "schema");
            Refused(Sample.Replace(@"[""cc_hood_01.x"", ""cc_hood_02.x"", ""cc_hood_end.x""]", "[]"), "no bones");
            Refused(Sample.Replace(@", ""cc_hood_end.x""]", "]"), "not a tip");
            Refused(Sample.Replace(@"""cc_hood_01.x"", ""cc_hood_02.x"", ""cc_hood_end.x""", @"""cc_hood_01.x"""), "no tip");
            Refused(Sample.Replace(@"""stiffness"": 0.35", @"""stiffness"": 1.5"), "stiffness");
            Refused(Sample.Replace(@"""Chest"", ""UpperChest""]", @"""Chest"", ""Pelvis""]"), "Pelvis");
            Refused(Sample.Replace(@"""max_angle_deg"": 40,", ""), "max_angle_deg");
            Refused(Sample.Substring(0, 40), "not JSON");
        }

        [Test]
        public void Spec_with_no_chains_is_valid()
        {
            const string none = @"{""schema"": ""secondary/1"", ""tool"": ""secondary_chains.py"", ""character"": ""Runner"",
  ""units"": ""m"", ""up"": ""+Z"", ""forward"": ""-Y"", ""chains"": [], ""colliders"": []}";
            Assert.IsTrue(SecondarySpec.TryParse(none, out SecondarySpec spec, out string error), error);
            Assert.AreEqual(0, spec.chains.Length);
            Assert.AreEqual(0, spec.colliders.Length);
        }
    }
}
