// RebindStore — keep the player's rebinds, and run one interactive rebind without the usual traps.
//
// REQUIRES com.unity.inputsystem.
// Drop into a Runtime assembly that references Unity.InputSystem. Static; nothing to put in a scene.
//
// What is stored is the override layer only — a small JSON document keyed by binding id — never
// the asset. Load it once at boot, on the same InputActionAsset instance the reader enables,
// before the first frame of play:
//
//   RebindStore.Load(actions);                                   // PlayerPrefs, default key
//   RebindStore.LoadFromPath(actions, RebindStore.DefaultPath);  // or a file beside the saves
//
// Binding ids are the join key. Regenerating the asset with new ids orphans every saved rebind,
// so an asset that has shipped keeps its ids.
using System;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

public static class RebindStore
{
    public const string DefaultKey = "input.rebinds.v1";

    public static string DefaultPath => Path.Combine(Application.persistentDataPath, "rebinds.json");

    // ---- PlayerPrefs ---------------------------------------------------------------------------

    public static void Save(InputActionAsset actions, string key = DefaultKey)
    {
        PlayerPrefs.SetString(key, actions.SaveBindingOverridesAsJson());
        PlayerPrefs.Save();
    }

    /// <summary>False when nothing was stored or the stored text was rejected; the bindings are then unchanged.</summary>
    public static bool Load(InputActionAsset actions, string key = DefaultKey)
        => Apply(actions, PlayerPrefs.GetString(key, string.Empty), "PlayerPrefs:" + key);

    public static void Reset(InputActionAsset actions, string key = DefaultKey)
    {
        actions.RemoveAllBindingOverrides();
        PlayerPrefs.DeleteKey(key);
        PlayerPrefs.Save();
    }

    // ---- a file --------------------------------------------------------------------------------

    public static void SaveToPath(InputActionAsset actions, string path)
    {
        string json = actions.SaveBindingOverridesAsJson();
        string dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        // Write beside, then swap: a quit half way through must leave the old file, not half of a new one.
        string tmp = path + ".tmp";
        File.WriteAllText(tmp, json);
        if (File.Exists(path)) File.Delete(path);
        File.Move(tmp, path);
    }

    public static bool LoadFromPath(InputActionAsset actions, string path)
    {
        if (!File.Exists(path)) return false;
        string json;
        try { json = File.ReadAllText(path); }
        catch (IOException e)
        {
            Debug.LogWarning("[INPUT] rebinds unreadable at " + path + ": " + e.Message);
            return false;
        }
        return Apply(actions, json, path);
    }

    static bool Apply(InputActionAsset actions, string json, string source)
    {
        if (string.IsNullOrEmpty(json)) return false;
        // Loading removes the existing overrides first, so a document that fails to parse would
        // leave the player on defaults mid-session. Keep the current layer and put it back.
        string before = actions.SaveBindingOverridesAsJson();
        try
        {
            actions.LoadBindingOverridesFromJson(json);
            return true;
        }
        catch (Exception e)
        {
            Debug.LogWarning("[INPUT] rebinds from " + source + " rejected (" + e.GetType().Name +
                             "): " + e.Message);
            actions.LoadBindingOverridesFromJson(before);
            return false;
        }
    }

    // ---- one interactive rebind ----------------------------------------------------------------

    /// <summary>
    /// Listen for the next control and bind it to <paramref name="bindingIndex"/> of
    /// <paramref name="action"/>. For a composite, pass the index of the part (up, down, …); the
    /// composite row itself throws InvalidOperationException. <paramref name="finished"/> gets true on a new binding, false on a
    /// cancel; either way the operation is disposed and the action is back in its previous state.
    /// </summary>
    public static InputActionRebindingExtensions.RebindingOperation Begin(
        InputAction action, int bindingIndex, Action<bool> finished = null, string cancelPath = "<Keyboard>/escape")
    {
        // The operation throws InvalidOperationException on an enabled action.
        bool wasEnabled = action.enabled;
        action.Disable();

        void End(InputActionRebindingExtensions.RebindingOperation op, bool ok)
        {
            op.Dispose();                       // it holds native memory; a leaked one is reported at exit
            if (wasEnabled) action.Enable();
            finished?.Invoke(ok);
        }

        // The package already excludes pointer position and delta. It adds an Escape cancel only
        // when the action is not a Button, so a Launch row would have no way out without this.
        return action.PerformInteractiveRebinding(bindingIndex)
            .WithCancelingThrough(cancelPath)
            // A stick sweeps through other controls on its way; wait and take the strongest.
            .OnMatchWaitForAnother(0.1f)
            .OnComplete(op => End(op, true))
            .OnCancel(op => End(op, false))
            .Start();
    }

    /// <summary>
    /// The name of another action in the same map already bound to the same control as this
    /// binding, or null. Call it in the finished callback and decide: swap, refuse or allow.
    /// </summary>
    public static string FindConflict(InputAction action, int bindingIndex)
    {
        InputActionMap map = action.actionMap;
        if (map == null) return null;
        InputBinding mine = action.bindings[bindingIndex];
        foreach (InputBinding other in map.bindings)
        {
            if (other.id == mine.id || other.isComposite) continue;
            if (string.Equals(other.effectivePath, mine.effectivePath, StringComparison.OrdinalIgnoreCase))
                return other.action;
        }
        return null;
    }

    /// <summary>The text to show for a binding — "Space", "A", "LS" — after overrides.</summary>
    public static string Label(InputAction action, int bindingIndex)
        => action.GetBindingDisplayString(bindingIndex);

    /// <summary>
    /// The first binding of an action in a control scheme, or -1. For a composite this is the
    /// composite row; its parts are the following indices.
    /// </summary>
    public static int IndexInScheme(InputAction action, string scheme)
        => action.GetBindingIndex(InputBinding.MaskByGroup(scheme));
}
