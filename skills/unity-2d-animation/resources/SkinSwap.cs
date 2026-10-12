// SkinSwap.cs — changes what a Sprite Library character wears at runtime: the whole library
// (a skin), every label of one category taken from another library (a piece of equipment),
// one label's sprite, or which label a part shows.
//
// Drop into a Runtime folder (an asmdef references Unity.2D.Animation.Runtime) and add it to
// the object that holds the SpriteLibrary — the character root.
//
// REQUIRES com.unity.2d.animation (13.x on Unity 6000.3, 14.x on 6000.4 — the calls used
// here are the same in both).
//
//   var swap = runner.GetComponent<SkinSwap>();
//   swap.SetLibrary(nightCourierLibrary);            // every part changes
//   swap.Equip(depotGearLibrary, "helmet");          // the helmet category only
//   swap.Unequip("helmet");                          // back to the library's own helmet
//   swap.Show("visor", "down");                      // a part shows another label
//
// Three things in the package this file exists to get right:
//   · SpriteLibrary.AddOverride(asset, category) changes the data and refreshes nothing.
//     Only the Sprite overload refreshes. Equip() calls RefreshSpriteResolvers() itself.
//   · RefreshSpriteResolvers() skips inactive children; they resolve when they are enabled.
//   · A swapped-in sprite that carries bones needs a SpriteSkin with Auto Rebind on, and
//     bones that match under its Root Bone. CheckBindings() says which parts do not,
//     instead of leaving a part frozen in its bind pose.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.U2D;
using UnityEngine.U2D.Animation;

[DisallowMultipleComponent]
[RequireComponent(typeof(SpriteLibrary))]
public sealed class SkinSwap : MonoBehaviour
{
    [Tooltip("After every swap, warn about parts whose SpriteSkin cannot follow the new sprite.")]
    [SerializeField] bool checkBindings = true;

    SpriteLibrary _library;
    SpriteResolver[] _resolvers;
    readonly List<string> _equipped = new List<string>();

    public SpriteLibrary Library => _library != null ? _library : _library = GetComponent<SpriteLibrary>();

    /// <summary>Categories currently overridden through Equip or Override.</summary>
    public IReadOnlyList<string> Equipped => _equipped;

    void Awake() => Rescan();

    /// <summary>Call after adding or removing parts at runtime.</summary>
    public void Rescan() => _resolvers = GetComponentsInChildren<SpriteResolver>(true);

    /// <summary>Swaps the whole library. Overrides made with Equip stay on top of it.</summary>
    public void SetLibrary(SpriteLibraryAsset asset)
    {
        if (asset == null) { Debug.LogWarning("[SKIN-SWAP] SetLibrary(null) ignored", this); return; }
        Library.spriteLibraryAsset = asset;      // the setter refreshes the resolvers
        AfterSwap();
    }

    /// <summary>Overrides every label of one category with the same-named labels of another library.</summary>
    public bool Equip(SpriteLibraryAsset source, string category)
    {
        if (source == null || !HasCategory(source, category))
        {
            Debug.LogWarning("[SKIN-SWAP] no category '" + category + "' in " + (source != null ? source.name : "null"), this);
            return false;
        }
        Library.AddOverride(source, category);
        Library.RefreshSpriteResolvers();        // this overload does not refresh on its own
        Remember(category);
        AfterSwap();
        return true;
    }

    /// <summary>Overrides one label with one sprite.</summary>
    public void Override(Sprite sprite, string category, string label)
    {
        Library.AddOverride(sprite, category, label);
        Remember(category);
        AfterSwap();
    }

    /// <summary>Removes the overrides of one category; the library's own sprites show again.</summary>
    public void Unequip(string category)
    {
        Library.RemoveOverride(category);
        _equipped.Remove(category);
        AfterSwap();
    }

    public void UnequipAll()
    {
        for (int i = _equipped.Count - 1; i >= 0; i--) Library.RemoveOverride(_equipped[i]);
        _equipped.Clear();
        AfterSwap();
    }

    /// <summary>
    /// Points every part that currently shows <paramref name="category"/> at another label.
    /// Returns how many parts changed. A clip that keys the resolver writes over this on the
    /// next frame it plays.
    /// </summary>
    public int Show(string category, string label)
    {
        if (_resolvers == null) Rescan();
        int changed = 0;
        foreach (SpriteResolver resolver in _resolvers)
        {
            if (resolver == null || resolver.GetCategory() != category) continue;
            if (resolver.SetCategoryAndLabel(category, label)) changed++;
            else Debug.LogWarning("[SKIN-SWAP] '" + resolver.name + "' has no " + category + "/" + label, resolver);
        }
        if (changed > 0) AfterSwap();
        return changed;
    }

    /// <summary>
    /// Parts whose SpriteSkin cannot deform the sprite they now show. Empty means every
    /// rigged part is bound. Auto Rebind runs when the skin next deforms, not when the sprite
    /// changes, so for those parts the answer is only final one frame after the swap — pass
    /// false to leave them out when asking in the same frame.
    /// </summary>
    public List<string> CheckBindings(bool includeAutoRebind = true)
    {
        if (_resolvers == null) Rescan();
        var broken = new List<string>();
        foreach (SpriteResolver resolver in _resolvers)
        {
            if (resolver == null || !resolver.TryGetComponent(out SpriteRenderer renderer)) continue;
            Sprite sprite = renderer.sprite;
            if (sprite == null) continue;
            int bones = sprite.GetBindPoses().Length;
            if (bones == 0) continue;                                  // a rigid part: nothing to bind

            if (!resolver.TryGetComponent(out SpriteSkin skin))
            {
                broken.Add(resolver.name + ": sprite '" + sprite.name + "' has bones and the part has no SpriteSkin");
                continue;
            }
            if (skin.autoRebind && !includeAutoRebind) continue;
            Transform[] transforms = skin.boneTransforms;
            bool bound = skin.rootBone != null && transforms != null && transforms.Length == bones;
            if (bound)
                foreach (Transform t in transforms)
                    if (t == null) { bound = false; break; }
            if (!bound)
                broken.Add(resolver.name + ": '" + sprite.name + "' needs " + bones + " bones, SpriteSkin has " +
                           (transforms != null ? transforms.Length : 0) +
                           (skin.autoRebind ? " (Auto Rebind found no match under the Root Bone)" : " (Auto Rebind is off)"));
        }
        return broken;
    }

    void Remember(string category)
    {
        if (!_equipped.Contains(category)) _equipped.Add(category);
    }

    void AfterSwap()
    {
        if (!checkBindings) return;
        // Same frame: only what is already certain. A failed Auto Rebind is logged by the
        // package itself ("Rebind failed for …") when the skin next deforms.
        foreach (string line in CheckBindings(false)) Debug.LogWarning("[SKIN-SWAP] " + line, this);
    }

    static bool HasCategory(SpriteLibraryAsset asset, string category)
    {
        foreach (string name in asset.GetCategoryNames())
            if (name == category) return true;
        return false;
    }
}
