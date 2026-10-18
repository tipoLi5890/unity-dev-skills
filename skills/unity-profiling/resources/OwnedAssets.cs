using System.Collections.Generic;
using UnityEngine;

namespace UnityDev.Perf
{
    /// <summary>
    /// OwnedAssets — a material, mesh or texture made at runtime dies with the object that made it.
    ///
    /// Unity never frees a runtime-created Material, Mesh or Texture2D when the GameObject using it
    /// is destroyed: it is an asset with no owner, and it stays in memory until
    /// Resources.UnloadUnusedAssets or the end of the session. A screen rebuilt every match leaks
    /// one set per match. Register each one with the component that made it:
    ///
    ///   var mat  = OwnedAssets.Own(this, new Material(baseMaterial) { name = "BallOutline" });
    ///   var mesh = OwnedAssets.Own(this, new Mesh { name = "CourtLines" });
    ///
    /// Own adds an OwnedAssets component to that GameObject on first use; its OnDestroy destroys
    /// everything registered. Name every runtime asset: the soak test (templates/AssetLeakSoakTest.cs)
    /// lists what grew by name, and an unnamed material is a blank line in that list.
    ///
    /// Not for: shared assets loaded from disk (destroying one breaks every user), Renderer.material
    /// (that getter makes a copy you should register too, or avoid with sharedMaterial / a property
    /// block), and TextMeshPro's fontMaterial getter and outlineWidth / outlineColor setters (each makes a
    /// per-label copy of the font material; share one cached material instead,
    /// unity-ui-ugui → reference/text-and-image-traps.md).
    /// </summary>
    public sealed class OwnedAssets : MonoBehaviour
    {
        readonly List<Object> items = new List<Object>();

        public static T Own<T>(Component owner, T asset) where T : Object
        {
            if (asset == null || owner == null) return asset;
            var bag = owner.GetComponent<OwnedAssets>();
            if (bag == null) bag = owner.gameObject.AddComponent<OwnedAssets>();
            bag.items.Add(asset);
            return asset;
        }

        public int Count => items.Count;

        void OnDestroy()
        {
            foreach (var o in items)
                if (o != null) Destroy(o);
            items.Clear();
        }
    }
}
