// Physics2DAudit.cs — a read-only audit of the 2D physics set-up in the open scene, printed
// as one JSON object. It changes nothing: no component, no setting, no asset.
//
// Drop into an Editor folder.
//
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json). Tilemap
// colliders are recognised by type name, so the file also compiles without the Tilemap module.
//
//   Tools/Unity Dev/Physics 2D/Audit Open Scene      logs "[PHYSICS2D-AUDIT] {json}"
//   Physics2DAudit.Audit()                           returns the same JSON, for an eval or a test
//
// Each finding is a candidate, not a verdict: the audit reads the scene as it is saved, and
// cannot see which objects a script moves at runtime. `check` names the rule:
//
//   moved-without-body        a collider with no Rigidbody2D under an Animator or a project script
//   layers-contact-nothing    a collider whose effective contact mask is empty, or whose layer is not simulated
//   composite-child-unmerged  a solid collider on a composite's body with compositeOperation None
//   trigger-without-body      a trigger with no Rigidbody2D: it reports only against a moving body
//   tilemap-without-composite a TilemapCollider2D that is not merged into a CompositeCollider2D
//   composite-on-dynamic-body a composite built from a tilemap on a Dynamic body: the level falls
//   collider-without-shapes   an enabled collider that produced no physics shapes
//   body-not-simulated        a Rigidbody2D with simulated off
//   effector-unused           an effector with no collider using it, or usedByEffector with no effector
using System.Collections.Generic;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class Physics2DAudit
{
    const string MenuPath = "Tools/Unity Dev/Physics 2D/Audit Open Scene";

    struct Finding { public string check, path, detail; }

    [MenuItem(MenuPath)]
    static void Menu() => Debug.Log("[PHYSICS2D-AUDIT] " + Audit());

    public static string Audit()
    {
        Scene scene = SceneManager.GetActiveScene();
        var colliders = new List<Collider2D>();
        var bodies = new List<Rigidbody2D>();
        var effectors = new List<Effector2D>();
        // Walk the roots so that inactive objects are read too: a disabled pooled sentry is
        // part of the set-up.
        foreach (GameObject root in scene.GetRootGameObjects())
        {
            colliders.AddRange(root.GetComponentsInChildren<Collider2D>(true));
            bodies.AddRange(root.GetComponentsInChildren<Rigidbody2D>(true));
            effectors.AddRange(root.GetComponentsInChildren<Effector2D>(true));
        }

        var findings = new List<Finding>();
        int simulationLayers = Physics2D.simulationLayers.value;
        var attached = new List<Collider2D>();

        foreach (Collider2D c in colliders)
        {
            Rigidbody2D body = c.attachedRigidbody;
            bool isTilemap = c.GetType().Name == "TilemapCollider2D";
            bool merged = c.compositeOperation != Collider2D.CompositeOperation.None;

            if (body == null && !c.gameObject.isStatic)
            {
                string mover = MoverAbove(c.transform);
                if (mover != null)
                    Add(findings, "moved-without-body", c,
                        "no Rigidbody2D, and " + mover + " may move it; a moving collider needs a Kinematic body");
            }

            if (c.isTrigger && body == null)
                Add(findings, "trigger-without-body", c,
                    "reports only when the other collider has a Dynamic or Kinematic Rigidbody2D");

            if ((simulationLayers & (1 << c.gameObject.layer)) == 0)
                Add(findings, "layers-contact-nothing", c,
                    "layer '" + LayerMask.LayerToName(c.gameObject.layer) + "' is not in Physics2D.simulationLayers");
            else if (c.contactMask.value == 0)
                Add(findings, "layers-contact-nothing", c,
                    "layer '" + LayerMask.LayerToName(c.gameObject.layer) +
                    "' contacts no layer after the matrix and the include/exclude overrides");

            if (isTilemap && (!merged || c.composite == null))
                Add(findings, "tilemap-without-composite", c,
                    "one shape per tile: seams snag a sliding body; set compositeOperation Merge beside a CompositeCollider2D");

            // A collider with no shapes is silent in the inspector. Merged children have none of
            // their own by design, and an inactive object has none until it is enabled.
            if (c.enabled && c.gameObject.activeInHierarchy && !merged &&
                (c.errorState != ColliderErrorState2D.None || c.shapeCount == 0))
                Add(findings, "collider-without-shapes", c,
                    "errorState " + c.errorState + ", shapeCount " + c.shapeCount);

            if (c.usedByEffector && c.GetComponent<Effector2D>() == null)
                Add(findings, "effector-unused", c, "usedByEffector is set and no effector is on this GameObject");

            if (c is CompositeCollider2D composite && body != null)
            {
                attached.Clear();
                body.GetAttachedColliders(attached, true);
                bool fromTilemap = false;
                foreach (Collider2D child in attached)
                {
                    if (child == composite) continue;
                    if (child.GetType().Name == "TilemapCollider2D") fromTilemap = true;
                    if (child.compositeCapable && !child.isTrigger &&
                        child.compositeOperation == Collider2D.CompositeOperation.None)
                        Add(findings, "composite-child-unmerged", child,
                            "shares a body with CompositeCollider2D '" + composite.name +
                            "' and keeps its own shapes; set compositeOperation Merge unless that is intended");
                }
                if (fromTilemap && body.bodyType == RigidbodyType2D.Dynamic)
                    Add(findings, "composite-on-dynamic-body", composite,
                        "the Rigidbody2D added with the composite is Dynamic; set bodyType Static");
            }
        }

        foreach (Rigidbody2D b in bodies)
            if (!b.simulated)
                Add(findings, "body-not-simulated", b,
                    "simulated is off: the body, its colliders and its joints are outside the world");

        foreach (Effector2D e in effectors)
        {
            bool used = false;
            foreach (Collider2D c in e.GetComponents<Collider2D>())
                if (c.usedByEffector) { used = true; break; }
            if (!used)
                Add(findings, "effector-unused", e,
                    e.GetType().Name + " has no collider on this GameObject with usedByEffector set");
        }

        return ToJson(scene, colliders.Count, bodies.Count, effectors.Count, findings);
    }

    // The nearest thing above a body-less collider that could move it: an Animator, or a
    // MonoBehaviour that is not Unity's own. Null when nothing suggests movement.
    static string MoverAbove(Transform t)
    {
        for (; t != null; t = t.parent)
        {
            foreach (Behaviour script in t.GetComponents<Behaviour>())
            {
                if (script == null) continue;                      // a missing script
                // By name, so the file does not depend on the Animation module.
                if (script.GetType().Name == "Animator") return "an Animator on '" + t.name + "'";
                if (!(script is MonoBehaviour)) continue;
                string ns = script.GetType().Namespace ?? "";
                if (ns.StartsWith("UnityEngine") || ns.StartsWith("Unity.") || ns.StartsWith("TMPro")) continue;
                return script.GetType().Name + " on '" + t.name + "'";
            }
        }
        return null;
    }

    static void Add(List<Finding> findings, string check, Component on, string detail) =>
        findings.Add(new Finding { check = check, path = PathOf(on.transform), detail = detail });

    static string PathOf(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (t = t.parent; t != null; t = t.parent) sb.Insert(0, t.name + "/");
        return sb.ToString();
    }

    static string ToJson(Scene scene, int colliders, int bodies, int effectors, List<Finding> findings)
    {
        var counts = new SortedDictionary<string, int>();
        foreach (Finding f in findings)
        {
            counts.TryGetValue(f.check, out int n);
            counts[f.check] = n + 1;
        }

        var sb = new StringBuilder(256 + findings.Count * 160);
        sb.Append("{\"scene\":").Append(Quote(scene.path));
        sb.Append(",\"simulationMode\":").Append(Quote(Physics2D.simulationMode.ToString()));
        sb.Append(",\"colliders\":").Append(colliders);
        sb.Append(",\"bodies\":").Append(bodies);
        sb.Append(",\"effectors\":").Append(effectors);
        sb.Append(",\"ok\":").Append(findings.Count == 0 ? "true" : "false");
        sb.Append(",\"counts\":{");
        bool first = true;
        foreach (KeyValuePair<string, int> kv in counts)
        {
            if (!first) sb.Append(',');
            first = false;
            sb.Append(Quote(kv.Key)).Append(':').Append(kv.Value);
        }
        sb.Append("},\"findings\":[");
        for (int i = 0; i < findings.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"check\":").Append(Quote(findings[i].check));
            sb.Append(",\"path\":").Append(Quote(findings[i].path));
            sb.Append(",\"detail\":").Append(Quote(findings[i].detail)).Append('}');
        }
        return sb.Append("]}").ToString();
    }

    static string Quote(string s)
    {
        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char ch in s)
        {
            if (ch == '"' || ch == '\\') sb.Append('\\').Append(ch);
            else if (ch == '\n') sb.Append("\\n");
            else if (ch == '\r') sb.Append("\\r");
            else if (ch == '\t') sb.Append("\\t");
            else if (ch < ' ') sb.Append("\\u").Append(((int)ch).ToString("x4"));
            else sb.Append(ch);
        }
        return sb.Append('"').ToString();
    }
}
