using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

/// <summary>
/// JourneyInvariants2D — the 2D sibling of JourneyAsserts.NeverInside: the player was never
/// inside solid 2D geometry at any sample of a recorded journey.
///
/// Drop it into the Runtime assembly that holds GameProbe.cs and JourneyRecorder.cs.
/// REQUIRES com.unity.modules.physics2d (the built-in 2D physics module; read
/// Packages/manifest.json — a project created from a 3D template may have removed it).
///
/// It is a separate file on purpose. JourneyRecorder.cs names only 3D physics, so a project
/// with the 2D physics module disabled still compiles the whole 3D harness; a 2D project adds
/// this one file. Nothing else in the harness refers to it.
///
/// Like the 3D rule it returns violations rather than asserting, so it stays in a Runtime
/// assembly with no test-framework reference:
///
///   var inside = JourneyInvariants2D.NeverInside2D(journey.Captured, LayerMask.GetMask("Rooftop"), 0.2f);
///   Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
/// </summary>
public static class JourneyInvariants2D
{
    static readonly List<Collider2D> _hits = new List<Collider2D>(4);

    /// <summary>
    /// The player was never inside solid 2D geometry. Each sample's pos is tested on the x/y
    /// plane (z is dropped) with a circle of the given radius against the layers in mask.
    ///
    /// Triggers are ignored, whatever Physics2D.queriesHitTriggers says: a pickup or a sentry's
    /// vision cone is a place the runner is allowed to be. Composite, tilemap and edge
    /// colliders count like any other solid.
    ///
    /// Evaluated against the colliders present when this runs, so it is an invariant about
    /// STATIC geometry — rooftops, depot shelving, yard walls. For a moving platform or a
    /// pushed pickup, sample an overlap flag per frame into custom{} and use JourneyAsserts.Never.
    ///
    /// Choose the radius smaller than the body: a runner standing on a rooftop is in contact
    /// with it, and a circle as wide as its collider reports every grounded sample. Half the
    /// collider's smallest half-extent is a safe start. Leave the player's own layer out of mask.
    /// </summary>
    public static List<JourneyViolation> NeverInside2D(IList<ProbeSnapshot> samples, LayerMask mask, float radius)
    {
        var filter = new ContactFilter2D();
        filter.SetLayerMask(mask);
        filter.useTriggers = false;

        var bad = new List<JourneyViolation>();
        for (int i = 0; i < samples.Count; i++)
        {
            ProbeSnapshot s = samples[i];
            if (!s.hasPlayer) continue;
            Vector2 point = s.pos;
            _hits.Clear();
            if (Physics2D.OverlapCircle(point, radius, filter, _hits) == 0) continue;
            bad.Add(new JourneyViolation
            {
                n = s.n, frame = s.frame, t = s.t, rule = "never-inside-2d",
                detail = "pos " + point.ToString("F2") + " overlaps '" + _hits[0].name +
                         "' on layers " + mask.value +
                         " at radius " + radius.ToString("F2", CultureInfo.InvariantCulture),
            });
        }
        return bad;
    }
}
