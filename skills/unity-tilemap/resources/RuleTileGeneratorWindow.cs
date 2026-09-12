// Interactive front end for RuleTileFromSprites: select a sliced tileset in the
// Project window, look at what the analysis found, then write the rule tile.
//
// REQUIRES com.unity.2d.tilemap.extras (see RuleTileFromSprites.cs). Drop both files
// plus SpriteGridAnalysis.cs into an Editor folder. If that folder is covered by an
// .asmdef, the package's runtime assembly has to be in its references or none of the
// rule tile types resolve — and the error reads as a missing package rather than a
// missing reference.
//
// Survey before Generate is the whole point of the window. The analysis is a heuristic
// over pixels: reading the pattern list costs seconds and catches a tolerance that was
// too loose before it becomes 40 rules and an asset in the diff.
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;   // RuleTile — see the namespace note in RuleTileFromSprites.cs

public class RuleTileGeneratorWindow : EditorWindow
{
    float m_MatchThreshold = 0.75f;
    float m_ColorTolerance = 0.04f;
    bool m_FilterToKnownPatterns = true;
    Vector2 m_Scroll;
    string m_Report = "";

    [MenuItem("Tools/Unity Dev/Rule Tile from Sprites")]
    static void ShowWindow()
    {
        GetWindow<RuleTileGeneratorWindow>("Rule Tile");
    }

    void OnGUI()
    {
        EditorGUILayout.LabelField("Select a sliced tileset texture in the Project window.",
                                   EditorStyles.wordWrappedMiniLabel);
        EditorGUILayout.Space();

        m_MatchThreshold = EditorGUILayout.Slider("Match threshold", m_MatchThreshold, 0.5f, 0.9f);
        m_ColorTolerance = EditorGUILayout.Slider("Colour tolerance", m_ColorTolerance, 0.005f, 0.2f);
        m_FilterToKnownPatterns = EditorGUILayout.Toggle("Known patterns only", m_FilterToKnownPatterns);

        EditorGUILayout.Space();
        using (new EditorGUILayout.HorizontalScope())
        {
            if (GUILayout.Button("Survey")) Survey();
            if (GUILayout.Button("Generate")) Generate();
        }

        if (string.IsNullOrEmpty(m_Report)) return;
        EditorGUILayout.Space();
        m_Scroll = EditorGUILayout.BeginScrollView(m_Scroll);
        EditorGUILayout.TextArea(m_Report, GUILayout.ExpandHeight(true));
        EditorGUILayout.EndScrollView();
    }

    Sprite[] SelectedSprites(out string assetPath)
    {
        assetPath = null;
        var texture = Selection.activeObject as Texture2D;
        if (texture == null)
        {
            m_Report = "Select a Texture2D asset first.";
            return null;
        }

        assetPath = AssetDatabase.GetAssetPath(texture);
        var sprites = AssetDatabase.LoadAllAssetsAtPath(assetPath).OfType<Sprite>().ToArray();
        if (sprites.Length == 0)
        {
            // No sprite sub-assets means the sheet was never sliced, or it was left in
            // Multiple mode with no rects. Slicing is unity-2d-sprites, not this window.
            m_Report = $"{assetPath}\nNo Sprite sub-assets — the sheet is not sliced.";
            return null;
        }

        if (!texture.isReadable)
        {
            m_Report = $"{assetPath}\nRead/Write is off on this texture; the analysis cannot " +
                       "sample it. Enable it for the run and turn it off again afterwards.";
            return null;
        }

        return sprites;
    }

    void Survey()
    {
        var sprites = SelectedSprites(out string assetPath);
        if (sprites == null) return;

        var found = RuleTileFromSprites.Survey(sprites, m_MatchThreshold, m_ColorTolerance);
        var lines = found.Select(f =>
            $"{(RuleTileFromSprites.IsKnownPattern(f.pattern) ? "  " : "? ")}{f.pattern}   {f.sprite.name}");

        m_Report = $"{assetPath}\n{found.Count} sprite(s) analysed. '?' marks a configuration " +
                   $"that is not in the known set.\n\n{string.Join("\n", lines)}";
    }

    void Generate()
    {
        var sprites = SelectedSprites(out string assetPath);
        if (sprites == null) return;

        var rules = RuleTileFromSprites.Build(
            sprites, m_MatchThreshold, m_ColorTolerance, m_FilterToKnownPatterns);
        if (rules.Count == 0)
        {
            m_Report = $"{assetPath}\nNo usable rules. Survey first — the thresholds are " +
                       "probably rejecting or accepting everything.";
            return;
        }

        string savePath = System.IO.Path.ChangeExtension(assetPath, null) + "_RuleTile.asset";
        if (System.IO.File.Exists(savePath) &&
            !EditorUtility.DisplayDialog("Rule Tile", $"Overwrite {savePath}?", "Overwrite", "Cancel"))
            return;

        var tile = ScriptableObject.CreateInstance<RuleTile>();
        RuleTileFromSprites.Apply(tile, rules);

        AssetDatabase.CreateAsset(tile, savePath);
        AssetDatabase.SaveAssets();
        Selection.activeObject = tile;

        string defaultSprite = tile.m_DefaultSprite != null ? tile.m_DefaultSprite.name : "none";
        m_Report = $"{savePath}\n{rules.Count} rule(s), most constrained first. " +
                   $"Default sprite: {defaultSprite}.";
    }
}
