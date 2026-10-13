// PersistentId.cs — a stable id for a scene object the save file talks about: a pickup, a gate,
// a switch, a checkpoint. The save stores this string; it never stores a reference, an instance
// id or a hierarchy path, none of which survive a restart.
//
// Drop into a Runtime assembly. No package needed. Add it to every scene object whose state is
// saved. The id is generated in the Editor when the component is added, and regenerated when a
// duplicate of the object is made in the same scene. A prefab ASSET keeps an empty id — every
// instance would otherwise share it — and each instance placed in a scene gets its own.
//
// At runtime the ids of loaded objects are in one table: PersistentId.TryFind(id, out found).
// An object spawned in play gets its id from the data that spawned it, through Assign.
using System;
using System.Collections.Generic;
using UnityEngine;

[AddComponentMenu("Courier/Persistent Id")]
[DisallowMultipleComponent]
public sealed class PersistentId : MonoBehaviour
{
    [Tooltip("Written into save files. Changing it orphans every save that mentions this object.")]
    [SerializeField] string id = "";

    public string Id => id;

    static readonly Dictionary<string, PersistentId> s_Loaded = new Dictionary<string, PersistentId>();

    /// <summary>How many ids are registered — a readiness number for the probe.</summary>
    public static int LoadedCount => s_Loaded.Count;

    /// <summary>The loaded object with this id. Objects authored inactive never register.</summary>
    public static bool TryFind(string id, out PersistentId found)
    {
        if (!string.IsNullOrEmpty(id) && s_Loaded.TryGetValue(id, out found) && found != null) return true;
        found = null;
        return false;
    }

    /// <summary>Every loaded id, for the pass that applies a save to a scene that just loaded.</summary>
    public static void CopyLoaded(List<PersistentId> into)
    {
        into.Clear();
        foreach (PersistentId p in s_Loaded.Values)
            if (p != null) into.Add(p);
    }

    /// <summary>Give a runtime-spawned object the id its spawn data carries.</summary>
    public void Assign(string newId)
    {
        if (string.IsNullOrEmpty(newId)) throw new ArgumentException("an id cannot be empty", nameof(newId));
        Unregister();
        id = newId;
        Register();
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics() => s_Loaded.Clear();

    void Awake() => Register();
    void OnDestroy() => Unregister();

    void Register()
    {
        if (string.IsNullOrEmpty(id)) return;       // a pooled or spawned object before Assign
        if (s_Loaded.TryGetValue(id, out PersistentId other) && other != null && other != this)
        {
            // Two objects answering to one id means one of them loads the other's state.
            Debug.LogError("[SAVE] duplicate persistent id " + id + " on '" + name + "' and '" +
                           other.name + "': the second is not registered", this);
            return;
        }
        s_Loaded[id] = this;
    }

    void Unregister()
    {
        if (!string.IsNullOrEmpty(id) && s_Loaded.TryGetValue(id, out PersistentId held) && held == this)
            s_Loaded.Remove(id);
    }

#if UNITY_EDITOR
    static readonly List<PersistentId> s_Scratch = new List<PersistentId>();

    void Reset() => EnsureUnique();
    void OnValidate() => EnsureUnique();

    [ContextMenu("Regenerate Id (orphans saved state)")]
    void Regenerate()
    {
        id = "";
        EnsureUnique();
    }

    void EnsureUnique()
    {
        if (Application.isPlaying) return;

        UnityEngine.SceneManagement.Scene scene = gameObject.scene;
        bool isAsset = !scene.IsValid() ||
                       UnityEditor.SceneManagement.EditorSceneManager.IsPreviewScene(scene);
        if (isAsset)
        {
            // The prefab asset, or the prefab open for editing: no id, so no two instances
            // start out with the same one.
            if (!string.IsNullOrEmpty(id)) id = "";
            return;
        }

        if (!string.IsNullOrEmpty(id) && !TakenInScene(scene)) return;

        id = Guid.NewGuid().ToString("N");
        UnityEditor.EditorUtility.SetDirty(this);
        // On a prefab instance the new value is an override, and an override set from code is
        // dropped on save unless it is recorded.
        UnityEditor.PrefabUtility.RecordPrefabInstancePropertyModifications(this);
    }

    bool TakenInScene(UnityEngine.SceneManagement.Scene scene)
    {
        // OnValidate also runs while a scene is still loading, when its roots cannot be listed.
        // Ids that were saved unique are unique; the check matters for a copy made in the Editor.
        if (!scene.isLoaded) return false;
        foreach (GameObject root in scene.GetRootGameObjects())
        {
            root.GetComponentsInChildren(true, s_Scratch);
            foreach (PersistentId other in s_Scratch)
                if (other != this && other.id == id) return true;
        }
        return false;
    }
#endif
}
