// Bootstrap.cs — the one object that never unloads. It lives on the root of the Boot scene
// (build index 0), creates the services everything else asks for — GameState, SceneLoader,
// SaveStore — puts them in one registry, and loads the first content scene additively.
//
// Drop into a Runtime assembly beside GameState.cs, SceneLoader.cs and SaveStore.cs. No package
// needed. Set-up: a scene named Boot, first in the build's scene list, holding one GameObject
// with this component and nothing a level owns.
//
// Pressing Play in the Editor with a content scene open: when scene 0 of the build list is named
// Boot, EnsureBootScene loads it additively before the open scene's Awake, and Boot adopts the
// open scene as content instead of loading the first one. The Boot scene's own Awake still runs
// AFTER the open scene's, so content never touches a service in Awake or OnEnable — it asks
// through Bootstrap.WhenReady, which runs at once in a build and one frame late in that case.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// The services of the game, by type. Created once by Bootstrap; a second Provide of the same
/// type throws, so a service cannot be replaced behind a caller's back.
/// </summary>
public sealed class ServiceRegistry
{
    readonly Dictionary<Type, object> _services = new Dictionary<Type, object>();

    public int Count => _services.Count;

    public void Provide<T>(T service) where T : class
    {
        if (service == null) throw new ArgumentNullException(nameof(service));
        if (_services.ContainsKey(typeof(T)))
            throw new InvalidOperationException(typeof(T).Name + " is already provided");
        _services[typeof(T)] = service;
    }

    public bool TryGet<T>(out T service) where T : class
    {
        bool found = _services.TryGetValue(typeof(T), out object boxed);
        service = found ? (T)boxed : null;
        return found;
    }

    public T Get<T>() where T : class
    {
        if (TryGet(out T service)) return service;
        var names = new List<string>();
        foreach (Type t in _services.Keys) names.Add(t.Name);
        throw new InvalidOperationException(typeof(T).Name + " was never provided. Provided: " +
                                            string.Join(", ", names.ToArray()));
    }
}

[AddComponentMenu("Courier/Bootstrap")]
[DefaultExecutionOrder(-1000)]   // within the Boot scene, before anything else in it
public sealed class Bootstrap : MonoBehaviour
{
    public const string BootSceneName = "Boot";

    [Tooltip("Build path of the scene loaded after boot, e.g. Assets/Scenes/Menu.unity. Empty: load nothing and stay in Boot.")]
    [SerializeField] string firstScenePath = "";

    [Tooltip("The phase the game is in once that scene has loaded.")]
    [SerializeField] GamePhase firstPhase = GamePhase.Menu;

    [Tooltip("File name under Application.persistentDataPath.")]
    [SerializeField] string saveFileName = "save.json";

    [Tooltip("Pause when the application goes to the background while Playing.")]
    [SerializeField] bool pauseOnBackground = true;

    public static Bootstrap Instance { get; private set; }

    /// <summary>True once the services exist. Content waits on this, or uses WhenReady.</summary>
    public static bool Ready => Instance != null && Instance._ready;

    public ServiceRegistry Services { get; private set; }
    public GameState State { get; private set; }
    public SceneLoader Loader { get; private set; }
    public SaveStore Saves { get; private set; }

    /// <summary>
    /// The application is leaving the foreground. On a phone this is the last callback that is
    /// certain to run: write the save here, not in OnApplicationQuit.
    /// </summary>
    public event Action Backgrounded;

    static readonly List<Action<Bootstrap>> s_Waiting = new List<Action<Bootstrap>>();
    static string s_OpenedScenePath = "";

    bool _ready;
    GamePhase _arriveAs = GamePhase.Playing;

    /// <summary>The one static accessor: Bootstrap.Get&lt;GameState&gt;(). Throws before boot.</summary>
    public static T Get<T>() where T : class
    {
        if (!Ready) throw new InvalidOperationException(
            "Bootstrap.Get<" + typeof(T).Name + "> before boot: ask from Start, or through Bootstrap.WhenReady");
        return Instance.Services.Get<T>();
    }

    /// <summary>Run now when the services exist, otherwise as soon as they do.</summary>
    public static void WhenReady(Action<Bootstrap> then)
    {
        if (then == null) return;
        if (Ready) then(Instance);
        else s_Waiting.Add(then);
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        // With domain reload off, statics survive the previous Play session.
        Instance = null;
        s_Waiting.Clear();
        s_OpenedScenePath = "";
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    static void EnsureBootScene()
    {
        // Opt-in by name: nothing happens in a project whose first scene is not called Boot.
        if (SceneManager.sceneCountInBuildSettings == 0) return;
        string first = SceneUtility.GetScenePathByBuildIndex(0);
        if (Path.GetFileNameWithoutExtension(first) != BootSceneName) return;

        Scene opened = SceneManager.GetActiveScene();
        if (opened.buildIndex == 0) return;                      // a build, or Boot itself was open
        // The test framework starts PlayMode runs in a scene it names InitTestScene<guid>; a
        // test builds what it needs, and a Boot scene beside it would answer for the test's own.
        if (opened.name.StartsWith("InitTestScene", StringComparison.Ordinal)) return;

        s_OpenedScenePath = opened.path;
        SceneManager.LoadScene(0, LoadSceneMode.Additive);
    }

    void Awake()
    {
        if (Instance != null && Instance != this)
        {
            // Boot loaded a second time — a "back to menu" that loaded scene 0. Keep the first.
            Debug.LogWarning("[BOOT] a second Bootstrap was loaded and removed: load content scenes, never the Boot scene");
            Destroy(gameObject);
            return;
        }
        Instance = this;

        if (gameObject.scene.name != BootSceneName)
            Debug.LogWarning("[BOOT] Bootstrap is in scene '" + gameObject.scene.name +
                             "', which unloads: it belongs in the scene named " + BootSceneName);

        // Order is the dependency order, written once and read top to bottom.
        Services = new ServiceRegistry();
        State = new GameState();
        Loader = GetComponent<SceneLoader>();
        if (Loader == null) Loader = gameObject.AddComponent<SceneLoader>();
        Saves = new SaveStore(Application.persistentDataPath, saveFileName);

        Services.Provide(State);
        Services.Provide(Loader);
        Services.Provide(Saves);

        State.RegisterOnProbe();
        Loader.Loaded += OnContentLoaded;
        Loader.Failed += OnContentFailed;

        _ready = true;
        Debug.Log("[BOOT] ready services=" + Services.Count + " scene=" + gameObject.scene.name);

        Action<Bootstrap>[] waiting = s_Waiting.ToArray();
        s_Waiting.Clear();
        foreach (Action<Bootstrap> then in waiting) then(this);
    }

    void Start()
    {
        if (Instance != this) return;

        if (!string.IsNullOrEmpty(s_OpenedScenePath))
        {
            // Play was pressed with a content scene open: that scene is the content.
            Scene opened = SceneManager.GetSceneByPath(s_OpenedScenePath);
            s_OpenedScenePath = "";
            if (AdoptContent(opened)) return;
        }
        if (!string.IsNullOrEmpty(firstScenePath)) LoadContent(firstScenePath, firstPhase);
    }

    /// <summary>
    /// Go to Loading, replace the content scene, and arrive in <paramref name="arriveAs"/>.
    /// False when the phase does not allow a load or the loader is busy; nothing has changed.
    /// </summary>
    public bool LoadContent(string scenePath, GamePhase arriveAs = GamePhase.Playing)
    {
        if (Loader.IsBusy || !State.CanGo(GamePhase.Loading)) return false;
        // Refused here, before the phase moves: a path that is not in the build would otherwise
        // leave the game in Loading with the old scene still on screen.
        if (SceneUtility.GetBuildIndexByScenePath(scenePath) < 0)
        {
            Debug.LogError("[BOOT] '" + scenePath + "' is not in the build's scene list");
            return false;
        }
        State.TryGo(GamePhase.Loading);
        _arriveAs = arriveAs;
        return Loader.Load(scenePath);
    }

    /// <summary>The same, for a scene that is already loaded.</summary>
    public bool AdoptContent(Scene scene, GamePhase arriveAs = GamePhase.Playing)
    {
        if (Loader.IsBusy || Loader.HasContent || !scene.IsValid() || !scene.isLoaded) return false;
        if (State.Phase != GamePhase.Loading && !State.TryGo(GamePhase.Loading)) return false;
        _arriveAs = arriveAs;
        return Loader.Adopt(scene);
    }

    void OnContentLoaded(Scene scene)
    {
        if (State.Phase == GamePhase.Loading) State.TryGo(_arriveAs);
    }

    void OnContentFailed(string scenePath, string reason)
    {
        // The old scene may already be gone. The menu is the one place that is always reachable.
        if (State.Phase == GamePhase.Loading) State.TryGo(GamePhase.Menu);
    }

    void OnApplicationPause(bool paused)
    {
        if (!paused || Instance != this || !_ready) return;
        if (pauseOnBackground && State.IsPlaying) State.TryGo(GamePhase.Paused);
        Backgrounded?.Invoke();
    }

    void OnDestroy()
    {
        if (Instance != this) return;
        if (Loader != null)
        {
            Loader.Loaded -= OnContentLoaded;
            Loader.Failed -= OnContentFailed;
        }
        if (State != null) State.ReleaseTimeScale();
        Instance = null;
    }
}
