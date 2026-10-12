// RoomBounds.cs — a room as data: a rectangle on tile boundaries, its doors, and one event
// when the runner enters it. The camera, the spawner and the save point all listen to that
// event; none of them owns the room.
//
// Drop into a Runtime assembly and put one on an empty object at each room's bottom-left
// corner. REQUIRES the built-in 2D physics module (com.unity.modules.physics2d). It names no
// camera type: to confine a camera to the room, call the camera's own switch from onEntered.
//
// Scene rules this script depends on:
//   - The runner carries a Rigidbody2D, or OnTriggerEnter2D never fires.
//   - The trigger is the room inset by `inset` on every side, so the triggers of two rooms
//     that share a wall never overlap and the runner is inside one room at most.
//   - The room object sits on a layer that collides with the runner's layer and nothing else.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Events;

[RequireComponent(typeof(BoxCollider2D))]
public sealed class RoomBounds : MonoBehaviour
{
    [Serializable]
    public struct Door
    {
        public string to;             // the roomId on the other side
        public Vector2 localPosition; // where the runner arrives in THIS room, relative to its corner
        public string requires;       // an ability or key the door is gated on; empty for none
        public bool oneWay;           // a ledge drop: the far room needs no door back
    }

    [Tooltip("Unique per level. Doors name rooms by this.")]
    public string roomId = "room";

    [Tooltip("World units, from this object's position (the bottom-left corner). Keep it a whole number of tiles.")]
    public Vector2 size = new Vector2(20f, 11.25f);

    [Tooltip("How far the trigger sits inside the room on every side.")]
    public float inset = 0.5f;

    public List<Door> doors = new List<Door>();

    [Tooltip("Only this object changes rooms. Empty means anything tagged Player.")]
    public Transform runner;

    [Tooltip("Raised when the runner enters this room. Wire the camera's room switch here.")]
    public UnityEvent onEntered = new UnityEvent();

    /// <summary>(previous room or null, room entered). Raised once per change of room.</summary>
    public static event Action<RoomBounds, RoomBounds> Entered;

    public static RoomBounds Current { get; private set; }
    public static IReadOnlyList<RoomBounds> All => _all;
    static readonly List<RoomBounds> _all = new List<RoomBounds>();

    public Rect WorldRect => new Rect(transform.position, size);
    public bool Contains(Vector2 point) => WorldRect.Contains(point);

    /// <summary>
    /// A confined camera needs a room at least one screen in both dimensions; in a smaller
    /// room it has no legal position and shows the neighbour.
    /// </summary>
    public bool FitsView(float orthographicSize, float aspect) =>
        size.y >= 2f * orthographicSize - 1e-4f && size.x >= 2f * orthographicSize * aspect - 1e-4f;

    public static RoomBounds Find(string id)
    {
        for (int i = 0; i < _all.Count; i++)
            if (_all[i].roomId == id) return _all[i];
        return null;
    }

    /// <summary>
    /// The room graph's invariants over every enabled room, as sentences: ids are unique,
    /// every door leads to a room that exists, every door that is not one-way has a door
    /// back, and no two rooms overlap. Empty when the graph is sound.
    /// </summary>
    public static List<string> GraphProblems()
    {
        var problems = new List<string>();
        for (int i = 0; i < _all.Count; i++)
        {
            RoomBounds a = _all[i];
            for (int j = i + 1; j < _all.Count; j++)
            {
                if (_all[j].roomId == a.roomId) problems.Add("two rooms are called '" + a.roomId + "'");
                if (a.WorldRect.Overlaps(_all[j].WorldRect))
                    problems.Add("rooms '" + a.roomId + "' and '" + _all[j].roomId + "' overlap");
            }
            foreach (Door door in a.doors)
            {
                RoomBounds b = Find(door.to);
                if (b == null) { problems.Add("'" + a.roomId + "' has a door to '" + door.to + "', which does not exist"); continue; }
                if (door.oneWay) continue;
                bool back = false;
                foreach (Door other in b.doors) back |= other.to == a.roomId;
                if (!back) problems.Add("'" + a.roomId + "' opens into '" + b.roomId + "', which has no door back");
            }
        }
        return problems;
    }

    /// <summary>Make this the current room now. Call it for the room a respawn lands in.</summary>
    public void Enter()
    {
        if (Current == this) return;
        RoomBounds previous = Current;
        Current = this;
        onEntered.Invoke();
        Entered?.Invoke(previous, this);
    }

    [ContextMenu("Fit Trigger To Room")]
    public void FitTrigger()
    {
        var box = GetComponent<BoxCollider2D>();
        box.isTrigger = true;
        box.offset = size * 0.5f;
        box.size = new Vector2(Mathf.Max(0.1f, size.x - 2f * inset), Mathf.Max(0.1f, size.y - 2f * inset));
    }

    void Reset() => FitTrigger();
    void OnValidate() => FitTrigger();

    void OnEnable() => _all.Add(this);

    void OnDisable()
    {
        _all.Remove(this);
        if (Current == this) Current = null;
    }

    void Start()
    {
        // The runner spawns inside a room without crossing its edge, so no trigger fires.
        Transform who = runner;
        if (who == null)
        {
            GameObject tagged = GameObject.FindWithTag("Player");
            if (tagged != null) who = tagged.transform;
        }
        if (who != null && Contains(who.position)) Enter();
    }

    void OnTriggerEnter2D(Collider2D other)
    {
        // A compound runner reports the child collider; its Rigidbody2D is the runner.
        Transform who = other.attachedRigidbody != null ? other.attachedRigidbody.transform : other.transform;
        if (runner != null ? who != runner : !who.CompareTag("Player")) return;
        Enter();
    }

    // Statics outlive a play session when domain reload is off.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _all.Clear();
        Current = null;
        Entered = null;
    }

    void OnDrawGizmos()
    {
        Gizmos.color = Current == this ? Color.green : Color.yellow;
        Gizmos.DrawWireCube((Vector3)WorldRect.center, size);
        Gizmos.color = Color.cyan;
        foreach (Door door in doors)
            Gizmos.DrawWireSphere(transform.position + (Vector3)door.localPosition, 0.25f);
    }
}
