// AutoRig2DTests — EditMode tests for AutoRig2D and RigDriver2D. A small layered character is
// written as a PSB in the test (raw channels, luni and lyid per layer), imported by the PSD
// Importer and rigged from its layer names alone. Then: every layer has bones and every weight
// sums to 1; every SpriteSkin of the generated prefab and of the variant is Ready; the face
// library swaps the eyes; a raised arm, skinned on the CPU from the imported data and masked by
// the layer's own alpha, opens no hole and keeps the shoulder covered; the side run moves the
// legs in opposite phase; the spring on the bag stays finite and inside its angle limit; the pose
// gate passes the rig and fails a torso mesh with triangles missing; the rig.json reader flips y and
// normalises weights; and a rig-file layer the PSB lacks is a problem.
//
// Drop into an Editor test assembly (UNITY_INCLUDE_TESTS) that references the assemblies holding
// AutoRig2D.cs, Rig2DLayout.cs, SpriteLibraryBuilder.cs and RigDriver2D.cs, plus
// Unity.2D.Animation.Runtime/.Editor and Unity.2D.Psdimporter.Editor. Needs graphics (not
// -nographics): the layer alpha comes from a readable copy of the imported texture.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.U2D.Sprites;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.U2D;
using UnityEngine.U2D.Animation;

namespace UnityDev.Rig2D.Tests
{
    public class AutoRig2DTests
    {
        const string Folder = "Assets/AutoRig2DTests_Temp";
        const string Psb = Folder + "/Courier2D.psb";
        const int W = 200, H = 320;
        AutoRig2D.Result _result;
        readonly List<GameObject> _made = new List<GameObject>();

        [OneTimeSetUp]
        public void Build()
        {
            if (AssetDatabase.IsValidFolder(Folder)) AssetDatabase.DeleteAsset(Folder);
            AssetDatabase.CreateFolder("Assets", "AutoRig2DTests_Temp");
            File.WriteAllBytes(Psb, SyntheticPsb.Courier(W, H));
            AssetDatabase.ImportAsset(Psb, ImportAssetOptions.ForceSynchronousImport);
            _result = AutoRig2D.Rig(Psb, new AutoRig2D.Options());
        }

        [OneTimeTearDown]
        public void Remove() => AssetDatabase.DeleteAsset(Folder);

        [TearDown]
        public void TearDown()
        {
            foreach (GameObject go in _made) if (go) Object.DestroyImmediate(go);
            _made.Clear();
        }

        GameObject Spawn(string path)
        {
            var go = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(path));
            _made.Add(go);
            return go;
        }

        // a bone: the Transform of that name that renders nothing
        static Transform Bone(GameObject root, string name)
        {
            Transform[] all = root.GetComponentsInChildren<Transform>(true);
            Transform t = all.FirstOrDefault(x => x.name == name && x.GetComponent<SpriteRenderer>() == null);
            Assert.IsNotNull(t, "no bone " + name + " among " + string.Join(", ", all.Select(x => x.name)));
            return t;
        }

        [Test]
        public void EveryLayerIsRiggedAndWeightsSumToOne()
        {
            Assert.IsTrue(_result.Ok, _result.ToJson());
            Sprite[] sprites = AssetDatabase.LoadAllAssetsAtPath(Psb).OfType<Sprite>().ToArray();
            Assert.AreEqual(SyntheticPsb.LayerCount, sprites.Length);
            foreach (Sprite s in sprites)
            {
                Assert.Greater(s.GetBones().Length, 0, s.name + " has no bones");
                var w = s.GetVertexAttribute<BoneWeight>(VertexAttribute.BlendWeight);
                Assert.AreEqual(s.GetVertexCount(), w.Length, s.name);
                foreach (BoneWeight b in w)
                    Assert.AreEqual(1f, b.weight0 + b.weight1 + b.weight2 + b.weight3, 1e-3f, s.name);
            }
            Assert.IsFalse(AutoRig2D.IsHandRigged(Psb), "our own bones read as a hand rig");
        }

        [Test]
        public void SkeletonFollowsTheNamingConvention()
        {
            var dp = new SpriteDataProviderFactories();
            dp.Init();
            var p = dp.GetSpriteEditorDataProviderFromObject(AssetImporter.GetAtPath(Psb));
            p.InitSpriteEditorDataProvider();
            var cd = p.GetDataProvider<UnityEditor.U2D.Animation.ICharacterDataProvider>().GetCharacterData();
            var names = cd.bones.Select(b => b.name).ToList();
            foreach (string n in new[] { "hips", "chest", "neck", "face", "shoulder_L", "elbow_L", "wrist_L", "shoulder_R", "hip_L", "knee_L", "ankle_L", "bag_pivot", "hair_front_pivot" })
                Assert.Contains(n, names);
            SpriteBone Bone(string n) => cd.bones[names.IndexOf(n)];
            Assert.AreEqual("shoulder_L", names[Bone("elbow_L").parentId]);
            Assert.AreEqual("chest", names[Bone("shoulder_L").parentId]);
            Assert.AreEqual("hips", names[Bone("hip_R").parentId]);
            Assert.AreEqual("neck", names[Bone("hair_front_pivot").parentId]);
            Assert.AreNotEqual("neck", names[Bone("bag_pivot").parentId]);
            Assert.IsFalse(names.Any(n => n.EndsWith("_1")), "a bone shares a layer's name");
        }

        [Test]
        public void EverySpriteSkinIsReady()
        {
            foreach (string path in new[] { Psb, _result.variant })
            {
                Assert.IsNotNull(path);
                SpriteSkin[] skins = Spawn(path).GetComponentsInChildren<SpriteSkin>(true);
                Assert.AreEqual(SyntheticPsb.LayerCount, skins.Length, path);
                foreach (SpriteSkin sk in skins)
                    Assert.AreEqual(SpriteSkinState.Ready, AutoRig2D.SkinState(sk), path + " " + sk.name);
            }
        }

        [Test]
        public void VariantSwapsEyesAndMouthThroughTheLibrary()
        {
            Assert.IsNotNull(_result.library);
            GameObject go = Spawn(_result.variant);
            var drv = go.GetComponent<RigDriver2D>();
            Assert.IsNotNull(drv);
            Assert.AreEqual(1, drv.eyes.Length);
            Assert.AreEqual(1, drv.mouths.Length);
            Assert.IsFalse(go.GetComponentsInChildren<Transform>(true).First(t => t.name == "eyes_closed").gameObject.activeSelf);
            drv.Bind();
            SpriteRenderer eyes = drv.eyes[0].GetComponent<SpriteRenderer>();
            Assert.AreEqual("eyes_open", eyes.sprite.name);
            drv.SetEyes(false);
            Assert.AreEqual("eyes_closed", eyes.sprite.name);
            drv.SetMouth(true);
            Assert.AreEqual("mouth_open", drv.mouths[0].GetComponent<SpriteRenderer>().sprite.name);
            Assert.IsTrue(drv.springBones.Any(t => t.name == "bag_pivot"), "the bag layer should give a spring bone");
        }

        [Test]
        public void RaisedArmOpensNoHoleAndKeepsTheShoulderCovered()
        {
            GameObject go = Spawn(Psb);
            var drv = go.AddComponent<RigDriver2D>();
            drv.Bind();
            float ppu = ((UnityEditor.U2D.PSD.PSDImporter)AssetImporter.GetAtPath(Psb)).spritePixelsPerUnit;
            var tex = Readable();
            Transform hand = Bone(go, "wrist_L");
            Vector3 handRest = hand.position;
            Raster rest = Raster.Of(go, tex, ppu);
            drv.PoseArmUp();
            Transform shoulder = Bone(go, "shoulder_L");
            Assert.Greater(Vector3.Distance(hand.position, handRest) * ppu, 40f, "the arm did not move: the test would pass on nothing");
            Raster posed = Raster.Of(go, tex, ppu);
            // a hole the pose opened: background the outside cannot reach, where the rest pose was painted
            bool[] enclosed = posed.Enclosed();
            int newHoles = 0;
            for (int i = 0; i < enclosed.Length; i++) if (enclosed[i] && rest.on[i]) newHoles++;
            Assert.LessOrEqual(newHoles, 4, "raising the arm opened enclosed holes (px)");
            float cover = posed.DiskCoverage(shoulder.position, 6f / ppu);
            Assert.GreaterOrEqual(cover, 0.97f, "the shoulder joint is not covered once the arm is raised");
        }

        [Test]
        public void PoseGatePassesTheRigAndCatchesACutMesh()
        {
            Assert.Greater(_result.poseHoles.Count, 1, "the pose gate did not run: " + _result.ToJson());
            Assert.AreEqual(0, _result.poseHoles[0].holes, "solid pixels at rest that no triangle draws");
            Assert.IsFalse(_result.problems.Any(p => p.StartsWith("pose gate")), _result.ToJson());
            // a torso mesh with every third triangle gone, as a hand edit or a careless mesher
            // leaves it: background shows through the body at rest
            const string psb = Folder + "/Courier2D_cut.psb";
            File.WriteAllBytes(psb, SyntheticPsb.Courier(W, H));
            AssetDatabase.ImportAsset(psb, ImportAssetOptions.ForceSynchronousImport);
            Assert.IsTrue(AutoRig2D.Rig(psb, new AutoRig2D.Options { variant = false }).Ok);
            var f = new SpriteDataProviderFactories();
            f.Init();
            var dp = f.GetSpriteEditorDataProviderFromObject(AssetImporter.GetAtPath(psb));
            dp.InitSpriteEditorDataProvider();
            var mesh = dp.GetDataProvider<ISpriteMeshDataProvider>();
            SpriteRect torso = dp.GetSpriteRects().First(x => x.name == "torso");
            int[] idx = mesh.GetIndices(torso.spriteID);
            mesh.SetIndices(torso.spriteID, Enumerable.Range(0, idx.Length / 3).Where(t => t % 3 != 0).SelectMany(t => new[] { idx[3 * t], idx[3 * t + 1], idx[3 * t + 2] }).ToArray());
            mesh.SetEdges(torso.spriteID, Rig2DLayout.BoundaryEdges(mesh.GetIndices(torso.spriteID)));
            dp.Apply();
            ((UnityEditor.U2D.PSD.PSDImporter)AssetImporter.GetAtPath(psb)).SaveAndReimport();
            AutoRig2D.Result cut = AutoRig2D.PoseCheck(psb);
            Assert.Greater(cut.poseHoles[0].holes, 0, cut.ToJson());
            Assert.IsTrue(cut.problems.Any(p => p.Contains("drawn by no triangle")), "a cut mesh passed the pose gate: " + cut.ToJson());
        }

        [Test]
        public void SideRunMovesTheLegsInOppositePhase()
        {
            GameObject go = Spawn(_result.variant);
            var drv = go.GetComponent<RigDriver2D>();
            drv.view = RigDriver2D.View.Side;
            drv.motion = RigDriver2D.Motion.Run;
            drv.Bind();
            Transform l = Bone(go, "hip_L");
            Transform r = Bone(go, "hip_R");
            Quaternion l0 = l.localRotation, r0 = r.localRotation;
            drv.Evaluate(drv.stride * 0.25f);
            float dl = Mathf.DeltaAngle(0, (Quaternion.Inverse(l0) * l.localRotation).eulerAngles.z);
            float dr = Mathf.DeltaAngle(0, (Quaternion.Inverse(r0) * r.localRotation).eulerAngles.z);
            Assert.Greater(Mathf.Abs(dl), 20f);
            Assert.Less(dl * dr, 0f, "the legs swing together");
            drv.ResetPose();
            Assert.AreEqual(0f, Quaternion.Angle(l0, l.localRotation), 1e-3f);
        }

        [Test]
        public void SpringStaysFiniteAndInsideItsLimit()
        {
            GameObject go = Spawn(_result.variant);
            var drv = go.GetComponent<RigDriver2D>();
            drv.motion = RigDriver2D.Motion.Idle;
            drv.Bind();
            Transform bag = Bone(go, "bag_pivot");
            Assert.Contains(bag, drv.springBones);
            for (int f = 0; f < 240; f++)
            {
                go.transform.position = new Vector3(Mathf.Sin(f * 0.2f) * 0.3f, 0, 0);   // shake the body
                drv.Evaluate(f / 60f);
                Quaternion animated = bag.rotation;
                drv.StepSprings(1f / 60f);
                Assert.IsFalse(float.IsNaN(bag.rotation.z), "NaN at frame " + f);
                Assert.LessOrEqual(Quaternion.Angle(animated, bag.rotation), drv.springMaxAngle + 0.5f, "frame " + f);
            }
            float settled = 0f;
            for (int f = 0; f < 240; f++)
            {
                drv.Evaluate(4f);
                Quaternion animated = bag.rotation;
                drv.StepSprings(1f / 60f);
                settled = Quaternion.Angle(animated, bag.rotation);
            }
            Assert.Less(settled, 20f, "the bag does not settle once the body stops");
        }

        [Test]
        public void RigFileBonesNamedLikeLayersAreRenamed()
        {
            // a rig file beside the PSB whose bones carry part names (head, hand_L, foot_R …): the
            // importer would rename those to head_1 and nothing would find them
            const string psb = Folder + "/Courier2D_file.psb";
            WriteWithRigFile(psb, "");
            AutoRig2D.Result r = AutoRig2D.Rig(psb, new AutoRig2D.Options { variant = false });
            Assert.IsTrue(r.Ok, r.ToJson());
            Assert.AreEqual("rig.json", r.source);
            GameObject go = Spawn(psb);
            foreach (string n in new[] { "neck", "wrist_L", "ankle_R", "shoulder_L", "knee_R" }) Bone(go, n);
            Assert.IsFalse(go.GetComponentsInChildren<Transform>(true).Any(t => t.name.EndsWith("_1")), "a bone was renamed by the importer");
            foreach (SpriteSkin sk in go.GetComponentsInChildren<SpriteSkin>(true))
                Assert.AreEqual(SpriteSkinState.Ready, AutoRig2D.SkinState(sk), sk.name);
        }

        [Test]
        public void RigFileLayerWithNoSpriteIsAProblem()
        {
            // the rig file meshes a layer the PSB does not have (renamed, or a stale import): the
            // rig would come back without it and every other gate would still pass
            const string psb = Folder + "/Courier2D_renamed.psb";
            WriteWithRigFile(psb, ",\"parts\":[{\"name\":\"scarf\",\"bones\":[\"chest\"],\"verts\":[90,80,110,80,100,100]," +
                                  "\"indices\":[0,1,2],\"bw\":[0,1,0,0,0,1,0,0,0,1,0,0]}]");
            AutoRig2D.Result r = AutoRig2D.Rig(psb, new AutoRig2D.Options { variant = false });
            Assert.IsFalse(r.Ok, "a rig-file layer with no sprite passed: " + r.ToJson());
            Assert.IsTrue(r.problems.Any(p => p.Contains("layer scarf of the rig file has no sprite")), r.ToJson());
            Assert.AreEqual(1, r.problems.Count, "only the missing layer is a problem: " + r.ToJson());
        }

        // the synthetic courier, and beside it a rig2d/1 file with its bones (named like parts) plus extra
        static void WriteWithRigFile(string psb, string extra)
        {
            File.WriteAllBytes(psb, SyntheticPsb.Courier(W, H));
            var sb = new StringBuilder("{\"schema\":\"rig2d/1\",\"width\":" + W + ",\"height\":" + H + ",\"y_down\":true,\"view\":\"front\",\"bones\":[");
            var rows = new List<string>();
            void B(string n, string parent, float hx, float hy, float tx, float ty) =>
                rows.Add($"{{\"name\":\"{n}\",\"parent\":\"{parent}\",\"hx\":{hx},\"hy\":{H - hy},\"tx\":{tx},\"ty\":{H - ty}}}");
            B("hips", "", 100, 145, 100, 186); B("chest", "hips", 100, 186, 100, 243); B("head", "chest", 100, 243, 100, 304);
            foreach (var (k, m) in new[] { ("L", 1f), ("R", -1f) })
            {
                float X(float x) => 100 + m * (x - 100);
                B("upperarm_" + k, "chest", X(130), 226, X(138), 190); B("forearm_" + k, "upperarm_" + k, X(138), 190, X(144), 160);
                B("hand_" + k, "forearm_" + k, X(144), 160, X(148), 134);
                B("thigh_" + k, "hips", X(114), 132, X(116), 86); B("shin_" + k, "thigh_" + k, X(116), 86, X(118), 40);
                B("foot_" + k, "shin_" + k, X(118), 40, X(130), 18);
            }
            sb.Append(string.Join(",", rows)).Append(']').Append(extra).Append('}');
            File.WriteAllText(Path.ChangeExtension(psb, ".rig2d.json"), sb.ToString());
            AssetDatabase.ImportAsset(psb, ImportAssetOptions.ForceSynchronousImport);
        }

        [Test]
        public void RigJsonIsReadInImagePixelsWithYDown()
        {
            const string json = "{\"canvas\":[100,200],\"bones\":[{\"name\":\"hips\",\"parent\":null,\"head\":[50,120],\"tail\":[50,80]}," +
                                "{\"name\":\"chest\",\"parent\":\"hips\",\"head\":[50,80],\"tail\":[50,20]}]," +
                                "\"parts\":{\"torso\":{\"bones\":[\"hips\",\"chest\"],\"vertices\":[[40,100],[60,100],[50,30]],\"indices\":[0,1,2]," +
                                "\"weights\":[[[0,2.0],[1,2.0]],[[0,1.0]],[[1,0.5],[0,0.0]]]}}}";
            var problems = new List<string>();
            Assert.IsTrue(Rig2DLayout.ReadRigJson(json, out Rig2DLayout.RigFile rig, problems), string.Join("; ", problems));
            Assert.AreEqual(new Vector2(50, 80), rig.bones[0].head);
            Assert.AreEqual(new Vector2(50, 180), rig.bones[1].tail);
            BoneWeight[] w = rig.parts["torso"].weights;
            Assert.AreEqual(0.5f, w[0].weight0, 1e-5f);
            Assert.AreEqual(1f, w[1].weight0 + w[1].weight1, 1e-5f);
            Assert.AreEqual(1, w[2].boneIndex0);
            // rig2d/1, as layer_split.py writes it: flat vertex and weight lists, view and facing
            const string flat = "{\"schema\":\"rig2d/1\",\"width\":100,\"height\":200,\"y_down\":true,\"view\":\"side\",\"facing\":\"left\"," +
                                "\"bones\":[{\"name\":\"hips\",\"parent\":\"\",\"hx\":50,\"hy\":120,\"tx\":50,\"ty\":80}]," +
                                "\"parts\":[{\"name\":\"pelvis\",\"bones\":[\"hips\"],\"verts\":[40,130,60,130,50,110],\"indices\":[0,1,2],\"bw\":[0,1,0,0,0,1,0,0,0,1,0,0]}," +
                                "{\"name\":\"empty\",\"bones\":[\"hips\"],\"verts\":[],\"indices\":[],\"bw\":[]}]}";
            Assert.IsTrue(Rig2DLayout.ReadRigJson(flat, out rig, problems), string.Join("; ", problems));
            Assert.AreEqual("side", rig.view);
            Assert.AreEqual("left", rig.facing);
            Assert.AreEqual(new Vector2(40, 70), rig.parts["pelvis"].vertices[0]);
            Assert.AreEqual(1f, rig.parts["pelvis"].weights[2].weight0, 1e-5f);
            Assert.IsFalse(rig.parts.ContainsKey("empty"), "an empty part is meshed by the tool, not read");
            Assert.IsFalse(Rig2DLayout.ReadRigJson("{\"canvas\":[1,1],\"bones\":[{\"name\":\"a\",\"parent\":\"x\",\"head\":[0,0],\"tail\":[0,1]}]}",
                                                   out _, problems = new List<string>()));
        }

        static Texture2D Readable()
        {
            var f = new SpriteDataProviderFactories();
            f.Init();
            var dp = f.GetSpriteEditorDataProviderFromObject(AssetImporter.GetAtPath(Psb));
            dp.InitSpriteEditorDataProvider();
            return dp.GetDataProvider<ITextureDataProvider>().GetReadableTexture2D();
        }

        // ------------------------------------------------------------------ CPU skinning raster

        /// <summary>Every SpriteSkin skinned on the CPU (bone localToWorld × bind pose, as SpriteSkin
        /// does), rasterised at one cell per pixel and masked by the sprite's own alpha.</summary>
        sealed class Raster
        {
            public bool[] on; public int w, h; public Vector2 min; public float cell;

            public static Raster Of(GameObject root, Texture2D tex, float ppu)
            {
                var tris = new List<(Vector2 a, Vector2 b, Vector2 c, Vector2 ua, Vector2 ub, Vector2 uc)>();
                foreach (SpriteSkin sk in root.GetComponentsInChildren<SpriteSkin>())
                {
                    Sprite s = sk.GetComponent<SpriteRenderer>().sprite;
                    // copied at once: each accessor's native view is only valid until the next call
                    Vector3[] pos = s.GetVertexAttribute<Vector3>(VertexAttribute.Position).ToArray();
                    BoneWeight[] bw = s.GetVertexAttribute<BoneWeight>(VertexAttribute.BlendWeight).ToArray();
                    Vector2[] uv = s.GetVertexAttribute<Vector2>(VertexAttribute.TexCoord0).ToArray();
                    Matrix4x4[] bind = s.GetBindPoses().ToArray();
                    ushort[] idx = s.GetIndices().ToArray();
                    Transform[] bones = sk.boneTransforms;
                    var world = new Vector2[pos.Length];
                    for (int v = 0; v < pos.Length; v++)
                    {
                        BoneWeight q = bw[v];
                        Vector3 p = Vector3.zero;
                        p += q.weight0 * (bones[q.boneIndex0].localToWorldMatrix * bind[q.boneIndex0]).MultiplyPoint3x4(pos[v]);
                        p += q.weight1 * (bones[q.boneIndex1].localToWorldMatrix * bind[q.boneIndex1]).MultiplyPoint3x4(pos[v]);
                        p += q.weight2 * (bones[q.boneIndex2].localToWorldMatrix * bind[q.boneIndex2]).MultiplyPoint3x4(pos[v]);
                        p += q.weight3 * (bones[q.boneIndex3].localToWorldMatrix * bind[q.boneIndex3]).MultiplyPoint3x4(pos[v]);
                        world[v] = p;
                    }
                    for (int t = 0; t + 2 < idx.Length; t += 3)
                        tris.Add((world[idx[t]], world[idx[t + 1]], world[idx[t + 2]], uv[idx[t]], uv[idx[t + 1]], uv[idx[t + 2]]));
                }
                var r = new Raster { cell = 1f / ppu };
                // a fixed window around the root, wide enough for a raised arm
                r.min = (Vector2)root.transform.position - new Vector2(W, H) * r.cell;
                r.w = 3 * W; r.h = 3 * H;
                r.on = new bool[r.w * r.h];
                foreach (var tr in tris)
                {
                    Vector2 lo = Vector2.Min(tr.a, Vector2.Min(tr.b, tr.c)), hi = Vector2.Max(tr.a, Vector2.Max(tr.b, tr.c));
                    int x0 = Mathf.Max(0, Mathf.FloorToInt((lo.x - r.min.x) / r.cell)), x1 = Mathf.Min(r.w - 1, Mathf.CeilToInt((hi.x - r.min.x) / r.cell));
                    int y0 = Mathf.Max(0, Mathf.FloorToInt((lo.y - r.min.y) / r.cell)), y1 = Mathf.Min(r.h - 1, Mathf.CeilToInt((hi.y - r.min.y) / r.cell));
                    float den = (tr.b.y - tr.c.y) * (tr.a.x - tr.c.x) + (tr.c.x - tr.b.x) * (tr.a.y - tr.c.y);
                    if (Mathf.Abs(den) < 1e-12f) continue;
                    for (int y = y0; y <= y1; y++)
                        for (int x = x0; x <= x1; x++)
                        {
                            if (r.on[y * r.w + x]) continue;
                            Vector2 p = r.min + new Vector2(x + 0.5f, y + 0.5f) * r.cell;
                            float l1 = ((tr.b.y - tr.c.y) * (p.x - tr.c.x) + (tr.c.x - tr.b.x) * (p.y - tr.c.y)) / den;
                            float l2 = ((tr.c.y - tr.a.y) * (p.x - tr.c.x) + (tr.a.x - tr.c.x) * (p.y - tr.c.y)) / den;
                            float l3 = 1f - l1 - l2;
                            if (l1 < -1e-4f || l2 < -1e-4f || l3 < -1e-4f) continue;
                            Vector2 u = l1 * tr.ua + l2 * tr.ub + l3 * tr.uc;
                            if (tex.GetPixelBilinear(u.x, u.y).a > 0.5f) r.on[y * r.w + x] = true;
                        }
                }
                return r;
            }

            /// <summary>Background cells that the outside cannot reach (4-connected).</summary>
            public bool[] Enclosed()
            {
                var seen = new bool[on.Length];
                var q = new Queue<int>();
                for (int x = 0; x < w; x++) { Seed(x, 0); Seed(x, h - 1); }
                for (int y = 0; y < h; y++) { Seed(0, y); Seed(w - 1, y); }
                void Seed(int x, int y) { int i = y * w + x; if (!on[i] && !seen[i]) { seen[i] = true; q.Enqueue(i); } }
                while (q.Count > 0)
                {
                    int i = q.Dequeue(), x = i % w, y = i / w;
                    if (x > 0) Seed(x - 1, y);
                    if (x < w - 1) Seed(x + 1, y);
                    if (y > 0) Seed(x, y - 1);
                    if (y < h - 1) Seed(x, y + 1);
                }
                var enclosed = new bool[on.Length];
                for (int i = 0; i < on.Length; i++) enclosed[i] = !on[i] && !seen[i];
                return enclosed;
            }

            public float DiskCoverage(Vector2 c, float radius)
            {
                int hit = 0, all = 0;
                int r = Mathf.CeilToInt(radius / cell);
                int cx = Mathf.FloorToInt((c.x - min.x) / cell), cy = Mathf.FloorToInt((c.y - min.y) / cell);
                for (int y = cy - r; y <= cy + r; y++)
                    for (int x = cx - r; x <= cx + r; x++)
                    {
                        if (x < 0 || y < 0 || x >= w || y >= h) continue;
                        Vector2 p = min + new Vector2(x + 0.5f, y + 0.5f) * cell;
                        if ((p - c).sqrMagnitude > radius * radius) continue;
                        all++;
                        if (on[y * w + x]) hit++;
                    }
                return all == 0 ? 0f : hit / (float)all;
            }
        }

        // ------------------------------------------------------------------ the synthetic PSB

        /// <summary>A front-facing courier in flat shapes, one layer per part, overlapping at every
        /// joint, written as an 8-bit RGB PSB (version 2) with transparency, raw channels.</summary>
        static class SyntheticPsb
        {
            public const int LayerCount = 17;

            delegate bool Shape(float x, float y);   // document pixels, y up

            static Shape Circle(float cx, float cy, float r) => (x, y) => (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r;
            static Shape Ellipse(float cx, float cy, float rx, float ry) => (x, y) => (x - cx) * (x - cx) / (rx * rx) + (y - cy) * (y - cy) / (ry * ry) <= 1f;
            static Shape Box(float x0, float y0, float x1, float y1) => (x, y) => x >= x0 && x <= x1 && y >= y0 && y <= y1;
            static Shape Capsule(float ax, float ay, float bx, float by, float r) => (x, y) =>
                Rig2DLayout.SegmentDistance(new Vector2(x, y), new Vector2(ax, ay), new Vector2(bx, by)) <= r;
            static Shape Or(Shape a, Shape b) => (x, y) => a(x, y) || b(x, y);

            public static byte[] Courier(int w, int h)
            {
                // bottom to top, as the file stores them
                var hidden = new HashSet<string> { "eyes_closed", "mouth_open" };   // saved hidden, as a splitter does
                var layers = new (string name, Shape shape, Color32 colour)[]
                {
                    ("leg_R", Capsule(86, 140, 82, 32, 12), new Color32(40, 50, 90, 255)),
                    ("foot_R", Ellipse(78, 24, 16, 9), new Color32(30, 30, 30, 255)),
                    ("leg_L", Capsule(114, 140, 118, 32, 12), new Color32(40, 50, 90, 255)),
                    ("foot_L", Ellipse(122, 24, 16, 9), new Color32(30, 30, 30, 255)),
                    ("pelvis", Box(72, 122, 128, 168), new Color32(50, 60, 100, 255)),
                    ("bag", Box(128, 112, 150, 140), new Color32(150, 100, 40, 255)),
                    ("head", Circle(100, 272, 32), new Color32(240, 200, 170, 255)),
                    ("eyes_open", Or(Box(84, 274, 92, 282), Box(108, 274, 116, 282)), new Color32(20, 20, 20, 255)),
                    ("eyes_closed", Or(Box(83, 277, 93, 279), Box(107, 277, 117, 279)), new Color32(20, 20, 20, 255)),
                    ("mouth_closed", Box(93, 255, 107, 258), new Color32(120, 40, 40, 255)),
                    ("mouth_open", Ellipse(100, 256, 6, 5), new Color32(90, 20, 20, 255)),
                    ("torso", Or(Box(70, 150, 130, 240), Circle(100, 236, 12)), new Color32(230, 120, 30, 255)),
                    ("arm_R", Capsule(70, 234, 55, 152, 9), new Color32(230, 120, 30, 255)),
                    ("hand_R", Circle(53, 142, 10), new Color32(240, 200, 170, 255)),
                    ("arm_L", Capsule(130, 234, 145, 152, 9), new Color32(230, 120, 30, 255)),
                    ("hand_L", Circle(147, 142, 10), new Color32(240, 200, 170, 255)),
                    ("hair_front", Ellipse(100, 296, 30, 10), new Color32(60, 40, 30, 255)),
                };
                var b = new List<byte>();
                void U16(int v) { b.Add((byte)(v >> 8)); b.Add((byte)v); }
                void U32(long v) { for (int s = 24; s >= 0; s -= 8) b.Add((byte)(v >> s)); }
                void U64(long v) { for (int s = 56; s >= 0; s -= 8) b.Add((byte)(v >> s)); }
                void Ascii(string s) { b.AddRange(Encoding.ASCII.GetBytes(s)); }
                void Patch64(int at, long v) { for (int k = 0; k < 8; k++) b[at + k] = (byte)(v >> (56 - 8 * k)); }
                void Patch32(int at, long v) { for (int k = 0; k < 4; k++) b[at + k] = (byte)(v >> (24 - 8 * k)); }

                Ascii("8BPS"); U16(2); b.AddRange(new byte[6]);
                U16(4); U32(h); U32(w); U16(8); U16(3);      // RGB + transparency, 8 bit
                U32(0); U32(0);                              // colour mode data, image resources
                int lmi = b.Count; U64(0);
                int li = b.Count; U64(0);
                U16(layers.Length);
                // records: crop each layer to its opaque box (image rows, y down)
                var crops = new List<(int top, int left, int bottom, int right, byte[][] planes)>();
                var comp = new Color32[w * h];
                for (int n = 0; n < layers.Length; n++)
                {
                    var (name, shape, colour) = layers[n];
                    int top = h, left = w, bottom = 0, right = 0;
                    for (int y = 0; y < h; y++)
                        for (int x = 0; x < w; x++)
                            if (shape(x + 0.5f, h - y - 0.5f)) { top = Mathf.Min(top, y); left = Mathf.Min(left, x); bottom = Mathf.Max(bottom, y + 1); right = Mathf.Max(right, x + 1); }
                    int cw = right - left, ch = bottom - top;
                    var planes = new byte[4][];
                    for (int c = 0; c < 4; c++) planes[c] = new byte[cw * ch];
                    for (int y = 0; y < ch; y++)
                        for (int x = 0; x < cw; x++)
                        {
                            bool inside = shape(left + x + 0.5f, h - (top + y) - 0.5f);
                            int i = y * cw + x;
                            planes[0][i] = inside ? (byte)255 : (byte)0;     // channel -1: transparency
                            planes[1][i] = colour.r; planes[2][i] = colour.g; planes[3][i] = colour.b;
                            if (inside && !hidden.Contains(name)) comp[(top + y) * w + left + x] = colour;
                        }
                    crops.Add((top, left, bottom, right, planes));
                    U32(top); U32(left); U32(bottom); U32(right);
                    U16(4);
                    foreach (int id in new[] { -1, 0, 1, 2 }) { U16(id & 0xFFFF); U64(2 + cw * ch); }
                    Ascii("8BIMnorm"); b.Add(255); b.Add(0); b.Add((byte)(0x08 | (hidden.Contains(name) ? 0x02 : 0))); b.Add(0);
                    int extraAt = b.Count; U32(0);
                    int start = b.Count;
                    U32(0); U32(0);                                          // no mask, no blending ranges
                    byte[] latin = Encoding.ASCII.GetBytes(name);
                    b.Add((byte)latin.Length); b.AddRange(latin);
                    while ((b.Count - start - 8) % 4 != 0) b.Add(0);        // pascal name padded to 4
                    byte[] uni = Encoding.BigEndianUnicode.GetBytes(name);
                    int luniLen = 4 + uni.Length + (4 - (4 + uni.Length) % 4) % 4;
                    Ascii("8BIMluni"); U32(luniLen); U32(name.Length); b.AddRange(uni);
                    for (int k = 4 + uni.Length; k < luniLen; k++) b.Add(0);
                    Ascii("8BIMlyid"); U32(4); U32(n + 2);
                    Patch32(extraAt, b.Count - start);
                }
                foreach (var cr in crops)
                    foreach (byte[] plane in cr.planes) { U16(0); b.AddRange(plane); }
                while ((b.Count - li - 8) % 4 != 0) b.Add(0);
                Patch64(li, b.Count - li - 8);
                U32(0);                                                      // global layer mask info
                Patch64(lmi, b.Count - lmi - 8);
                U16(0);                                                      // merged image, raw, planar
                for (int c = 0; c < 4; c++)
                    for (int i = 0; i < w * h; i++)
                        b.Add(c == 0 ? comp[i].r : c == 1 ? comp[i].g : c == 2 ? comp[i].b : comp[i].a);
                return b.ToArray();
            }
        }
    }
}
