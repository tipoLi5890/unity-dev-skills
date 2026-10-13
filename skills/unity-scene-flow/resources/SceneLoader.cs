// SceneLoader.cs — loads one content scene additively beside the Boot scene, reports progress,
// makes the new scene active, and unloads the one it replaces. One operation at a time: a second
// request while one is in flight is refused and counted, never queued.
//
// Drop into a Runtime assembly and add it to the Boot scene's root object (Bootstrap.cs adds it
// when it is missing). No package needed.
//
// Scenes are named by path — "Assets/Scenes/GateRoom.unity" — exactly as the build's scene list
// spells them. A name matches the first scene that has it; a path matches one scene.
//
// The loader cannot hang a loading screen: it waits on frames, never on scaled time, and a load
// that reports no progress for stallSeconds of real time fails with a reason instead of waiting.
using System;
using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;

[AddComponentMenu("Courier/Scene Loader")]
public sealed class SceneLoader : MonoBehaviour
{
    [Tooltip("Real seconds with no progress before a load is reported as failed.")]
    [SerializeField] float stallSeconds = 10f;

    [Tooltip("Real seconds a load is held before activation, so a loading screen is not a one-frame flash. 0 activates as soon as the scene is ready.")]
    [SerializeField] float minimumSeconds = 0f;

    [Tooltip("Free assets nothing references after an unload. It is a hitch, which is why it runs behind the loading screen.")]
    [SerializeField] bool unloadUnusedAssets = true;

    /// <summary>
    /// Optional hold at the end of a load: the scene is ready but not activated until this
    /// returns true — a fade that has to finish, a "press to continue". It is bounded by
    /// stallSeconds as well, so a gate nobody opens cannot hang the game.
    /// </summary>
    public Func<bool> activationGate;

    /// <summary>True while a load or an unload is in flight.</summary>
    public bool IsBusy { get; private set; }

    /// <summary>0..1 across the whole operation. 0.9 is "ready, waiting to activate".</summary>
    public float Progress { get; private set; }

    /// <summary>The content scene currently loaded; not valid when there is none.</summary>
    public Scene Content { get; private set; }

    /// <summary>The build path it was loaded from, or "" for an adopted scene with no asset.</summary>
    public string ContentPath { get; private set; } = "";

    public bool HasContent => Content.IsValid() && Content.isLoaded;

    /// <summary>Requests refused because another operation was in flight.</summary>
    public int Refused { get; private set; }

    public string LastError { get; private set; } = "";

    /// <summary>The scene is loaded, active, and its Awake and OnEnable have run.</summary>
    public event Action<Scene> Loaded;

    /// <summary>The scene with this name is gone; its objects are destroyed.</summary>
    public event Action<string> Unloaded;

    /// <summary>(scene path, reason). The loader is idle again when this is raised.</summary>
    public event Action<string, string> Failed;

    /// <summary>
    /// Replace the content scene with the one at <paramref name="scenePath"/>. The old scene is
    /// unloaded first, so the two never share memory. False when an operation is in flight.
    /// </summary>
    public bool Load(string scenePath)
    {
        if (!Begin()) return false;
        StartCoroutine(LoadRoutine(scenePath));
        return true;
    }

    /// <summary>Unload the content scene and leave only Boot. False when busy or nothing is loaded.</summary>
    public bool Unload()
    {
        if (IsBusy) { Refused++; return false; }
        if (!HasContent) return false;
        Begin();
        StartCoroutine(UnloadThenIdle());
        return true;
    }

    /// <summary>
    /// Take a scene that is already loaded as the content scene: the scene that was open when
    /// Play was pressed in the Editor, or one a test built with SceneManager.CreateScene. Makes
    /// it active and raises Loaded. False when busy, when content is already held, or when the
    /// scene is not loaded.
    /// </summary>
    public bool Adopt(Scene scene)
    {
        if (IsBusy) { Refused++; return false; }
        if (HasContent || !scene.IsValid() || !scene.isLoaded) return false;
        Content = scene;
        ContentPath = scene.path ?? "";
        SceneManager.SetActiveScene(scene);
        Progress = 1f;
        Loaded?.Invoke(scene);
        return true;
    }

    string _activating = "";

    void OnEnable() => SceneManager.sceneLoaded += OnSceneLoaded;
    void OnDisable() => SceneManager.sceneLoaded -= OnSceneLoaded;

    void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        // sceneLoaded is raised after the scene's Awake and OnEnable and before its Start, so
        // what a level instantiates from Start onwards lands in the level. What it instantiates
        // in Awake or OnEnable still lands in the scene that was active before: pass a parent.
        if (_activating.Length > 0 && scene.path == _activating) SceneManager.SetActiveScene(scene);
    }

    bool Begin()
    {
        if (IsBusy) { Refused++; return false; }
        IsBusy = true;
        Progress = 0f;
        LastError = "";
        return true;
    }

    IEnumerator LoadRoutine(string scenePath)
    {
        // Checked before anything is unloaded: a typo must not cost the scene the player is in.
        int index = SceneUtility.GetBuildIndexByScenePath(scenePath);
        if (index < 0)
        {
            Fail(scenePath, "not in the build's scene list");
            yield break;
        }

        if (HasContent) yield return UnloadRoutine();

        float started = Time.realtimeSinceStartup;
        _activating = scenePath;
        AsyncOperation op = SceneManager.LoadSceneAsync(index, LoadSceneMode.Additive);
        if (op == null)
        {
            Fail(scenePath, "LoadSceneAsync returned nothing");
            yield break;
        }

        // Held, so activation — every Awake and OnEnable of the scene in one frame — happens
        // when the loading screen says so. While it is held, progress stops at 0.9 and every
        // other async operation in the process queues behind this one.
        op.allowSceneActivation = false;
        float lastProgress = -1f;
        float lastMoved = Time.realtimeSinceStartup;
        while (op.progress < 0.9f)
        {
            if (op.progress > lastProgress)
            {
                lastProgress = op.progress;
                lastMoved = Time.realtimeSinceStartup;
            }
            else if (Time.realtimeSinceStartup - lastMoved > stallSeconds)
            {
                op.allowSceneActivation = true;      // release the queue it is blocking
                Fail(scenePath, "no progress for " + stallSeconds.ToString("F0") + " s at " +
                                op.progress.ToString("F2"));
                yield break;
            }
            Progress = op.progress;
            yield return null;
        }
        Progress = 0.9f;

        float heldFrom = Time.realtimeSinceStartup;
        while (Time.realtimeSinceStartup - started < minimumSeconds ||
               (activationGate != null && !activationGate()))
        {
            if (Time.realtimeSinceStartup - heldFrom > stallSeconds + minimumSeconds)
            {
                Debug.LogWarning("[SCENE] activation gate still closed after " +
                                 stallSeconds.ToString("F0") + " s: activating " + scenePath);
                break;
            }
            yield return null;
        }

        op.allowSceneActivation = true;
        while (!op.isDone) yield return null;

        Scene scene = SceneManager.GetSceneByPath(scenePath);
        if (!scene.IsValid() || !scene.isLoaded)
        {
            Fail(scenePath, "loaded, but no scene answers to that path");
            yield break;
        }

        // The active scene is where Instantiate and new GameObject land and whose lighting
        // settings render. Left on Boot, everything the level spawns outlives the level.
        // OnSceneLoaded has normally done this already; this covers a scene it did not match.
        _activating = "";
        if (SceneManager.GetActiveScene() != scene) SceneManager.SetActiveScene(scene);
        Content = scene;
        ContentPath = scenePath;
        Progress = 1f;
        IsBusy = false;
        Debug.Log("[SCENE] loaded " + scenePath + " in " +
                  (Time.realtimeSinceStartup - started).ToString("F2") + " s");
        Loaded?.Invoke(scene);
    }

    IEnumerator UnloadThenIdle()
    {
        yield return UnloadRoutine();
        Progress = 1f;
        IsBusy = false;
    }

    IEnumerator UnloadRoutine()
    {
        string name = Content.name;
        AsyncOperation op = SceneManager.UnloadSceneAsync(Content);
        Content = default;
        ContentPath = "";
        // Null when the scene cannot be unloaded — it is the only one loaded. With a Boot scene
        // that never happens, which is one more reason to have one.
        if (op != null) yield return op;
        if (unloadUnusedAssets) yield return Resources.UnloadUnusedAssets();
        Unloaded?.Invoke(name);
    }

    void Fail(string scenePath, string reason)
    {
        _activating = "";
        LastError = scenePath + ": " + reason;
        IsBusy = false;
        Debug.LogError("[SCENE] load failed — " + LastError);
        Failed?.Invoke(scenePath, reason);
    }
}
