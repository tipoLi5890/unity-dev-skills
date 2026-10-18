// UrpMaterialValidation.cs — run URP's own material validation from a script, and audit a folder
// for materials that Unity would rewrite the next time it validates them.
//
// Drop into an Editor folder whose assembly references Unity.RenderPipelines.Universal.Editor.
// REQUIRES com.unity.render-pipelines.universal 17.x (read Packages/manifest.json).
//
//   UrpMaterialValidation.Validate(material)          for a builder: call after setting properties
//   UrpMaterialValidation.Audit("Assets/Art")         read-only JSON: which materials would drift
//   Tools/Unity Dev/Render URP/Audit Material Validation (selected folder)
//                                                     logs "[URP-MATERIAL-AUDIT] {json}"
//
// Why: URP's ShaderGUI.ValidateMaterial rewrites keywords, blend factors, queue and passes from the
// surface properties whenever Unity next validates the material. A builder that does not run the
// same code leaves a diff behind on every rebuild, and loses settings: _EMISSION is removed unless
// globalIlluminationFlags includes AnyEmissive; a hand-made alpha blend becomes the shader-side
// premultiply (_SrcBlend One + _ALPHAPREMULTIPLY_ON) when _BlendModePreserveSpecular is 1.
//
// Lit's own ValidateMaterial also calls LitDetailGUI.SetMaterialKeywords, which is internal; this
// file cannot, so materials using detail maps report detail keywords as their own finding.
//
// A keyword the current shader does not declare is reported as removed; that is a real finding (a
// stale keyword), not noise.
//
// The audit never edits an asset: it validates an in-memory copy and compares.
using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.Rendering.Universal.ShaderGUI;
using UnityEngine;

public static class UrpMaterialValidation
{
    const string MenuPath = "Tools/Unity Dev/Render URP/Audit Material Validation (selected folder)";
    static readonly string[] Passes = { "ShadowCaster", "DepthOnly", "MOTIONVECTORS", "DepthNormals" };
    static readonly string[] Floats = { "_SrcBlend", "_DstBlend", "_SrcBlendAlpha", "_DstBlendAlpha", "_ZWrite", "_AlphaToMask" };

    /// <summary>Same keyword, blend, queue and pass settings URP's inspector would write. Returns false
    /// for a shader this file does not know (Shader Graph, custom), which it leaves untouched.</summary>
    public static bool Validate(Material m)
    {
        if (m == null || m.shader == null) return false;
        switch (m.shader.name)
        {
            case "Universal Render Pipeline/Lit":
                BaseShaderGUI.SetMaterialKeywords(m, LitGUI.SetMaterialKeywords);
                return true;
            case "Universal Render Pipeline/Simple Lit":
                BaseShaderGUI.SetMaterialKeywords(m, SimpleLitGUI.SetMaterialKeywords);
                return true;
            case "Universal Render Pipeline/Unlit":
                BaseShaderGUI.SetMaterialKeywords(m);
                return true;
            default:
                return false;
        }
    }

    [MenuItem(MenuPath)]
    static void Menu()
    {
        string folder = "Assets";
        var sel = Selection.activeObject;
        if (sel != null)
        {
            string p = AssetDatabase.GetAssetPath(sel);
            if (AssetDatabase.IsValidFolder(p)) folder = p;
        }
        Debug.Log("[URP-MATERIAL-AUDIT] " + Audit(folder));
    }

    /// <summary>Read-only. JSON: {"folder","checked","skipped","drift":[{"path","changes":[…]}]}.</summary>
    public static string Audit(string folder)
    {
        var guids = AssetDatabase.FindAssets("t:Material", new[] { folder });
        int checkedCount = 0, skipped = 0;
        var drift = new List<(string path, List<string> changes)>();
        foreach (var g in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(g);
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null) continue;
            var copy = new Material(m);
            try
            {
                if (!Validate(copy)) { skipped++; continue; }
                checkedCount++;
                var changes = Compare(m, copy);
                if (m.IsKeywordEnabled("_DETAIL_MULX2") || m.IsKeywordEnabled("_DETAIL_SCALED"))
                    changes.Add("uses detail keywords: validate in the inspector once, this file cannot");
                if (changes.Count > 0) drift.Add((path, changes));
            }
            finally { Object.DestroyImmediate(copy); }
        }
        var sb = new StringBuilder();
        sb.Append("{\"folder\":").Append(Q(folder)).Append(",\"checked\":").Append(checkedCount)
          .Append(",\"skipped\":").Append(skipped).Append(",\"drift\":[");
        for (int i = 0; i < drift.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"path\":").Append(Q(drift[i].path)).Append(",\"changes\":[")
              .Append(string.Join(",", drift[i].changes.Select(Q))).Append("]}");
        }
        return sb.Append("]}").ToString();
    }

    static List<string> Compare(Material before, Material after)
    {
        var c = new List<string>();
        var kb = new HashSet<string>(before.shaderKeywords);
        var ka = new HashSet<string>(after.shaderKeywords);
        foreach (var k in ka.Except(kb).OrderBy(x => x)) c.Add("keyword +" + k);
        foreach (var k in kb.Except(ka).OrderBy(x => x)) c.Add("keyword -" + k);
        foreach (var f in Floats)
            if (before.HasProperty(f) && !Mathf.Approximately(before.GetFloat(f), after.GetFloat(f)))
                c.Add(f + " " + before.GetFloat(f) + " -> " + after.GetFloat(f));
        if (before.renderQueue != after.renderQueue) c.Add("renderQueue " + before.renderQueue + " -> " + after.renderQueue);
        foreach (var p in Passes)
            if (before.GetShaderPassEnabled(p) != after.GetShaderPassEnabled(p))
                c.Add("pass " + p + " " + (after.GetShaderPassEnabled(p) ? "enabled" : "disabled"));
        if (before.globalIlluminationFlags != after.globalIlluminationFlags)
            c.Add("globalIlluminationFlags " + before.globalIlluminationFlags + " -> " + after.globalIlluminationFlags);
        if (before.GetTag("RenderType", false) != after.GetTag("RenderType", false))
            c.Add("RenderType " + before.GetTag("RenderType", false) + " -> " + after.GetTag("RenderType", false));
        return c;
    }

    static string Q(string s) => "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
}
