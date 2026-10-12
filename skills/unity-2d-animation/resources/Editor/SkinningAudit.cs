// SkinningAudit.cs — what a skeletal 2D character costs and where its bindings are broken,
// as one JSON object. Per rigged sprite: bones, vertices, triangles, the most bones any
// vertex is weighted to, vertices with no weight, weights that point past the bone list.
// Per SpriteSkin: its state, missing bone transforms, Auto Rebind. Per character: the
// summed mesh the rig deforms every frame.
//
// Drop into an Editor folder (an Editor asmdef references Unity.2D.Animation.Runtime).
// Menu: Tools/Unity Dev/2D Animation/Audit Skinning. From `unity command eval`:
//
//   return SkinningAudit.Json("Assets/Art/Runner");
//
// REQUIRES com.unity.2d.animation (13.x on Unity 6000.3, 14.x on 6000.4 — the calls used
// here are the same in both).
//
// Reads only. Sprites come from the imported assets under the root, so the numbers are what
// the last import produced: re-import after a Skinning Editor Apply before trusting them.
// SpriteSkin components come from prefabs under the root, the prefab each rigged PSB
// generates, and every loaded scene.
//
// Sprite issues:
//   no-weights           bones are assigned and the mesh carries no weight channel
//   unweighted-vertices  vertices no bone moves — they stay behind when the part bends
//   bad-bone-index       a weight names a bone the sprite does not have
// Skin states are SpriteSkinState names (Ready, TransformArrayContainsNull, …) recomputed
// from public data; issues add:
//   missing-bones        one or more entries of boneTransforms are null
//   swap-without-rebind  a SpriteResolver swaps this renderer's sprite and Auto Rebind is off
using System.Collections.Generic;
using System.Text;
using Unity.Collections;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.U2D;
using UnityEngine.U2D.Animation;

public static class SkinningAudit
{
    const float WeightEpsilon = 0.0001f;

    sealed class SpriteRow
    {
        public int bones, vertices, triangles, maxInfluences, unweighted, badIndex;
        public bool hasWeights;
    }

    [MenuItem("Tools/Unity Dev/2D Animation/Audit Skinning")]
    static void Menu()
    {
        string root = "Assets";
        foreach (Object o in Selection.objects)
        {
            string path = AssetDatabase.GetAssetPath(o);
            if (!string.IsNullOrEmpty(path) && AssetDatabase.IsValidFolder(path)) { root = path; break; }
        }
        Debug.Log("[SKINNING-AUDIT] " + Json(root));
    }

    /// <summary>The audit as one JSON object on one line.</summary>
    public static string Json(string root = "Assets")
    {
        if (!AssetDatabase.IsValidFolder(root)) return "{\"error\":\"not a project folder\",\"root\":" + Str(root) + "}";

        var sb = new StringBuilder(4096);
        int problems = 0;
        var rows = new Dictionary<Sprite, SpriteRow>();
        var riggedAssets = new List<string>();

        // 1 · sprites
        var paths = new List<string>();
        var seen = new HashSet<string>();
        foreach (string guid in AssetDatabase.FindAssets("t:Sprite", new[] { root }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (seen.Add(path)) paths.Add(path);
        }
        paths.Sort(System.StringComparer.Ordinal);

        sb.Append("{\"root\":").Append(Str(root)).Append(",\"sprites\":[");
        bool first = true;
        int spritesScanned = 0;
        var leftBehind = new List<string>();
        foreach (string path in paths)
        {
            var rigged = new List<Sprite>();
            var plain = new List<string>();
            foreach (Object sub in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                if (!(sub is Sprite sprite)) continue;
                spritesScanned++;
                if (sprite.GetBones().Length > 0) rigged.Add(sprite);
                else plain.Add(sprite.name);
            }
            if (rigged.Count == 0) continue;
            riggedAssets.Add(path);

            // A boneless part inside a rigged asset gets no SpriteSkin and does not follow
            // the skeleton unless something parents it to a bone.
            foreach (string name in plain) leftBehind.Add(path + ":" + name);

            rigged.Sort((a, b) => string.CompareOrdinal(a.name, b.name));
            foreach (Sprite sprite in rigged)
            {
                SpriteRow row = Measure(sprite);
                rows[sprite] = row;

                var issues = new List<string>();
                if (!row.hasWeights) issues.Add("no-weights");
                if (row.unweighted > 0) issues.Add("unweighted-vertices");
                if (row.badIndex > 0) issues.Add("bad-bone-index");
                problems += issues.Count;

                sb.Append(first ? "" : ",");
                first = false;
                sb.Append("{\"asset\":").Append(Str(path))
                  .Append(",\"sprite\":").Append(Str(sprite.name))
                  .Append(",\"bones\":").Append(row.bones)
                  .Append(",\"vertices\":").Append(row.vertices)
                  .Append(",\"triangles\":").Append(row.triangles)
                  .Append(",\"maxInfluences\":").Append(row.maxInfluences)
                  .Append(",\"unweightedVertices\":").Append(row.unweighted)
                  .Append(",\"badBoneIndices\":").Append(row.badIndex)
                  .Append(",\"issues\":");
                Strings(sb, issues);
                sb.Append('}');
            }
        }
        sb.Append("],\"bonelessSpritesInRiggedAssets\":");
        Strings(sb, leftBehind);

        // 2 · SpriteSkin components, grouped by the character that owns them
        sb.Append(",\"skins\":[");
        var characters = new StringBuilder();
        first = true;
        bool firstCharacter = true;
        int skinCount = 0;

        var prefabPaths = new List<string>(riggedAssets);
        foreach (string guid in AssetDatabase.FindAssets("t:Prefab", new[] { root }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (!prefabPaths.Contains(path)) prefabPaths.Add(path);
        }
        foreach (string path in prefabPaths)
        {
            GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (prefab == null) continue;
            Character(prefab, path, rows, sb, characters, ref first, ref firstCharacter, ref skinCount, ref problems);
        }
        for (int i = 0; i < SceneManager.sceneCount; i++)
        {
            Scene scene = SceneManager.GetSceneAt(i);
            if (!scene.isLoaded) continue;
            foreach (GameObject sceneRoot in scene.GetRootGameObjects())
                Character(sceneRoot, "scene:" + scene.name, rows, sb, characters,
                          ref first, ref firstCharacter, ref skinCount, ref problems);
        }

        sb.Append("],\"characters\":[").Append(characters)
          .Append("],\"spritesScanned\":").Append(spritesScanned)
          .Append(",\"riggedSprites\":").Append(rows.Count)
          .Append(",\"skinsScanned\":").Append(skinCount)
          .Append(",\"problems\":").Append(problems)
          .Append('}');
        return sb.ToString();
    }

    static SpriteRow Measure(Sprite sprite)
    {
        var row = new SpriteRow
        {
            bones = sprite.GetBones().Length,
            vertices = sprite.GetVertexCount(),
            triangles = sprite.GetIndices().Length / 3,
            hasWeights = sprite.HasVertexAttribute(VertexAttribute.BlendWeight),
        };
        if (!row.hasWeights) return row;

        NativeSlice<BoneWeight> weights = sprite.GetVertexAttribute<BoneWeight>(VertexAttribute.BlendWeight);
        for (int i = 0; i < weights.Length; i++)
        {
            BoneWeight w = weights[i];
            int used = 0;
            bool bad = false;
            Count(w.weight0, w.boneIndex0, row.bones, ref used, ref bad);
            Count(w.weight1, w.boneIndex1, row.bones, ref used, ref bad);
            Count(w.weight2, w.boneIndex2, row.bones, ref used, ref bad);
            Count(w.weight3, w.boneIndex3, row.bones, ref used, ref bad);
            if (used == 0) row.unweighted++;
            if (bad) row.badIndex++;
            if (used > row.maxInfluences) row.maxInfluences = used;
        }
        return row;
    }

    static void Count(float weight, int boneIndex, int bones, ref int used, ref bool bad)
    {
        if (weight <= WeightEpsilon) return;
        used++;
        if (boneIndex < 0 || boneIndex >= bones) bad = true;
    }

    static void Character(GameObject root, string where, Dictionary<Sprite, SpriteRow> rows, StringBuilder sb,
                          StringBuilder characters, ref bool first, ref bool firstCharacter,
                          ref int skinCount, ref int problems)
    {
        SpriteSkin[] skins = root.GetComponentsInChildren<SpriteSkin>(true);
        if (skins.Length == 0) return;

        int vertices = 0, triangles = 0, notReady = 0;
        var bones = new HashSet<Transform>();
        foreach (SpriteSkin skin in skins)
        {
            skinCount++;
            Sprite sprite = skin.TryGetComponent(out SpriteRenderer renderer) ? renderer.sprite : null;
            Transform[] transforms = skin.boneTransforms;
            int expected = sprite != null ? sprite.GetBindPoses().Length : 0;
            int missing = 0;
            if (transforms != null)
                foreach (Transform t in transforms)
                {
                    if (t == null) missing++;
                    else bones.Add(t);
                }

            SpriteSkinState state = State(sprite, expected, skin.rootBone, transforms, missing);
            var issues = new List<string>();
            if (missing > 0) issues.Add("missing-bones");
            if (!skin.autoRebind && skin.TryGetComponent(out SpriteResolver _)) issues.Add("swap-without-rebind");
            if (state != SpriteSkinState.Ready) notReady++;
            problems += issues.Count + (state != SpriteSkinState.Ready ? 1 : 0);

            if (sprite != null)
            {
                if (!rows.TryGetValue(sprite, out SpriteRow row)) row = Measure(sprite);
                vertices += row.vertices;
                triangles += row.triangles;
            }

            sb.Append(first ? "" : ",");
            first = false;
            sb.Append("{\"in\":").Append(Str(where))
              .Append(",\"path\":").Append(Str(HierarchyPath(skin.transform)))
              .Append(",\"sprite\":").Append(sprite != null ? Str(sprite.name) : "null")
              .Append(",\"state\":").Append(Str(state.ToString()))
              .Append(",\"boneTransforms\":").Append(transforms != null ? transforms.Length : 0)
              .Append(",\"expected\":").Append(expected)
              .Append(",\"missing\":").Append(missing)
              .Append(",\"rootBone\":").Append(skin.rootBone != null ? Str(skin.rootBone.name) : "null")
              .Append(",\"autoRebind\":").Append(skin.autoRebind ? "true" : "false")
              .Append(",\"alwaysUpdate\":").Append(skin.alwaysUpdate ? "true" : "false")
              .Append(",\"issues\":");
            Strings(sb, issues);
            sb.Append('}');
        }

        characters.Append(firstCharacter ? "" : ",");
        firstCharacter = false;
        characters.Append("{\"in\":").Append(Str(where))
                  .Append(",\"root\":").Append(Str(root.name))
                  .Append(",\"skins\":").Append(skins.Length)
                  .Append(",\"notReady\":").Append(notReady)
                  .Append(",\"boneTransforms\":").Append(bones.Count)
                  .Append(",\"vertices\":").Append(vertices)
                  .Append(",\"triangles\":").Append(triangles)
                  .Append('}');
    }

    // The package's own validation is internal; this is the same ladder in the same order,
    // minus the weight check, which the sprite rows report as bad-bone-index.
    static SpriteSkinState State(Sprite sprite, int bindPoses, Transform rootBone, Transform[] transforms, int missing)
    {
        if (sprite == null) return SpriteSkinState.SpriteNotFound;
        if (bindPoses == 0) return SpriteSkinState.SpriteHasNoSkinningInformation;
        if (rootBone == null) return SpriteSkinState.RootTransformNotFound;
        if (transforms == null) return SpriteSkinState.InvalidTransformArray;
        if (transforms.Length != bindPoses) return SpriteSkinState.InvalidTransformArrayLength;
        if (missing > 0) return SpriteSkinState.TransformArrayContainsNull;
        return SpriteSkinState.Ready;
    }

    static string HierarchyPath(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (Transform p = t.parent; p != null; p = p.parent) sb.Insert(0, p.name + "/");
        return sb.ToString();
    }

    static void Strings(StringBuilder sb, List<string> values)
    {
        sb.Append('[');
        for (int i = 0; i < values.Count; i++) sb.Append(i > 0 ? "," : "").Append(Str(values[i]));
        sb.Append(']');
    }

    static string Str(string s)
    {
        if (s == null) return "null";
        var sb = new StringBuilder(s.Length + 2);
        sb.Append('"');
        foreach (char c in s)
        {
            if (c == '"' || c == '\\') sb.Append('\\').Append(c);
            else if (c == '\n') sb.Append("\\n");
            else if (c == '\r') sb.Append("\\r");
            else if (c == '\t') sb.Append("\\t");
            else if (c < ' ') sb.Append("\\u").Append(((int)c).ToString("x4"));
            else sb.Append(c);
        }
        sb.Append('"');
        return sb.ToString();
    }
}
