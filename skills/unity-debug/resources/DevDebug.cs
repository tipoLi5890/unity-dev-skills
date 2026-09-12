using UnityEngine;

/// <summary>
/// DevDebug — drop-in runtime diagnostics for Unity play-mode issues.
///
/// Attach to the player (or any moving / physics object). Output goes to Unity's
/// Editor.log (grep "[DBG]") AND an on-screen panel, so a coding agent can debug by
/// reading the log file directly instead of asking the user for screenshots.
/// DELETE this component (and the file) when you are done.
///
/// Answers the usual "why is play mode misbehaving?" questions fast:
///   * Is it actually moving?          -> pos / velocity / travelled
///   * Is time frozen (paused)?        -> timeScale
///   * Is the body kinematic / locked? -> isKinematic / constraints
///   * Are there duplicates?           -> count of active objects with watchTag
///   * What did it hit?                -> lastEvent (own collision/trigger callbacks)
///
/// NOTE: uses rb.linearVelocity (Unity 6+). On older Unity replace with rb.velocity.
/// </summary>
public class DevDebug : MonoBehaviour
{
    [Header("Output")]
    public bool logToConsole = true;    // periodic "[DBG] ..." line to Editor.log
    public bool showOverlay = true;     // on-screen panel
    public int logEveryNFixed = 20;     // ~0.4s at the default 50 Hz physics rate

    [Header("What to watch")]
    public string watchTag = "Player";  // counts active objects with this tag (spot duplicates)

    private Rigidbody rb;
    private Vector3 startPos;
    private string lastEvent = "(none)";
    private int frame;

    void Awake()
    {
        rb = GetComponent<Rigidbody>();
    }

    void Start()
    {
        startPos = transform.position;
    }

    void FixedUpdate()
    {
        frame++;
        if (logToConsole && frame % Mathf.Max(1, logEveryNFixed) == 0)
            Debug.Log("[DBG] " + State());
    }

    string State()
    {
        Vector3 pos = transform.position;
        Vector3 vel = rb != null ? rb.linearVelocity : Vector3.zero;
        int count = string.IsNullOrEmpty(watchTag) ? -1 : GameObject.FindGameObjectsWithTag(watchTag).Length;
        return $"f#{frame} tScale={Time.timeScale} pos={pos} vel={vel} " +
               $"travelled={Vector3.Distance(pos, startPos):F2} " +
               $"kinematic={(rb != null && rb.isKinematic)} " +
               $"constraints={(rb != null ? rb.constraints.ToString() : "noRB")} " +
               $"'{watchTag}'x{count} last={lastEvent}";
    }

    void OnCollisionEnter(Collision c)
    {
        lastEvent = $"COLLIDE {c.gameObject.name} [{c.gameObject.tag}]";
    }

    void OnTriggerEnter(Collider o)
    {
        lastEvent = $"TRIGGER {o.name} [{o.tag}]";
    }

    void OnGUI()
    {
        if (!showOverlay) return;
        GUIStyle s = new GUIStyle(GUI.skin.box)
        {
            alignment = TextAnchor.UpperLeft,
            fontSize = 15,
            wordWrap = true
        };
        s.normal.textColor = Color.green;
        GUI.Box(new Rect(10, 10, 820, 140), "[DevDebug]  " + State(), s);
    }
}
