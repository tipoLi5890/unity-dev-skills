// CreateRunActions — build the courier-run .inputactions asset from script.
//
// REQUIRES com.unity.inputsystem.
// Drop into an Editor folder (an Editor assembly that references Unity.InputSystem).
// Menu: Tools/Unity Dev/Input/Create Run Actions…
//
// One "Run" map — Move, Aim, Launch, Interact, Pause — and three control schemes. The on-screen
// stick and buttons are a gamepad as far as an action can tell, so the Touch scheme shares the
// gamepad bindings (groups "Gamepad;Touch") and lists the gamepad as an optional device.
//
// Writing an .inputactions file adds an asset to the project. The menu item reports the path and
// the contents first and writes only on confirmation. From `unity command eval`, call Plan() and
// show the result, wait for a yes, then call Write():
//
//   return CreateRunActions.Plan("Assets/Input/RunActions.inputactions");
//   return CreateRunActions.Write("Assets/Input/RunActions.inputactions", false);
//
// The asset is an importer asset: it is written as JSON text and imported, never CreateAsset.
// Every run generates new ids, and saved rebinds are keyed by binding id — so regenerate a
// shipped asset only with overwrite, and only knowing that it resets every player's rebinds.
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.InputSystem;

public static class CreateRunActions
{
    public const string DefaultPath = "Assets/Input/RunActions.inputactions";

    const string KeyboardMouse = "Keyboard&Mouse";
    const string Gamepad = "Gamepad";
    const string Touch = "Touch";
    const string PadAndTouch = Gamepad + ";" + Touch;

    [MenuItem("Tools/Unity Dev/Input/Create Run Actions…")]
    static void Menu()
    {
        string path = DefaultPath;
        bool exists = File.Exists(path);
        string plan = Plan(path);
        if (!EditorUtility.DisplayDialog("Create Run Actions", plan,
                                         exists ? "Overwrite" : "Create", "Cancel"))
            return;
        Debug.Log("[INPUT] " + Write(path, exists));
    }

    /// <summary>What Write would create, without creating anything.</summary>
    public static string Plan(string path)
    {
        InputActionAsset asset = Build(Path.GetFileNameWithoutExtension(path));
        var sb = new StringBuilder();
        sb.Append(File.Exists(path) ? "OVERWRITE " : "create ").AppendLine(path);
        if (File.Exists(path))
            sb.AppendLine("  new binding ids: rebinds saved against the old file stop applying");
        Describe(asset, sb);
        Object.DestroyImmediate(asset);
        return sb.ToString();
    }

    /// <summary>Write the asset, import it, and read it back. Refuses an existing file unless told to overwrite.</summary>
    public static string Write(string path, bool overwrite)
    {
        if (!path.EndsWith(".inputactions"))
            return "REFUSED " + path + " — the importer only picks up the .inputactions extension";
        if (File.Exists(path) && !overwrite)
            return "REFUSED " + path + " exists — pass overwrite: true after confirming";

        InputActionAsset asset = Build(Path.GetFileNameWithoutExtension(path));
        string json = asset.ToJson();
        Object.DestroyImmediate(asset);

        string dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        File.WriteAllText(path, json);
        AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);

        // The file existing proves the write; the imported object proves the importer took it.
        var imported = AssetDatabase.LoadAssetAtPath<InputActionAsset>(path);
        if (imported == null)
            return "WROTE " + path + " but the importer produced no InputActionAsset — read the Console";
        var sb = new StringBuilder();
        sb.Append("wrote ").AppendLine(path);
        Describe(imported, sb);
        return sb.ToString();
    }

    /// <summary>The asset in memory. The caller destroys it.</summary>
    public static InputActionAsset Build(string assetName)
    {
        var asset = ScriptableObject.CreateInstance<InputActionAsset>();
        asset.name = assetName;

        // The map must not share the asset's name: with "Generate C# Class" ticked the importer
        // reports an error for that. The generated struct for this map is RunActions, so an
        // asset of that name also needs its own "C# Class Name" on the importer.
        InputActionMap run = asset.AddActionMap("Run");

        InputAction move = run.AddAction("Move", InputActionType.Value, expectedControlLayout: "Vector2");
        move.AddCompositeBinding("2DVector")
            .With("up", "<Keyboard>/w", KeyboardMouse)
            .With("down", "<Keyboard>/s", KeyboardMouse)
            .With("left", "<Keyboard>/a", KeyboardMouse)
            .With("right", "<Keyboard>/d", KeyboardMouse);
        move.AddCompositeBinding("2DVector")
            .With("up", "<Keyboard>/upArrow", KeyboardMouse)
            .With("down", "<Keyboard>/downArrow", KeyboardMouse)
            .With("left", "<Keyboard>/leftArrow", KeyboardMouse)
            .With("right", "<Keyboard>/rightArrow", KeyboardMouse);
        // No StickDeadzone processor here: the gamepad's stick controls already carry one, and a
        // second on the binding applies the dead zone twice.
        move.AddBinding("<Gamepad>/leftStick", groups: PadAndTouch);

        // PassThrough, because it mixes a pointer position (pixels) with a stick (-1..1); a Value
        // action would resolve the conflict by magnitude and the pointer would always win.
        InputAction aim = run.AddAction("Aim", InputActionType.PassThrough, expectedControlLayout: "Vector2");
        aim.AddBinding("<Mouse>/position", groups: KeyboardMouse);
        aim.AddBinding("<Gamepad>/rightStick", groups: PadAndTouch);

        InputAction launch = run.AddAction("Launch", InputActionType.Button, expectedControlLayout: "Button");
        launch.AddBinding("<Keyboard>/space", groups: KeyboardMouse);
        launch.AddBinding("<Gamepad>/buttonSouth", groups: PadAndTouch);

        InputAction interact = run.AddAction("Interact", InputActionType.Button, expectedControlLayout: "Button");
        interact.AddBinding("<Keyboard>/e", groups: KeyboardMouse);
        interact.AddBinding("<Gamepad>/buttonWest", groups: PadAndTouch);

        InputAction pause = run.AddAction("Pause", InputActionType.Button, expectedControlLayout: "Button");
        pause.AddBinding("<Keyboard>/escape", groups: KeyboardMouse);
        pause.AddBinding("<Gamepad>/start", groups: PadAndTouch);

        asset.AddControlScheme(KeyboardMouse).WithBindingGroup(KeyboardMouse)
            .WithRequiredDevice("<Keyboard>").WithRequiredDevice("<Mouse>");
        asset.AddControlScheme(Gamepad).WithBindingGroup(Gamepad)
            .WithRequiredDevice("<Gamepad>");
        asset.AddControlScheme(Touch).WithBindingGroup(Touch)
            .WithRequiredDevice("<Touchscreen>").WithOptionalDevice("<Gamepad>");

        return asset;
    }

    static void Describe(InputActionAsset asset, StringBuilder sb)
    {
        foreach (InputActionMap map in asset.actionMaps)
        {
            sb.Append("  map ").Append(map.name).Append(": ")
              .Append(map.actions.Count).Append(" actions, ")
              .Append(map.bindings.Count).AppendLine(" bindings");
            foreach (InputAction action in map.actions)
                sb.Append("    ").Append(action.name).Append(" (").Append(action.type).Append(", ")
                  .Append(action.expectedControlType).Append(") ")
                  .Append(action.bindings.Count).AppendLine(" bindings");
        }
        sb.Append("  schemes:");
        foreach (InputControlScheme scheme in asset.controlSchemes)
            sb.Append(' ').Append(scheme.name);
        sb.AppendLine();
    }
}
