// CameraRigBuilder.cs — three menu commands that build a camera rig on the open scene:
// a 2D follow rig with a room confiner, a third-person orbit rig, and a fixed rig.
//
// Drop into an Editor folder (an Editor asmdef that references Unity.Cinemachine).
//
// REQUIRES com.unity.cinemachine 3.x (written against 3.1.7). On 2.x nothing here compiles:
// the component names differ — reference/version-and-names.md. The 2D rig also needs the
// built-in 2D physics module, the third-person rig the built-in 3D physics module.
//
//   Tools/Unity Dev/Camera/Build 2D Follow Rig       select the runner, and optionally the room collider
//   Tools/Unity Dev/Camera/Build Third-Person Rig    select the runner
//   Tools/Unity Dev/Camera/Build Fixed Rig           frames from where the Main Camera is now
//
// Every command reports what it would create and waits for confirmation. From an eval or a
// test fixture, call Plan…() first, show the text, then call Build…() — the Build methods
// do not ask.
//
// Every value is assigned explicitly. A component added from code outside the Editor does
// not run Reset(), and several Cinemachine defaults live only there: the deoccluder's
// obstacle avoidance is off, the orbit radius is 10 and not 5.
using System.Text;
using Unity.Cinemachine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class CameraRigBuilder
{
    const string MenuRoot = "Tools/Unity Dev/Camera/";
    const int FollowPriority = 10;

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Build 2D Follow Rig")]
    static void Menu2DFollow()
    {
        Transform target = Selection.activeTransform;
        Collider2D room = SelectedRoom(target);
        if (!Confirm("2D follow rig", Plan2DFollow(target, room))) return;
        Selection.activeGameObject = Build2DFollow(target, room).gameObject;
    }

    [MenuItem(MenuRoot + "Build Third-Person Rig")]
    static void MenuThirdPerson()
    {
        Transform target = Selection.activeTransform;
        if (!Confirm("Third-person rig", PlanThirdPerson(target))) return;
        Selection.activeGameObject = BuildThirdPerson(target).gameObject;
    }

    [MenuItem(MenuRoot + "Build Fixed Rig")]
    static void MenuFixed()
    {
        Transform target = Selection.activeTransform;
        if (!Confirm("Fixed rig", PlanFixed(target))) return;
        Selection.activeGameObject = BuildFixed(target).gameObject;
    }

    static bool Confirm(string title, string plan)
    {
        Debug.Log("[CAMERA-RIG] plan\n" + plan);
        return EditorUtility.DisplayDialog("Build " + title + "?", plan, "Create", "Cancel");
    }

    // The room is the selected Box/Polygon/Composite collider that is not the runner's own.
    static Collider2D SelectedRoom(Transform target)
    {
        foreach (GameObject go in Selection.gameObjects)
        {
            if (target != null && go.transform == target) continue;
            if (go.TryGetComponent(out Collider2D c) &&
                (c is BoxCollider2D || c is PolygonCollider2D || c is CompositeCollider2D))
                return c;
        }
        return null;
    }

    // ------------------------------------------------------------------ plans

    public static string Plan2DFollow(Transform target, Collider2D room)
    {
        var sb = Header();
        sb.AppendLine("Main Camera: set to orthographic, keep its current size.");
        sb.AppendLine("Create 'CM Follow 2D' at z -10 with:");
        sb.AppendLine("  CinemachineCamera            priority " + FollowPriority + ", tracking " + Name(target));
        sb.AppendLine("  CinemachinePositionComposer  dead zone 0.10 x 0.15, damping 0.5 / 0.3, look-ahead 0.25 s");
        sb.AppendLine(room != null
            ? "  CinemachineConfiner2D        bounding shape '" + room.name + "', damping 0.5"
            : "  (no confiner — select the room's Box, Polygon or Composite collider with the runner to add one)");
        if (target == null) sb.AppendLine("No runner selected: the camera tracks nothing until Target is assigned.");
        return sb.ToString();
    }

    public static string PlanThirdPerson(Transform target)
    {
        var sb = Header();
        sb.AppendLine("Main Camera: set to perspective.");
        sb.AppendLine("Create 'CM Third Person' with:");
        sb.AppendLine("  CinemachineCamera               priority " + FollowPriority + ", tracking " + Name(target));
        sb.AppendLine("  CinemachineOrbitalFollow        sphere, radius 5, pivot 1.5 above the runner");
        sb.AppendLine("  CinemachineRotationComposer     damping 0.5 / 0.5");
        sb.AppendLine("  CinemachineInputAxisController  Look Orbit X / Y — assign the project's own Look action");
        sb.AppendLine("  CinemachineDeoccluder           Default layer, radius 0.2, pull camera forward");
        if (target == null) sb.AppendLine("No runner selected: the camera tracks nothing until Target is assigned.");
        return sb.ToString();
    }

    public static string PlanFixed(Transform target)
    {
        var sb = Header();
        sb.AppendLine("Create 'CM Fixed' at the Main Camera's current position and rotation with:");
        sb.AppendLine("  CinemachineCamera            priority 0, lens copied from the Main Camera");
        sb.AppendLine(target != null
            ? "  CinemachineRotationComposer  turns to keep " + target.name + " framed; the position never moves"
            : "  (nothing else — select the runner first to make it turn and track)");
        sb.AppendLine("It is live while it is the highest-priority enabled camera.");
        return sb.ToString();
    }

    static StringBuilder Header()
    {
        var sb = new StringBuilder();
        Camera cam = FindOutputCamera();
        sb.AppendLine("Scene: " + EditorSceneManager.GetActiveScene().name);
        if (cam == null) sb.AppendLine("Create 'Main Camera' (tag MainCamera) with a CinemachineBrain.");
        else if (!cam.TryGetComponent(out CinemachineBrain _))
            sb.AppendLine("Add a CinemachineBrain to '" + cam.name + "' (Smart Update, blends in Late Update).");
        else sb.AppendLine("Keep the CinemachineBrain on '" + cam.name + "'.");
        return sb;
    }

    static string Name(Transform t) => t != null ? "'" + t.name + "'" : "nothing";

    // ------------------------------------------------------------------ builders

    public static CinemachineCamera Build2DFollow(Transform target, Collider2D room)
    {
        Camera cam = EnsureBrain();
        Undo.RecordObject(cam, "Build 2D Follow Rig");
        cam.orthographic = true;

        Vector3 at = target != null ? target.position : Vector3.zero;
        CinemachineCamera vcam = NewCamera("CM Follow 2D", new Vector3(at.x, at.y, at.z - 10f),
                                           Quaternion.identity, target, FollowPriority, cam);

        var composer = Undo.AddComponent<CinemachinePositionComposer>(vcam.gameObject);
        composer.CameraDistance = 10f;
        composer.TargetOffset = Vector3.zero;
        composer.Damping = new Vector3(0.5f, 0.3f, 0f);
        composer.CenterOnActivate = true;
        ScreenComposerSettings composition = ScreenComposerSettings.Default;
        composition.ScreenPosition = Vector2.zero;                    // 0 is the centre in 3.x
        composition.DeadZone.Enabled = true;
        composition.DeadZone.Size = new Vector2(0.10f, 0.15f);
        composition.HardLimits.Enabled = true;
        composition.HardLimits.Size = new Vector2(0.6f, 0.7f);
        composer.Composition = composition;
        composer.Lookahead = new LookaheadSettings { Enabled = true, Time = 0.25f, Smoothing = 8f, IgnoreY = true };

        if (room != null)
        {
            var confiner = Undo.AddComponent<CinemachineConfiner2D>(vcam.gameObject);
            confiner.BoundingShape2D = room;
            confiner.Damping = 0.5f;
            confiner.SlowingDistance = 0f;
            confiner.InvalidateBoundingShapeCache();
        }
        return Finish(vcam);
    }

    public static CinemachineCamera BuildThirdPerson(Transform target)
    {
        Camera cam = EnsureBrain();
        Undo.RecordObject(cam, "Build Third-Person Rig");
        cam.orthographic = false;

        Vector3 at = target != null ? target.position : Vector3.zero;
        Quaternion facing = target != null ? Quaternion.Euler(0f, target.eulerAngles.y, 0f) : Quaternion.identity;
        CinemachineCamera vcam = NewCamera("CM Third Person", at + facing * new Vector3(0f, 2.5f, -5f),
                                           facing, target, FollowPriority, cam);

        var pivot = new Vector3(0f, 1.5f, 0f);
        var orbit = Undo.AddComponent<CinemachineOrbitalFollow>(vcam.gameObject);
        orbit.OrbitStyle = CinemachineOrbitalFollow.OrbitStyles.Sphere;
        orbit.Radius = 5f;
        orbit.TargetOffset = pivot;

        var aim = Undo.AddComponent<CinemachineRotationComposer>(vcam.gameObject);
        aim.TargetOffset = pivot;
        aim.Damping = new Vector2(0.5f, 0.5f);
        aim.Composition = ScreenComposerSettings.Default;

        // Added after the orbit so it finds the orbit's axes and creates a controller for each.
        Undo.AddComponent<CinemachineInputAxisController>(vcam.gameObject);

        var deoccluder = Undo.AddComponent<CinemachineDeoccluder>(vcam.gameObject);
        deoccluder.CollideAgainst = 1;                                // the Default layer
        deoccluder.MinimumDistanceFromTarget = 0.3f;
        // The runner's own collider is the first thing between the camera and the runner.
        deoccluder.IgnoreTag = target != null && !target.CompareTag("Untagged") ? target.tag : string.Empty;
        CinemachineDeoccluder.ObstacleAvoidance avoid = deoccluder.AvoidObstacles;
        avoid.Enabled = true;
        avoid.CameraRadius = 0.2f;
        avoid.Strategy = CinemachineDeoccluder.ObstacleAvoidance.ResolutionStrategy.PullCameraForward;
        avoid.MaximumEffort = 4;
        avoid.MinimumOcclusionTime = 0.1f;
        avoid.SmoothingTime = 0.2f;
        avoid.Damping = 0.4f;
        avoid.DampingWhenOccluded = 0.2f;
        deoccluder.AvoidObstacles = avoid;
        return Finish(vcam);
    }

    public static CinemachineCamera BuildFixed(Transform target)
    {
        Camera cam = EnsureBrain();
        CinemachineCamera vcam = NewCamera("CM Fixed", cam.transform.position, cam.transform.rotation,
                                           target, 0, cam);
        if (target != null)
        {
            var aim = Undo.AddComponent<CinemachineRotationComposer>(vcam.gameObject);
            aim.TargetOffset = Vector3.zero;
            aim.Damping = new Vector2(0.5f, 0.5f);
            aim.Composition = ScreenComposerSettings.Default;
        }
        return Finish(vcam);
    }

    // ------------------------------------------------------------------ parts

    static Camera FindOutputCamera()
    {
        Camera cam = Camera.main;
        return cam != null ? cam : Object.FindAnyObjectByType<Camera>();
    }

    static Camera EnsureBrain()
    {
        Camera cam = FindOutputCamera();
        if (cam == null)
        {
            var go = new GameObject("Main Camera") { tag = "MainCamera" };
            Undo.RegisterCreatedObjectUndo(go, "Create Main Camera");
            cam = Undo.AddComponent<Camera>(go);
            Undo.AddComponent<AudioListener>(go);
            go.transform.position = new Vector3(0f, 1f, -10f);
        }
        if (!cam.TryGetComponent(out CinemachineBrain brain))
            brain = Undo.AddComponent<CinemachineBrain>(cam.gameObject);
        Undo.RecordObject(brain, "Configure CinemachineBrain");
        brain.UpdateMethod = CinemachineBrain.UpdateMethods.SmartUpdate;
        brain.BlendUpdateMethod = CinemachineBrain.BrainUpdateMethods.LateUpdate;
        return cam;
    }

    static CinemachineCamera NewCamera(string name, Vector3 position, Quaternion rotation,
                                       Transform target, int priority, Camera output)
    {
        var go = new GameObject(name);
        Undo.RegisterCreatedObjectUndo(go, "Create " + name);
        go.transform.SetPositionAndRotation(position, rotation);

        var vcam = Undo.AddComponent<CinemachineCamera>(go);
        vcam.Target.TrackingTarget = target;
        vcam.Priority = priority;

        // A new CinemachineCamera carries its own lens (orthographic size 10, field of view 40)
        // and writes it to the Camera the moment it goes live. Copy the framing the scene
        // already has, so building a rig does not also change the zoom.
        LensSettings lens = vcam.Lens;
        lens.OrthographicSize = output.orthographicSize;
        lens.FieldOfView = output.fieldOfView;
        lens.NearClipPlane = output.nearClipPlane;
        lens.FarClipPlane = output.farClipPlane;
        vcam.Lens = lens;
        return vcam;
    }

    static CinemachineCamera Finish(CinemachineCamera vcam)
    {
        EditorUtility.SetDirty(vcam);
        EditorSceneManager.MarkSceneDirty(vcam.gameObject.scene);
        Debug.Log("[CAMERA-RIG] created " + vcam.name + " priority=" + vcam.Priority.Value +
                  " target=" + (vcam.Target.TrackingTarget != null ? vcam.Target.TrackingTarget.name : "none"));
        return vcam;
    }
}
