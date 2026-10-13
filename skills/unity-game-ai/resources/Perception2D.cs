// Perception2D — the line-of-sight cast for a 2D game: one Physics2D.Linecast against the cover
// layers, triggers ignored.
//
// Drop into the Runtime assembly that holds Perception.cs and add it to the sentry beside
// SentryBrain, which finds it through ILineOfSight and stops using the 3D cast. Set the
// sentry's plane to XY.
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
//
// It is a separate file on purpose: Perception.cs and SentryBrain.cs name no 2D type, so a
// 3D project with the 2D physics module removed compiles them, and a 2D project adds this one.
using UnityEngine;

[DisallowMultipleComponent]
public sealed class Perception2D : MonoBehaviour, ILineOfSight
{
    [Tooltip("Layers that hide a target: shelving, walls, closed gates. Never the sentry's or the runner's own layer.")]
    public LayerMask blockers = 1;

    readonly RaycastHit2D[] _hit = new RaycastHit2D[1];

    public bool Clear(Vector3 from, Vector3 to)
    {
        // A filter, not the plain overload: Physics2D.queriesHitTriggers is on by default, and a
        // pickup's trigger on a cover layer would otherwise hide the runner standing behind it.
        var filter = new ContactFilter2D();
        filter.SetLayerMask(blockers);
        filter.useTriggers = false;
        return Physics2D.Linecast(from, to, filter, _hit) == 0;
    }
}
