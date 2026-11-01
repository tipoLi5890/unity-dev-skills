// AutoRig2D.cs — rigs a layered PSB with no Skinning Editor step: bones from the layer names
// and positions (or a layer splitter's rig.json), a grid mesh and two-bone weights per layer,
// written through the same data providers the Skinning Editor's Apply uses. Then a Sprite
// Library of the swappable face states, and a Prefab Variant with resolvers and RigDriver2D.
//
// Copy beside Rig2DLayout.cs and SpriteLibraryBuilder.cs into an Editor folder whose asmdef
// references Unity.2D.Animation.Runtime, Unity.2D.Animation.Editor, Unity.2D.Psdimporter.Editor,
// Unity.2D.Sprite.Editor and the runtime assembly holding RigDriver2D.cs.
// REQUIRES com.unity.2d.animation and com.unity.2d.psdimporter (13.x/12.x on 6000.3, 14.x/13.x
// on 6000.4).
//
//   Tools/Unity Dev/2D Animation/Auto-Rig Selected PSB     (asks before replacing a hand rig)
//
//   Unity -batchmode -projectPath P -executeMethod UnityDev.Rig2D.AutoRig2D.RunFromCommandLine -quit
//       -rig2dPsb Assets/Art/Runner/Runner.psb        one or more, comma separated
//       [-rig2dJson Assets/Art/Runner/rig2d.json]     bones and meshes from the splitter (default:
//                                                     Runner.rig2d.json or rig2d.json beside the
//                                                     PSB; "none": from the layer names only)
//       [-rig2dPpu 512]                               pixels per unit to set on the importer
//       [-rig2dView front|side] [-rig2dFacing right|left]   the variant's run cycle (default:
//                                                     what the rig file says, else front, right)
//       [-rig2dOverwrite]                             replace a rig not written by this tool
//       [-rig2dReport Logs/autorig2d.json]
//   exits 0 rigged, 2 a gate failed or a hand rig was left alone, 1 usage error, 3 harness error.
//
// Gates (report "problems"): every layer gets bones; every weight sums to 1; every SpriteSkin
// of the generated prefab is Ready; the pose gate (PoseGate) skins the prefab in the standard
// poses and finds no layer pixel left undrawn at rest, no seam opening at a bending joint and
// every limb joint covered. Bone GUIDs are a hash of the bone name, so a re-run over a
// repainted file keeps every binding, and a rig whose GUIDs are not ours is a hand rig.
// Renaming a layer makes it a new sprite with no rig: re-run this after any rename.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.U2D.Animation;
using UnityEditor.U2D.PSD;
using UnityEditor.U2D.Sprites;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.U2D;
using UnityEngine.U2D.Animation;

namespace UnityDev.Rig2D
{
    public static class AutoRig2D
    {
        const string MenuPath = "Tools/Unity Dev/2D Animation/Auto-Rig Selected PSB";
        // A rig file's mesh must draw this share of the layer's solid pixels (pixel centres inside
        // a triangle); every pixel it leaves out renders as background, a sliver along the edge.
        public const float MinCover = 0.9995f;
        // Pose gate: background cells inside the silhouette, as a share of it. At rest the drawing
        // is the silhouette; in a pose, what a 2-cell closing fills beyond the rest pose's own.
        public const float MaxRestHoles = 0.0005f, MaxPoseHoles = 0.002f;
        // ... and every limb joint keeps this share of a JointDisc-cell disc round it covered
        public const float MinJointCover = 0.97f, JointDisc = 6f;
        static readonly string[] LimbJoints = { "elbow_", "wrist_", "hip_", "knee_", "ankle_" };

        public sealed class Options
        {
            public string rigJson;            // a rig2d.json path; null: the one beside the PSB if any
                                              // (SiblingRigFile); "none": from the layers only
            public float pixelsPerUnit;       // 0: keep the importer's value
            public RigDriver2D.View? view;    // null: the rig file's view, else front
            public bool? facesRight;          // null: the rig file's facing, else right
            public bool overwrite;            // replace bones another tool or a person wrote
            public bool variant = true;       // write <name>_Rig.prefab when it does not exist
        }

        public sealed class Result
        {
            public string psb, source = "layers", library, variant;
            public int sprites, rigged, badWeights, skins, skinsReady, bones;
            public readonly List<string> parts = new List<string>();
            public readonly List<string> notes = new List<string>();
            public readonly List<string> problems = new List<string>();
            public bool handRig;
            /// <summary>Per standard pose: background cells inside the silhouette (pose gate).</summary>
            public readonly List<(string pose, int holes)> poseHoles = new List<(string, int)>();
            public int silhouette;
            public float jointCover = 1f;
            public string jointWorst = "";
            public bool Ok => problems.Count == 0;

            public string ToJson()
            {
                var sb = new StringBuilder("{");
                sb.Append("\"psb\":").Append(Str(psb)).Append(",\"source\":").Append(Str(source))
                  .Append(",\"bones\":").Append(bones).Append(",\"sprites\":").Append(sprites)
                  .Append(",\"rigged\":").Append(rigged).Append(",\"badWeights\":").Append(badWeights)
                  .Append(",\"skins\":").Append(skins).Append(",\"skinsReady\":").Append(skinsReady)
                  .Append(",\"silhouette\":").Append(silhouette)
                  .Append(",\"jointCover\":").Append(jointCover.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture))
                  .Append(",\"jointWorst\":").Append(Str(jointWorst))
                  .Append(",\"poseHoles\":{").Append(string.Join(",", poseHoles.Select(p => Str(p.pose) + ":" + p.holes))).Append('}')
                  .Append(",\"library\":").Append(Str(library)).Append(",\"variant\":").Append(Str(variant))
                  .Append(",\"parts\":[").Append(string.Join(",", parts.Select(Str))).Append(']')
                  .Append(",\"notes\":[").Append(string.Join(",", notes.Select(Str))).Append(']')
                  .Append(",\"problems\":[").Append(string.Join(",", problems.Select(Str))).Append(']')
                  .Append(",\"ok\":").Append(Ok ? "true" : "false").Append('}');
                return sb.ToString();
            }
        }

        static string Str(string s) => s == null ? "null"
            : "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "") + "\"";

        // ------------------------------------------------------------------ entry points

        [MenuItem(MenuPath)]
        static void Menu()
        {
            foreach (string path in Selection.objects.Select(AssetDatabase.GetAssetPath).Where(IsPsb).Distinct())
            {
                var o = new Options();
                if (IsHandRigged(path) && !EditorUtility.DisplayDialog("Auto-Rig",
                        path + " has bones this tool did not write. Replace the whole rig?", "Replace", "Keep"))
                    continue;
                o.overwrite = true;
                Result r = Rig(path, o);
                Debug.Log("AutoRig2D " + r.ToJson());
            }
        }

        [MenuItem(MenuPath, true)]
        static bool MenuValid() => Selection.objects.Select(AssetDatabase.GetAssetPath).Any(IsPsb);

        static bool IsPsb(string p) => AssetImporter.GetAtPath(p) is PSDImporter;

        /// <summary>For -executeMethod. Exits 0 rigged, 2 a gate failed or a hand rig was kept,
        /// 1 usage error, 3 harness error.</summary>
        public static void RunFromCommandLine()
        {
            int code;
            try { code = Run(Environment.GetCommandLineArgs()); }
            catch (Exception e) { Debug.LogError("AutoRig2D: " + e); code = 3; }
            EditorApplication.Exit(code);
        }

        static int Run(string[] args)
        {
            string Arg(string k) { int i = Array.IndexOf(args, k); return i >= 0 && i + 1 < args.Length ? args[i + 1] : null; }
            string psbs = Arg("-rig2dPsb");
            if (string.IsNullOrEmpty(psbs)) { Debug.LogError("AutoRig2D: -rig2dPsb is required"); return 1; }
            var o = new Options { rigJson = Arg("-rig2dJson"), overwrite = Array.IndexOf(args, "-rig2dOverwrite") >= 0 };
            string ppu = Arg("-rig2dPpu"), view = Arg("-rig2dView"), facing = Arg("-rig2dFacing");
            if (facing != null)
            {
                if (facing != "right" && facing != "left") { Debug.LogError("AutoRig2D: -rig2dFacing is right or left"); return 1; }
                o.facesRight = facing == "right";
            }
            if (ppu != null && !float.TryParse(ppu, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out o.pixelsPerUnit))
            { Debug.LogError("AutoRig2D: -rig2dPpu takes a number"); return 1; }
            if (view != null)
            {
                if (view == "front") o.view = RigDriver2D.View.Front;
                else if (view == "side") o.view = RigDriver2D.View.Side;
                else { Debug.LogError("AutoRig2D: -rig2dView is front or side"); return 1; }
            }
            string report = Arg("-rig2dReport") ?? "Logs/autorig2d.json";
            var rows = new List<string>();
            int code = 0;
            foreach (string psb in psbs.Split(',').Select(s => s.Trim()).Where(s => s.Length > 0))
            {
                if (!IsPsb(psb)) { Debug.LogError("AutoRig2D: not a PSD Importer asset: " + psb); return 1; }
                Result r = Rig(psb, o);
                rows.Add(r.ToJson());
                if (!r.Ok) code = 2;
            }
            string dir = Path.GetDirectoryName(report);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(report, "[" + string.Join(",\n", rows) + "]\n");
            Debug.Log("AutoRig2D report " + report + ": " + string.Join(",", rows));
            return code;
        }

        // ------------------------------------------------------------------ the rig

        public static string StableGuid(string bone)
        {
            using (var md5 = MD5.Create())
                return string.Concat(md5.ComputeHash(Encoding.UTF8.GetBytes("autorig2d-bone/" + bone)).Select(b => b.ToString("x2")));
        }

        static ISpriteEditorDataProvider Provider(string path)
        {
            var factory = new SpriteDataProviderFactories();
            factory.Init();
            var dp = factory.GetSpriteEditorDataProviderFromObject(AssetImporter.GetAtPath(path));
            if (dp == null) throw new InvalidOperationException(path + " has no sprite data provider");
            dp.InitSpriteEditorDataProvider();
            return dp;
        }

        /// <summary>`Runner.rig2d.json` or `rig2d.json` beside the PSB, or null.</summary>
        public static string SiblingRigFile(string psb)
        {
            string a = Path.ChangeExtension(psb, ".rig2d.json"), b = Path.Combine(Path.GetDirectoryName(psb) ?? "", "rig2d.json");
            return File.Exists(a) ? a : File.Exists(b) ? b.Replace('\\', '/') : null;
        }

        /// <summary>True when the file has bones and any of them was not written by this tool.</summary>
        public static bool IsHandRigged(string path)
        {
            var cdp = Provider(path).GetDataProvider<ICharacterDataProvider>();
            if (cdp == null) return false;
            var bones = cdp.GetCharacterData().bones;
            return bones != null && bones.Any(b => b.guid != StableGuid(b.name));
        }

        /// <summary>Rigs one PSB and reports. Writes the importer data, the .spriteLib and (when
        /// missing) the variant; leaves a hand rig alone unless o.overwrite.</summary>
        public static Result Rig(string path, Options o)
        {
            var r = new Result { psb = path };
            var imp = (PSDImporter)AssetImporter.GetAtPath(path);
            bool dirty = false;
            if (!imp.useMosaicMode) { imp.useMosaicMode = true; dirty = true; }
            if (!imp.useCharacterMode) { imp.useCharacterMode = true; dirty = true; }
            if (o.pixelsPerUnit > 0 && Math.Abs(imp.spritePixelsPerUnit - o.pixelsPerUnit) > 1e-3f) { imp.spritePixelsPerUnit = o.pixelsPerUnit; dirty = true; }
            // hidden layers are the swap states a splitter saves hidden (eyes_closed, mouth_open):
            // without this they never become sprites. The setting has no public property.
            var so = new SerializedObject(imp);
            SerializedProperty hidden = so.FindProperty("m_ImportHiddenLayers");
            if (hidden != null && !hidden.boolValue) { hidden.boolValue = true; so.ApplyModifiedPropertiesWithoutUndo(); dirty = true; }
            if (dirty) imp.SaveAndReimport();
            if (!o.overwrite && IsHandRigged(path))
            {
                r.handRig = true;
                r.problems.Add("bones not written by AutoRig2D are present; pass -rig2dOverwrite (or answer Replace) to replace them");
                return r;
            }

            var dp = Provider(path);
            var cdp = dp.GetDataProvider<ICharacterDataProvider>();
            var bdp = dp.GetDataProvider<ISpriteBoneDataProvider>();
            var mdp = dp.GetDataProvider<ISpriteMeshDataProvider>();
            if (cdp == null || bdp == null || mdp == null) { r.problems.Add("not imported as a character (2D Animation missing?)"); return r; }
            CharacterData cd = cdp.GetCharacterData();
            SpriteRect[] rects = dp.GetSpriteRects();
            var layers = ReadLayers(dp, rects, cd);

            // skeleton: rig.json when given, the layer names otherwise
            List<Bone2D> bones;
            var given = new Dictionary<string, Part2D>(StringComparer.OrdinalIgnoreCase);
            RigDriver2D.View view = o.view ?? RigDriver2D.View.Front;
            bool facesRight = o.facesRight ?? true;
            string rigFile = o.rigJson ?? SiblingRigFile(path);
            if (rigFile == "none") rigFile = null;
            if (!string.IsNullOrEmpty(rigFile))
            {
                r.notes.Add("rig file: " + rigFile);
                if (!File.Exists(rigFile)) { r.problems.Add("rig file not found: " + rigFile); return r; }
                if (!Rig2DLayout.ReadRigJson(File.ReadAllText(rigFile), out Rig2DLayout.RigFile file, r.problems)) return r;
                bones = file.bones;
                given = file.parts;
                if (o.view == null && file.view == "side") view = RigDriver2D.View.Side;
                if (o.facesRight == null && file.facing == "left") facesRight = false;
                r.source = "rig.json";
            }
            else
            {
                bones = Rig2DLayout.InferBones(layers.Values.ToList(), r.notes);
                if (bones == null) { r.problems.AddRange(r.notes); return r; }
            }
            Rig2DLayout.NormalizeBoneNames(bones, given, layers.Keys, r.notes);
            r.bones = bones.Count;
            var byName = bones.ToDictionary(b => b.name);
            var index = new Dictionary<string, int>();
            for (int i = 0; i < bones.Count; i++) index[bones[i].name] = i;

            cd.bones = bones.Select((b, i) => MakeBone(b, byName, string.IsNullOrEmpty(b.parent),
                string.IsNullOrEmpty(b.parent) ? -1 : index[b.parent], Vector2.zero, i)).ToArray();
            // Edit the parts the getter returned and hand that array back: the setter stores them
            // reversed and the getter matches them to sprites by id, so a part is never rebuilt.
            CharacterPart[] parts = cd.parts;
            foreach (SpriteRect rect in rects)
            {
                int pi = Array.FindIndex(parts, p => p.spriteId == rect.spriteID.ToString());
                if (pi < 0 || !layers.TryGetValue(rect.name, out Layer2D layer)) { r.notes.Add("no character part for " + rect.name); continue; }
                Part2D part;
                if (given.TryGetValue(rect.name, out part) && part.bones.All(byName.ContainsKey))
                {
                    float cover = Rig2DLayout.Coverage(layer, part);
                    if (cover < MinCover) { r.notes.Add($"{rect.name}: the rig file's mesh covers {cover:P2} of the layer; meshed here instead"); part = null; }
                }
                else part = null;
                if (part == null)
                {
                    part = Rig2DLayout.GridMesh(layer, Rig2DLayout.PartBones(layer, byName));
                    float shortSide = Mathf.Min(layer.rect.width, layer.rect.height);
                    Rig2DLayout.DistanceWeights(part, byName, 0.2f * shortSide);
                }
                Vector2 origin = parts[pi].spritePosition.position, size = parts[pi].spritePosition.size;
                // a sprite's bone list runs parents first; weights follow the reordering
                int[] sub = part.bones.Select(b => index[b]).OrderBy(x => x).ToArray();
                int[] remap = part.bones.Select(b => Array.IndexOf(sub, index[b])).ToArray();
                parts[pi].bones = sub;
                var spriteBones = new List<SpriteBone>();
                for (int k = 0; k < sub.Length; k++)
                {
                    string parent = bones[sub[k]].parent;
                    int parentInSub = string.IsNullOrEmpty(parent) ? -1 : Array.IndexOf(sub, index[parent]);
                    spriteBones.Add(MakeBone(bones[sub[k]], byName, parentInSub < 0, parentInSub, origin, sub[k]));
                }
                bdp.SetBones(rect.spriteID, spriteBones);
                var verts = new Vertex2DMetaData[part.vertices.Length];
                for (int v = 0; v < verts.Length; v++)
                {
                    Vector2 p = part.vertices[v] - origin;
                    verts[v].position = new Vector2(Mathf.Clamp(p.x, 0, size.x), Mathf.Clamp(p.y, 0, size.y));
                    BoneWeight w = part.weights[v];
                    w.boneIndex0 = remap[w.boneIndex0];
                    w.boneIndex1 = remap[w.boneIndex1];
                    verts[v].boneWeight = w;
                }
                mdp.SetVertices(rect.spriteID, verts);
                mdp.SetIndices(rect.spriteID, part.indices);
                mdp.SetEdges(rect.spriteID, Rig2DLayout.BoundaryEdges(part.indices));
                r.parts.Add($"{rect.name}: {string.Join("+", part.bones)} v{verts.Length} t{part.indices.Length / 3}");
            }
            cd.parts = parts;
            cdp.SetCharacterData(cd);
            dp.Apply();
            imp.SaveAndReimport();

            Verify(path, r);
            // every layer the rig file names must have come back as a sprite: an import over the
            // settings of a differently cut file can drop one and still pass the gates above
            var spriteNames = new HashSet<string>(AssetDatabase.LoadAllAssetsAtPath(path).OfType<Sprite>().Select(s => s.name), StringComparer.OrdinalIgnoreCase);
            foreach (string name in given.Keys.Where(n => !spriteNames.Contains(n)))
                r.problems.Add($"layer {name} of the rig file has no sprite: a renamed layer, or a stale import (delete the PSB's .meta and re-run)");
            r.library = BuildLibrary(path, layers.Keys, r);
            if (o.variant) r.variant = BuildVariant(path, r.library, view, facesRight, r);
            PoseGate(r.variant ?? path, path, layers, r);
            return r;
        }

        // One SpriteBone, in pixels. A root (asRoot) sits at its document position minus origin
        // with its world angle; any other bone is local to its parent, x along the parent bone.
        // CharacterData passes origin 0 and the skeleton index of the parent; a sprite's own list
        // passes the sprite's document corner, and a bone whose parent is not in the list is a root.
        static SpriteBone MakeBone(Bone2D b, Dictionary<string, Bone2D> byName, bool asRoot, int parentId, Vector2 origin, int colour)
        {
            float Ang(Bone2D x) { Vector2 d = x.tail - x.head; return Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg; }
            Vector3 pos; Quaternion rot;
            if (asRoot) { pos = b.head - origin; rot = Quaternion.Euler(0, 0, Ang(b)); }
            else
            {
                Bone2D p = byName[b.parent];
                pos = Quaternion.Inverse(Quaternion.Euler(0, 0, Ang(p))) * (Vector3)(b.head - p.head);
                rot = Quaternion.Euler(0, 0, Ang(b) - Ang(p));
            }
            return new SpriteBone
            {
                name = b.name, guid = StableGuid(b.name), position = new Vector3(pos.x, pos.y, 0), rotation = rot,
                length = (b.tail - b.head).magnitude, parentId = asRoot ? -1 : parentId,
                color = Color.HSVToRGB(colour * 0.13f % 1f, 0.7f, 1f)
            };
        }

        // Every layer's alpha, from the importer's readable copy of the packed texture.
        static Dictionary<string, Layer2D> ReadLayers(ISpriteEditorDataProvider dp, SpriteRect[] rects, CharacterData cd)
        {
            var tex = dp.GetDataProvider<ITextureDataProvider>()?.GetReadableTexture2D();
            if (tex == null) throw new InvalidOperationException("no readable texture (run with graphics, not -nographics)");
            Color32[] px = tex.GetPixels32();
            var layers = new Dictionary<string, Layer2D>(StringComparer.Ordinal);
            foreach (SpriteRect rect in rects)
            {
                int pi = Array.FindIndex(cd.parts, p => p.spriteId == rect.spriteID.ToString());
                if (pi < 0) continue;
                RectInt doc = cd.parts[pi].spritePosition;
                float sx = rect.rect.width / Mathf.Max(doc.width, 1), sy = rect.rect.height / Mathf.Max(doc.height, 1);
                var mask = new bool[doc.width * doc.height];
                var solid = new bool[mask.Length];
                for (int y = 0; y < doc.height; y++)
                    for (int x = 0; x < doc.width; x++)
                    {
                        int tx = Mathf.Clamp((int)(rect.rect.x + (x + 0.5f) * sx), 0, tex.width - 1);
                        int ty = Mathf.Clamp((int)(rect.rect.y + (y + 0.5f) * sy), 0, tex.height - 1);
                        byte a = px[ty * tex.width + tx].a;
                        mask[y * doc.width + x] = a > 8;
                        solid[y * doc.width + x] = a >= 128;
                    }
                layers[rect.name] = new Layer2D { name = rect.name, rect = doc, mask = mask, solid = solid };
            }
            return layers;
        }

        // ------------------------------------------------------------------ pose gate

        /// <summary>The standard poses (front: rest, arm up, head turn, crouch, all three; side:
        /// rest, four phases of the run, and with a held prop the attack drawn back and at the hit) skinned on the CPU as SpriteSkin does (bone
        /// localToWorld x bind pose), rasterised one cell per document pixel and masked by each
        /// sprite's alpha, so no player loop or GPU is needed. Counts background cells inside the
        /// silhouette: at rest, solid layer pixels no triangle draws; in a pose, cells a 2-cell
        /// closing fills beyond what it fills at rest (a seam that opens at a bending joint).</summary>
        public static void PoseGate(string prefabPath, string psb, Dictionary<string, Layer2D> layers, Result r,
                                    params (string name, Action<RigDriver2D> set)[] extra)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            Texture2D tex = Provider(psb).GetDataProvider<ITextureDataProvider>()?.GetReadableTexture2D();
            if (prefab == null || tex == null) { r.notes.Add("pose gate skipped: no prefab or readable texture"); return; }
            var inst = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            try
            {
                var drv = inst.GetComponent<RigDriver2D>() ?? inst.AddComponent<RigDriver2D>();
                drv.Bind();
                var skins = inst.GetComponentsInChildren<SpriteSkin>().Where(k => k.GetComponent<SpriteRenderer>().sprite != null).ToArray();
                if (skins.Length == 0) return;
                float ppu = skins[0].GetComponent<SpriteRenderer>().sprite.pixelsPerUnit;
                // world to document pixels, from the rest pose: doc = world * ppu + offset
                Vector2 offset = Vector2.zero; int n = 0;
                foreach (SpriteSkin sk in skins)
                {
                    Sprite s = sk.GetComponent<SpriteRenderer>().sprite;
                    if (!layers.TryGetValue(s.name, out Layer2D l)) continue;
                    Vector2[] w = Skin(sk);
                    Vector3[] pos = s.GetVertexAttribute<Vector3>(VertexAttribute.Position).ToArray();
                    for (int v = 0; v < pos.Length; v++)
                    { offset += (Vector2)l.rect.position + (Vector2)pos[v] * ppu + s.pivot - w[v] * ppu; n++; }
                }
                if (n == 0) { r.notes.Add("pose gate skipped: no sprite matches a layer"); return; }
                offset /= n;
                var poses = new List<(string name, Action set)>();
                if (drv.view == RigDriver2D.View.Side)
                {
                    poses.Add(("rest", () => { }));
                    for (int q = 0; q < 4; q++) { float t = q * 0.25f * drv.stride; poses.Add(("run" + q, () => drv.RunSide(t))); }
                    // a held prop (prop_<name>_X) attacks: the poke drawn back and at the hit
                    if (layers.Keys.Any(k => k.StartsWith("prop_", StringComparison.OrdinalIgnoreCase)))
                        foreach (float p in new[] { 0.4f, 0.58f }) poses.Add(("attack" + p.ToString("0.00", CultureInfo.InvariantCulture), () => drv.Attack(p * drv.attackPeriod)));
                }
                else
                    poses.AddRange(new (string, Action)[] { ("rest", () => { }), ("armup", drv.PoseArmUp), ("headturn", drv.PoseHeadTurn),
                        ("crouch", drv.PoseCrouch), ("combo", () => { drv.PoseArmUp(); drv.PoseHeadTurn(); drv.PoseCrouch(); }) });
                foreach (var (name, set) in extra) poses.Add((name, () => set(drv)));
                var shots = new List<(string name, List<(Vector2 a, Vector2 b, Vector2 c, Vector2 ua, Vector2 ub, Vector2 uc)> tris, List<(string, Vector2)> joints)>();
                // a joint is a seam only where art hangs on both sides of it: a hidden arm (bones, no
                // layers) or a prop on the forearm alone has nothing there to part
                var weighted = new HashSet<Transform>(skins.SelectMany(k => k.boneTransforms ?? new Transform[0]).Where(t => t != null));
                Transform[] limbJoints = inst.GetComponentsInChildren<Transform>(true)
                    .Where(t => t.GetComponent<SpriteRenderer>() == null && t.parent != null && LimbJoints.Any(j => t.name.StartsWith(j))
                                && weighted.Contains(t) && weighted.Contains(t.parent)).ToArray();
                // where the parent puts each joint: a part pulled off its joint leaves this spot bare
                drv.ResetPose();
                Vector3[] jointRest = limbJoints.Select(t => t.localPosition).ToArray();
                foreach (var (name, set) in poses)
                {
                    drv.ResetPose(); set();
                    var tris = new List<(Vector2, Vector2, Vector2, Vector2, Vector2, Vector2)>();
                    foreach (SpriteSkin sk in skins)
                    {
                        Sprite s = sk.GetComponent<SpriteRenderer>().sprite;
                        Vector2[] w = Skin(sk);
                        Vector2[] uv = s.GetVertexAttribute<Vector2>(VertexAttribute.TexCoord0).ToArray();
                        ushort[] idx = s.GetIndices().ToArray();
                        for (int t = 0; t + 2 < idx.Length; t += 3)
                            tris.Add((w[idx[t]] * ppu + offset, w[idx[t + 1]] * ppu + offset, w[idx[t + 2]] * ppu + offset, uv[idx[t]], uv[idx[t + 1]], uv[idx[t + 2]]));
                    }
                    shots.Add((name, tris, limbJoints.Select((t, i) => (t.name, (Vector2)t.parent.TransformPoint(jointRest[i]) * ppu + offset)).ToList()));
                }
                drv.ResetPose();
                // one window for every pose, 4 cells of margin
                Vector2 lo = new Vector2(float.MaxValue, float.MaxValue), hi = -lo;
                foreach (var sh in shots) foreach (var t in sh.tris) { lo = Vector2.Min(lo, Vector2.Min(t.a, Vector2.Min(t.b, t.c))); hi = Vector2.Max(hi, Vector2.Max(t.a, Vector2.Max(t.b, t.c))); }
                int x0 = Mathf.FloorToInt(lo.x) - 4, y0 = Mathf.FloorToInt(lo.y) - 4, W = Mathf.CeilToInt(hi.x) + 4 - x0, H = Mathf.CeilToInt(hi.y) + 4 - y0;
                var ideal = new bool[W * H];
                var shown = new HashSet<string>(skins.Select(k => k.GetComponent<SpriteRenderer>().sprite.name));
                foreach (Layer2D l in layers.Values.Where(l => shown.Contains(l.name)))
                    for (int y = 0; y < l.rect.height; y++)
                        for (int x = 0; x < l.rect.width; x++)
                        {
                            int cx = l.rect.x + x - x0, cy = l.rect.y + y - y0;
                            if ((l.solid ?? l.mask)[y * l.rect.width + x] && cx >= 0 && cy >= 0 && cx < W && cy < H) ideal[cy * W + cx] = true;
                        }
                r.silhouette = ideal.Count(b => b);
                int restClosed = 0;
                foreach (var sh in shots)
                {
                    bool[] on = Rasterise(sh.tris, tex, x0, y0, W, H);
                    int holes;
                    if (sh.name == "rest")
                    {
                        holes = 0;
                        bool[] drawn = Rasterise(sh.tris, null, x0, y0, W, H);
                        for (int i = 0; i < on.Length; i++) if (ideal[i] && !drawn[i]) holes++;
                        restClosed = ClosingGain(on, W, H);
                        if (holes > MaxRestHoles * r.silhouette)
                            r.problems.Add($"pose gate: {holes} solid layer pixels at rest are drawn by no triangle (background shows through; limit {MaxRestHoles:P2} of the silhouette)");
                    }
                    else
                    {
                        holes = Mathf.Max(0, ClosingGain(on, W, H) - restClosed);
                        if (holes > MaxPoseHoles * r.silhouette)
                            r.problems.Add($"pose gate: {sh.name} opens {holes} background cells inside the silhouette (limit {MaxPoseHoles:P1} of it): a seam at a bending joint");
                    }
                    r.poseHoles.Add((sh.name, holes));
                    // every limb joint stays covered: a disc of JointDisc cells round it
                    foreach (var (joint, at) in sh.joints)
                    {
                        float c = DiscCover(on, x0, y0, W, H, at, JointDisc);
                        if (c < r.jointCover) { r.jointCover = c; r.jointWorst = sh.name + "/" + joint; }
                    }
                }
                if (r.jointCover < MinJointCover)
                    r.problems.Add($"pose gate: the joint {r.jointWorst} is covered {r.jointCover:P0} (limit {MinJointCover:P0}): the layers part there and background shows");
            }
            finally { UnityEngine.Object.DestroyImmediate(inst); }
        }

        /// <summary>The pose gate alone on an imported, rigged PSB (its variant when there is one),
        /// with extra poses after the standard ones.</summary>
        public static Result PoseCheck(string psb, params (string name, Action<RigDriver2D> set)[] extra)
        {
            var r = new Result { psb = psb };
            var dp = Provider(psb);
            var layers = ReadLayers(dp, dp.GetSpriteRects(), dp.GetDataProvider<ICharacterDataProvider>().GetCharacterData());
            string variant = Path.ChangeExtension(psb, null) + "_Rig.prefab";
            PoseGate(AssetDatabase.LoadAssetAtPath<GameObject>(variant) != null ? variant : psb, psb, layers, r, extra);
            return r;
        }

        static float DiscCover(bool[] on, int x0, int y0, int W, int H, Vector2 c, float radius)
        {
            int hit = 0, all = 0, rr = Mathf.CeilToInt(radius);
            for (int y = Mathf.FloorToInt(c.y) - rr; y <= Mathf.FloorToInt(c.y) + rr; y++)
                for (int x = Mathf.FloorToInt(c.x) - rr; x <= Mathf.FloorToInt(c.x) + rr; x++)
                {
                    if ((new Vector2(x + 0.5f, y + 0.5f) - c).sqrMagnitude > radius * radius) continue;
                    all++;
                    int cx = x - x0, cy = y - y0;
                    if (cx >= 0 && cy >= 0 && cx < W && cy < H && on[cy * W + cx]) hit++;
                }
            return all == 0 ? 1f : hit / (float)all;
        }

        // a SpriteSkin's vertices in world space, skinned as the package does
        static Vector2[] Skin(SpriteSkin sk)
        {
            Sprite s = sk.GetComponent<SpriteRenderer>().sprite;
            // copied at once: each accessor's native view is only valid until the next call
            Vector3[] pos = s.GetVertexAttribute<Vector3>(VertexAttribute.Position).ToArray();
            BoneWeight[] bw = s.GetVertexAttribute<BoneWeight>(VertexAttribute.BlendWeight).ToArray();
            Matrix4x4[] bind = s.GetBindPoses().ToArray();
            Transform[] bones = sk.boneTransforms;
            var m = bones.Select((b, i) => b.localToWorldMatrix * bind[i]).ToArray();
            var w = new Vector2[pos.Length];
            for (int v = 0; v < pos.Length; v++)
            {
                BoneWeight q = bw[v];
                w[v] = q.weight0 * m[q.boneIndex0].MultiplyPoint3x4(pos[v]) + q.weight1 * m[q.boneIndex1].MultiplyPoint3x4(pos[v])
                     + q.weight2 * m[q.boneIndex2].MultiplyPoint3x4(pos[v]) + q.weight3 * m[q.boneIndex3].MultiplyPoint3x4(pos[v]);
            }
            return w;
        }

        // cells whose centre lies in a triangle and whose texel there is at least half opaque
        static bool[] Rasterise(List<(Vector2 a, Vector2 b, Vector2 c, Vector2 ua, Vector2 ub, Vector2 uc)> tris, Texture2D tex, int x0, int y0, int W, int H)
        {
            // tex null: what the triangles cover, whatever the texture holds there
            var on = new bool[W * H];
            foreach (var tr in tris)
            {
                float den = (tr.b.y - tr.c.y) * (tr.a.x - tr.c.x) + (tr.c.x - tr.b.x) * (tr.a.y - tr.c.y);
                if (Mathf.Abs(den) < 1e-9f) continue;
                int xa = Mathf.Max(0, Mathf.FloorToInt(Mathf.Min(tr.a.x, Mathf.Min(tr.b.x, tr.c.x))) - x0), xb = Mathf.Min(W - 1, Mathf.CeilToInt(Mathf.Max(tr.a.x, Mathf.Max(tr.b.x, tr.c.x))) - x0);
                int ya = Mathf.Max(0, Mathf.FloorToInt(Mathf.Min(tr.a.y, Mathf.Min(tr.b.y, tr.c.y))) - y0), yb = Mathf.Min(H - 1, Mathf.CeilToInt(Mathf.Max(tr.a.y, Mathf.Max(tr.b.y, tr.c.y))) - y0);
                for (int y = ya; y <= yb; y++)
                    for (int x = xa; x <= xb; x++)
                    {
                        if (on[y * W + x]) continue;
                        float px = x0 + x + 0.5f, py = y0 + y + 0.5f;
                        float l1 = ((tr.b.y - tr.c.y) * (px - tr.c.x) + (tr.c.x - tr.b.x) * (py - tr.c.y)) / den;
                        float l2 = ((tr.c.y - tr.a.y) * (px - tr.c.x) + (tr.a.x - tr.c.x) * (py - tr.c.y)) / den;
                        float l3 = 1f - l1 - l2;
                        if (l1 < -1e-4f || l2 < -1e-4f || l3 < -1e-4f) continue;
                        Vector2 u = l1 * tr.ua + l2 * tr.ub + l3 * tr.uc;
                        if (tex == null || tex.GetPixelBilinear(u.x, u.y).a >= 0.5f) on[y * W + x] = true;
                    }
            }
            return on;
        }

        // background cells a closing (two 3x3 dilations, two erosions) fills
        static int ClosingGain(bool[] on, int W, int H)
        {
            bool[] Step(bool[] a, bool grow)
            {
                var o = new bool[a.Length];
                for (int y = 0; y < H; y++)
                    for (int x = 0; x < W; x++)
                    {
                        bool v = !grow;
                        for (int dy = -1; dy <= 1 && v != grow; dy++)
                            for (int dx = -1; dx <= 1; dx++)
                            {
                                int xx = x + dx, yy = y + dy;
                                bool b = xx >= 0 && yy >= 0 && xx < W && yy < H && a[yy * W + xx];
                                if (b == grow) { v = grow; break; }
                            }
                        o[y * W + x] = v;
                    }
                return o;
            }
            bool[] c = Step(Step(Step(Step(on, true), true), false), false);
            int gain = 0;
            for (int i = 0; i < on.Length; i++) if (c[i] && !on[i]) gain++;
            return gain;
        }

        // ------------------------------------------------------------------ gates

        /// <summary>What the import produced: rigged sprites, weight sums, and the state of every
        /// SpriteSkin on an instance of the generated prefab.</summary>
        public static void Verify(string path, Result r)
        {
            var sprites = AssetDatabase.LoadAllAssetsAtPath(path).OfType<Sprite>().ToArray();
            r.sprites = sprites.Length;
            foreach (Sprite s in sprites)
            {
                if (s.GetBones().Length > 0) r.rigged++;
                else r.problems.Add("layer without bones: " + s.name);
                var w = s.GetVertexAttribute<BoneWeight>(VertexAttribute.BlendWeight);
                int bad = 0;
                foreach (BoneWeight bw in w) if (Mathf.Abs(bw.weight0 + bw.weight1 + bw.weight2 + bw.weight3 - 1f) > 1e-3f) bad++;
                if (w.Length == 0 && s.GetBones().Length > 0) bad = s.GetVertexCount();
                if (bad > 0) r.problems.Add($"{s.name}: {bad} vertices whose weights do not sum to 1");
                r.badWeights += bad;
            }
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (model == null) { r.problems.Add("no generated prefab"); return; }
            var inst = (GameObject)PrefabUtility.InstantiatePrefab(model);
            try
            {
                foreach (SpriteSkin sk in inst.GetComponentsInChildren<SpriteSkin>(true))
                {
                    r.skins++;
                    SpriteSkinState st = SkinState(sk);
                    if (st == SpriteSkinState.Ready) r.skinsReady++;
                    else r.problems.Add($"SpriteSkin {sk.name}: {st}");
                }
            }
            finally { UnityEngine.Object.DestroyImmediate(inst); }
            if (r.skins == 0) r.problems.Add("the generated prefab has no SpriteSkin");
        }

        /// <summary>The package's validity ladder (internal there) from public data.</summary>
        public static SpriteSkinState SkinState(SpriteSkin sk)
        {
            var sr = sk.GetComponent<SpriteRenderer>();
            Sprite s = sr ? sr.sprite : null;
            if (s == null) return SpriteSkinState.SpriteNotFound;
            int bind = s.GetBindPoses().Length;
            if (bind == 0) return SpriteSkinState.SpriteHasNoSkinningInformation;
            if (sk.rootBone == null) return SpriteSkinState.RootTransformNotFound;
            Transform[] t = sk.boneTransforms;
            if (t == null) return SpriteSkinState.InvalidTransformArray;
            if (t.Length != bind) return SpriteSkinState.InvalidTransformArrayLength;
            if (t.Any(x => x == null)) return SpriteSkinState.TransformArrayContainsNull;
            return SpriteSkinState.Ready;
        }

        // ------------------------------------------------------------------ face states

        static string DefaultLabel(string category, IEnumerable<string> labels)
        {
            var l = labels.ToList();
            string c = Rig2DLayout.Lower(category);
            string want = c.StartsWith("mouth") ? "closed" : c.StartsWith("eye") ? "open" : null;
            return l.FirstOrDefault(x => Rig2DLayout.Lower(x) == want) ?? l[0];
        }

        static string BuildLibrary(string psb, IEnumerable<string> layerNames, Result r)
        {
            var groups = Rig2DLayout.SwapGroups(layerNames);
            if (groups.Count == 0) { r.notes.Add("no swappable states (eyes_open / eyes_closed …): no library"); return null; }
            var sprites = AssetDatabase.LoadAllAssetsAtPath(psb).OfType<Sprite>().ToDictionary(s => s.name);
            var entries = new List<SpriteLibraryBuilder.Entry>();
            foreach (var g in groups)
                foreach (var (label, layer) in g.Value)
                    if (sprites.TryGetValue(layer, out Sprite s))
                        entries.Add(new SpriteLibraryBuilder.Entry { category = g.Key, label = label, sprite = s, source = psb });
            if (entries.Count == 0) return null;
            return SpriteLibraryBuilder.Build(entries, Path.ChangeExtension(psb, null) + "_Faces", null);
        }

        static string BuildVariant(string psb, string library, RigDriver2D.View view, bool facesRight, Result r)
        {
            string path = Path.ChangeExtension(psb, null) + "_Rig.prefab";
            if (AssetDatabase.LoadAssetAtPath<GameObject>(path) != null) { r.notes.Add("variant kept as it is: " + path); return path; }
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(psb);
            var inst = (GameObject)PrefabUtility.InstantiatePrefab(model);
            try
            {
                var all = inst.GetComponentsInChildren<Transform>(true);
                var drv = inst.AddComponent<RigDriver2D>();
                drv.view = view;
                drv.facesRight = facesRight;
                var eyes = new List<SpriteResolver>();
                var mouths = new List<SpriteResolver>();
                if (library != null)
                {
                    var asset = AssetDatabase.LoadAssetAtPath<SpriteLibraryAsset>(library);
                    inst.AddComponent<SpriteLibrary>().spriteLibraryAsset = asset;
                    foreach (var g in Rig2DLayout.SwapGroups(all.Where(t => t.GetComponent<SpriteRenderer>()).Select(t => t.name)))
                    {
                        string def = DefaultLabel(g.Key, g.Value.Select(x => x.label));
                        foreach (var (label, layer) in g.Value)
                        {
                            Transform t = all.FirstOrDefault(x => x.name == layer && x.GetComponent<SpriteRenderer>());
                            if (t == null) continue;
                            if (label != def) { t.gameObject.SetActive(false); continue; }
                            t.gameObject.SetActive(true);
                            var sr = t.GetComponent<SpriteRenderer>();
                            if (sr) sr.enabled = true;
                            var skin = t.GetComponent<SpriteSkin>();
                            if (skin) skin.autoRebind = true;
                            var res = t.gameObject.AddComponent<SpriteResolver>();
                            res.SetCategoryAndLabel(g.Key, label);
                            string c = Rig2DLayout.Lower(g.Key);
                            if (c.StartsWith("eye")) eyes.Add(res);
                            else if (c.StartsWith("mouth")) mouths.Add(res);
                        }
                    }
                }
                drv.eyes = eyes.ToArray();
                drv.mouths = mouths.ToArray();
                drv.springBones = all.Where(t => t.GetComponent<SpriteRenderer>() == null && t != inst.transform && Rig2DLayout.IsSpring(t.name)).ToArray();
                PrefabUtility.SaveAsPrefabAsset(inst, path);
            }
            finally { UnityEngine.Object.DestroyImmediate(inst); }
            return path;
        }
    }
}
