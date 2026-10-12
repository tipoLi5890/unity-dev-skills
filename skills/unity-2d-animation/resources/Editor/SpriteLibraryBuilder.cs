// SpriteLibraryBuilder.cs — builds a Sprite Library Asset (.spriteLib) from a folder laid out
// as Category/Label.png, or from sprites named category_label, instead of dragging every
// sprite into the Sprite Library Editor by hand.
//
// Drop into an Editor folder (an Editor asmdef references Unity.2D.Animation.Runtime and
// Unity.2D.Animation.Editor).
//
// REQUIRES com.unity.2d.animation (13.x on Unity 6000.3, 14.x on 6000.4 — the calls used
// here are the same in both).
//
//   Tools/Unity Dev/2D Animation/Build Sprite Library From Folder
//       select the root folder:   Runner/Helmet/courier.png  →  category Helmet, label courier
//       a sheet with several sprites contributes one label per sprite, named after the sprite
//   Tools/Unity Dev/2D Animation/Build Sprite Library From Sprites
//       select sprites, textures or an imported PSB:   helmet_courier  →  category helmet,
//       label courier (split at the FIRST underscore; case is kept as written)
//
// Select a .spriteLib together with the folder or the sprites and the result becomes a
// variant of it: the selected library is its Main Library, labels with the same name
// override, everything else is inherited.
//
// Both commands report what they would write and wait for confirmation. From an eval or a
// test fixture: Collect…() → Plan() → show the text → Build(). Build does not ask.
//
//   var problems = new System.Collections.Generic.List<string>();
//   var entries  = SpriteLibraryBuilder.CollectFromFolder("Assets/Art/Runner/Parts", problems);
//   return SpriteLibraryBuilder.Plan(entries, problems, "Assets/Art/Runner/Runner.spriteLib", null);
//
// A resolver's key is a hash of "category_label". Rebuilding over an existing library keeps
// the asset's GUID, so components keep their reference — but a label the new set no longer
// contains is a key nothing answers: clips and resolvers that use it stop changing the
// sprite, silently. Plan() lists those.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.U2D.Animation;
using UnityEngine;
using UnityEngine.U2D.Animation;

public static class SpriteLibraryBuilder
{
    const string MenuRoot = "Tools/Unity Dev/2D Animation/";

    public sealed class Entry
    {
        public string category;
        public string label;
        public Sprite sprite;
        public string source;      // asset path, for the report
    }

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Build Sprite Library From Folder")]
    static void MenuFromFolder()
    {
        string folder = SelectedFolder();
        if (folder == null)
        {
            EditorUtility.DisplayDialog("Build Sprite Library", "Select the root folder in the Project window: " +
                "its sub-folders become categories and the sprites inside them become labels.", "OK");
            return;
        }
        var problems = new List<string>();
        Run(CollectFromFolder(folder, problems), problems, Path.GetFileName(folder));
    }

    [MenuItem(MenuRoot + "Build Sprite Library From Sprites")]
    static void MenuFromSprites()
    {
        var problems = new List<string>();
        Run(CollectFromSprites(SelectedSprites(), '_', problems), problems, "Sprites");
    }

    static void Run(List<Entry> entries, List<string> problems, string defaultName)
    {
        if (entries.Count == 0)
        {
            EditorUtility.DisplayDialog("Build Sprite Library", "Nothing to build.\n\n" + string.Join("\n", problems), "OK");
            return;
        }
        string output = EditorUtility.SaveFilePanelInProject("Save Sprite Library", defaultName,
            SpriteLibrarySourceAssetFactory.extension.TrimStart('.'), "Where to write the library");
        if (string.IsNullOrEmpty(output)) return;

        string main = SelectedMainLibrary(output);
        string plan = Plan(entries, problems, output, main);
        Debug.Log("[SPRITE-LIBRARY] plan\n" + plan);
        if (!EditorUtility.DisplayDialog("Build Sprite Library?", Shorten(plan), "Write", "Cancel")) return;

        string written = Build(entries, output, main);
        Selection.activeObject = AssetDatabase.LoadAssetAtPath<SpriteLibraryAsset>(written);
        Debug.Log("[SPRITE-LIBRARY] wrote " + written);
    }

    // A dialog cannot scroll; the full plan is in the Console.
    static string Shorten(string plan)
    {
        const int Max = 1800;
        return plan.Length <= Max ? plan : plan.Substring(0, Max) + "\n… (full plan in the Console)";
    }

    static string SelectedFolder()
    {
        foreach (UnityEngine.Object o in Selection.objects)
        {
            string path = AssetDatabase.GetAssetPath(o);
            if (!string.IsNullOrEmpty(path) && AssetDatabase.IsValidFolder(path)) return path;
        }
        return null;
    }

    static string SelectedMainLibrary(string outputPath)
    {
        foreach (UnityEngine.Object o in Selection.objects)
        {
            if (!(o is SpriteLibraryAsset)) continue;
            string path = AssetDatabase.GetAssetPath(o);
            if (!string.IsNullOrEmpty(path) && path != outputPath) return path;
        }
        return null;
    }

    static List<Sprite> SelectedSprites()
    {
        var sprites = new List<Sprite>();
        var seenPaths = new HashSet<string>();
        foreach (UnityEngine.Object o in Selection.objects)
        {
            if (o is Sprite s) { sprites.Add(s); continue; }
            if (o is SpriteLibraryAsset) continue;
            string path = AssetDatabase.GetAssetPath(o);
            if (string.IsNullOrEmpty(path) || AssetDatabase.IsValidFolder(path) || !seenPaths.Add(path)) continue;
            AddSpritesAt(path, sprites);
        }
        return sprites;
    }

    static void AddSpritesAt(string assetPath, List<Sprite> into)
    {
        foreach (UnityEngine.Object sub in AssetDatabase.LoadAllAssetsAtPath(assetPath))
            if (sub is Sprite s && !into.Contains(s)) into.Add(s);
    }

    // ------------------------------------------------------------------ collect

    /// <summary>root/Category/…/Label.png. The first folder under the root is the category.</summary>
    public static List<Entry> CollectFromFolder(string rootFolder, List<string> problems)
    {
        var entries = new List<Entry>();
        if (string.IsNullOrEmpty(rootFolder) || !AssetDatabase.IsValidFolder(rootFolder))
        {
            problems.Add("Not a project folder: " + rootFolder);
            return entries;
        }
        rootFolder = rootFolder.TrimEnd('/');

        var paths = new List<string>();
        var seen = new HashSet<string>();
        foreach (string guid in AssetDatabase.FindAssets("t:Sprite", new[] { rootFolder }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (seen.Add(path)) paths.Add(path);
        }
        paths.Sort(StringComparer.Ordinal);

        foreach (string path in paths)
        {
            string relative = path.Substring(rootFolder.Length + 1);
            int slash = relative.IndexOf('/');
            if (slash < 0)
            {
                problems.Add("Skipped " + path + " — it sits in the root, so it has no category folder.");
                continue;
            }
            string category = relative.Substring(0, slash);

            var sprites = new List<Sprite>();
            AddSpritesAt(path, sprites);
            sprites.Sort((a, b) => string.CompareOrdinal(a.name, b.name));
            string fileLabel = Path.GetFileNameWithoutExtension(path);
            foreach (Sprite sprite in sprites)
            {
                // One sprite in the file: the file is the label. A sheet: each sprite is one.
                string label = sprites.Count == 1 ? fileLabel : sprite.name;
                Add(entries, category, label, sprite, path, problems);
            }
        }
        return entries;
    }

    /// <summary>Sprites named category{separator}label, split at the first separator.</summary>
    public static List<Entry> CollectFromSprites(IEnumerable<Sprite> sprites, char separator, List<string> problems)
    {
        var entries = new List<Entry>();
        var sorted = new List<Sprite>();
        if (sprites != null)
            foreach (Sprite s in sprites)
                if (s != null) sorted.Add(s);
        sorted.Sort((a, b) => string.CompareOrdinal(a.name, b.name));

        foreach (Sprite sprite in sorted)
        {
            int cut = sprite.name.IndexOf(separator);
            if (cut <= 0 || cut == sprite.name.Length - 1)
            {
                problems.Add("Skipped sprite '" + sprite.name + "' — no '" + separator + "' between a category and a label.");
                continue;
            }
            Add(entries, sprite.name.Substring(0, cut), sprite.name.Substring(cut + 1), sprite,
                AssetDatabase.GetAssetPath(sprite), problems);
        }
        return entries;
    }

    static void Add(List<Entry> entries, string category, string label, Sprite sprite, string source, List<string> problems)
    {
        category = category.Trim();
        label = label.Trim();
        if (category.Length == 0 || label.Length == 0)
        {
            problems.Add("Skipped '" + sprite.name + "' in " + source + " — empty category or label.");
            return;
        }
        foreach (Entry e in entries)
        {
            if (e.category != category || e.label != label) continue;
            problems.Add("Duplicate " + category + "/" + label + " — kept " + e.source + ", skipped " + source + ".");
            return;
        }
        entries.Add(new Entry { category = category, label = label, sprite = sprite, source = source });
    }

    // ------------------------------------------------------------------ plan

    public static string Plan(List<Entry> entries, List<string> problems, string outputPath, string mainLibraryPath)
    {
        outputPath = WithExtension(outputPath);
        var sb = new StringBuilder();
        SpriteLibraryAsset existing = AssetDatabase.LoadAssetAtPath<SpriteLibraryAsset>(outputPath);
        sb.AppendLine((existing != null ? "Overwrite " : "Create ") + outputPath);

        SpriteLibraryAsset main = null;
        if (!string.IsNullOrEmpty(mainLibraryPath))
        {
            main = AssetDatabase.LoadAssetAtPath<SpriteLibraryAsset>(mainLibraryPath);
            sb.AppendLine(main != null
                ? "Variant of " + mainLibraryPath + " — its categories and labels are inherited"
                : "Main library NOT FOUND at " + mainLibraryPath + " — Build will throw");
        }

        SortedDictionary<string, List<Entry>> byCategory = Group(entries);
        sb.AppendLine(byCategory.Count + " categories, " + entries.Count + " labels:");
        foreach (KeyValuePair<string, List<Entry>> c in byCategory)
        {
            sb.Append("  ").Append(c.Key).Append(" (").Append(c.Value.Count).Append("): ");
            for (int i = 0; i < c.Value.Count; i++)
            {
                Entry e = c.Value[i];
                bool overrides = main != null && main.GetSprite(e.category, e.label) != null;
                sb.Append(i > 0 ? ", " : "").Append(e.label).Append(overrides ? "*" : "");
            }
            sb.AppendLine();
        }
        if (main != null) sb.AppendLine("  * overrides a label of the main library");

        if (existing != null)
        {
            // Everything the rebuilt asset will still answer for: the new labels and, for a
            // variant, the ones it inherits.
            var kept = new HashSet<string>();
            foreach (Entry e in entries) kept.Add(e.category + "/" + e.label);
            if (main != null) AddKeys(main, kept);

            var gone = new List<string>();
            foreach (string category in existing.GetCategoryNames())
                foreach (string label in existing.GetCategoryLabelNames(category))
                    if (!kept.Contains(category + "/" + label)) gone.Add(category + "/" + label);
            if (gone.Count > 0)
            {
                gone.Sort(StringComparer.Ordinal);
                sb.AppendLine("Labels that DISAPPEAR (clips and resolvers keyed on them stop changing the sprite):");
                foreach (string g in gone) sb.AppendLine("  " + g);
            }
        }

        if (problems != null && problems.Count > 0)
        {
            sb.AppendLine("Problems:");
            foreach (string p in problems) sb.AppendLine("  " + p);
        }
        return sb.ToString();
    }

    static void AddKeys(SpriteLibraryAsset asset, HashSet<string> into)
    {
        foreach (string category in asset.GetCategoryNames())
            foreach (string label in asset.GetCategoryLabelNames(category))
                into.Add(category + "/" + label);
    }

    // ------------------------------------------------------------------ build

    /// <summary>Writes the library and returns its project-relative path. Does not ask.</summary>
    public static string Build(List<Entry> entries, string outputPath, string mainLibraryPath)
    {
        if (entries == null || entries.Count == 0)
            throw new InvalidOperationException("No entries to write.");

        var categories = new List<ISpriteLibraryCategory>();
        foreach (KeyValuePair<string, List<Entry>> c in Group(entries))
        {
            var labels = new List<SpriteLibraryLabel>();
            foreach (Entry e in c.Value) labels.Add(new SpriteLibraryLabel(e.label, e.sprite));
            categories.Add(new SpriteLibraryCategory(c.Key, labels));
        }

        string written = SpriteLibrarySourceAssetFactory.Create(
            WithExtension(outputPath), categories,
            string.IsNullOrEmpty(mainLibraryPath) ? null : mainLibraryPath);

        // The factory writes the file; the importer that turns it into a SpriteLibraryAsset
        // only runs on import.
        AssetDatabase.ImportAsset(written, ImportAssetOptions.ForceUpdate);
        return written;
    }

    static string WithExtension(string path) =>
        string.IsNullOrEmpty(path) ? path : Path.ChangeExtension(path, SpriteLibrarySourceAssetFactory.extension);

    static SortedDictionary<string, List<Entry>> Group(List<Entry> entries)
    {
        var byCategory = new SortedDictionary<string, List<Entry>>(StringComparer.Ordinal);
        foreach (Entry e in entries)
        {
            if (!byCategory.TryGetValue(e.category, out List<Entry> list))
                byCategory[e.category] = list = new List<Entry>();
            list.Add(e);
        }
        foreach (List<Entry> list in byCategory.Values)
            list.Sort((a, b) => string.CompareOrdinal(a.label, b.label));
        return byCategory;
    }
}
