// ChunkStitcher.cs — an endless side run from pre-built strips: appends a chunk whose entry
// height equals the last chunk's exit height, ramps difficulty by distance, and returns the
// chunks behind the camera to a pool. The order is a pure function of the seed.
//
// Drop into a Runtime assembly and put one on an empty object at the start of the run.
// No package needed. A chunk is a prefab authored from x = 0 to x = length with its floor at
// entryHeight on the left edge and exitHeight on the right, both in tiles.
//
//   stitcher.Appended += (chunk, instance, startX) => pickups.Fill(instance, startX);
//   stitcher.Begin(seed);
//
// Run ChunkStitcher.SetProblems in an Edit Mode test: it is the invariant that the run can
// never dead-end, and it needs no scene.
using System;
using System.Collections.Generic;
using UnityEngine;

public sealed class ChunkStitcher : MonoBehaviour
{
    [Serializable]
    public class Chunk
    {
        public GameObject prefab;
        [Tooltip("World units from the left edge to the right edge.")]
        public float length = 40f;
        [Tooltip("Floor height at the left edge, in tiles.")]
        public int entryHeight;
        [Tooltip("Floor height at the right edge, in tiles.")]
        public int exitHeight;
        [Tooltip("0 is the gentlest. A chunk appears once the run has earned its number.")]
        public int difficulty;
    }

    public List<Chunk> chunks = new List<Chunk>();

    [Tooltip("What the run is seen from. Chunks are kept ahead of it and recycled behind it. Never Camera.main per frame.")]
    public Transform view;

    public int seed = 1;
    [Tooltip("Floor height the run starts at, in tiles.")]
    public int startHeight;
    [Tooltip("World units of run per difficulty step: at 250, difficulty 2 unlocks at 500.")]
    public float unitsPerDifficulty = 250f;
    [Tooltip("How many steps below the unlocked difficulty still appear, so the run breathes.")]
    public int difficultyWindow = 1;
    [Tooltip("World units kept built ahead of the view: at least one and a half screens.")]
    public float ahead = 40f;
    [Tooltip("World units behind the view before a chunk is recycled.")]
    public float behind = 30f;

    /// <summary>(definition, instance, world x of its left edge). Raised after a chunk is placed.</summary>
    public event Action<Chunk, GameObject, float> Appended;

    /// <summary>World x of the right edge of the last chunk placed.</summary>
    public float BuiltTo { get; private set; }
    public int ExitHeight { get; private set; }

    struct Live { public int index; public GameObject instance; public float endX; }

    readonly Queue<Live> _live = new Queue<Live>();
    readonly Dictionary<int, Stack<GameObject>> _pool = new Dictionary<int, Stack<GameObject>>();
    System.Random _rng;
    float _originX;

    // ------------------------------------------------------------------ pure, testable

    /// <summary>
    /// The index of the next chunk: among those whose entry matches <paramref name="exitHeight"/>,
    /// prefer difficulties in [unlocked - window, unlocked]; with none there, take any at or
    /// below unlocked. -1 only when the set breaks SetProblems.
    /// </summary>
    public static int Pick(IReadOnlyList<Chunk> set, int exitHeight, int unlocked, int window, System.Random rng)
    {
        int inBand = 0, allowed = 0;
        for (int i = 0; i < set.Count; i++)
        {
            if (set[i].entryHeight != exitHeight || set[i].difficulty > unlocked) continue;
            allowed++;
            if (set[i].difficulty >= unlocked - window) inBand++;
        }
        if (allowed == 0) return -1;
        bool band = inBand > 0;
        int roll = rng.Next(band ? inBand : allowed);
        for (int i = 0; i < set.Count; i++)
        {
            if (set[i].entryHeight != exitHeight || set[i].difficulty > unlocked) continue;
            if (band && set[i].difficulty < unlocked - window) continue;
            if (roll-- == 0) return i;
        }
        return -1;
    }

    /// <summary>The first <paramref name="count"/> chunk indices of a run. Same arguments, same list.</summary>
    public static List<int> Sequence(IReadOnlyList<Chunk> set, int seed, int count, int startHeight,
                                     float unitsPerDifficulty, int window)
    {
        var order = new List<int>(count);
        var rng = new System.Random(seed);
        int height = startHeight;
        float distance = 0f;
        for (int n = 0; n < count; n++)
        {
            int i = Pick(set, height, Unlocked(distance, unitsPerDifficulty), window, rng);
            if (i < 0) break;
            order.Add(i);
            height = set[i].exitHeight;
            distance += set[i].length;
        }
        return order;
    }

    public static int Unlocked(float distance, float unitsPerDifficulty) =>
        unitsPerDifficulty <= 0f ? int.MaxValue : Mathf.FloorToInt(distance / unitsPerDifficulty);

    /// <summary>
    /// What would let a run dead-end, as sentences: a start height or an exit height that no
    /// difficulty-0 chunk begins at, a chunk with no prefab or no length. Empty when sound.
    /// </summary>
    public static List<string> SetProblems(IReadOnlyList<Chunk> set, int startHeight)
    {
        var problems = new List<string>();
        var easyEntries = new HashSet<int>();
        for (int i = 0; i < set.Count; i++)
        {
            if (set[i].prefab == null) problems.Add("chunk " + i + " has no prefab");
            if (set[i].length <= 0f) problems.Add("chunk " + i + " has no length");
            if (set[i].difficulty == 0) easyEntries.Add(set[i].entryHeight);
        }
        if (!easyEntries.Contains(startHeight))
            problems.Add("no difficulty-0 chunk enters at the start height " + startHeight);
        for (int i = 0; i < set.Count; i++)
            if (!easyEntries.Contains(set[i].exitHeight))
                problems.Add("chunk " + i + " exits at height " + set[i].exitHeight + ", where no difficulty-0 chunk enters");
        return problems;
    }

    // ------------------------------------------------------------------ runtime

    /// <summary>Clear the run and start again from this object's position with a new seed.</summary>
    public void Begin(int newSeed)
    {
        while (_live.Count > 0) Release(_live.Dequeue());
        seed = newSeed;
        _rng = new System.Random(seed);
        _originX = transform.position.x;
        BuiltTo = _originX;
        ExitHeight = startHeight;
        Fill();
    }

    void Start()
    {
        List<string> problems = SetProblems(chunks, startHeight);
        if (problems.Count > 0)
        {
            Debug.LogError("[CHUNKS] the set can dead-end:\n  " + string.Join("\n  ", problems), this);
            enabled = false;
            return;
        }
        if (_rng == null) Begin(seed);
    }

    void Update()
    {
        if (_rng == null || view == null) return;
        Fill();
        while (_live.Count > 0 && _live.Peek().endX < view.position.x - behind)
            Release(_live.Dequeue());
    }

    void Fill()
    {
        float until = (view != null ? view.position.x : _originX) + ahead;
        while (BuiltTo < until)
        {
            int i = Pick(chunks, ExitHeight, Unlocked(BuiltTo - _originX, unitsPerDifficulty), difficultyWindow, _rng);
            if (i < 0) { enabled = false; return; }
            Chunk chunk = chunks[i];
            GameObject instance = Take(i);
            // The chunk is authored at its own heights, so only x moves. The runner moves
            // through the world; the world is never scrolled past the runner.
            instance.transform.SetPositionAndRotation(new Vector3(BuiltTo, transform.position.y, 0f), Quaternion.identity);
            instance.SetActive(true);
            float startX = BuiltTo;
            BuiltTo += chunk.length;
            ExitHeight = chunk.exitHeight;
            _live.Enqueue(new Live { index = i, instance = instance, endX = BuiltTo });
            Appended?.Invoke(chunk, instance, startX);
        }
    }

    GameObject Take(int index)
    {
        if (_pool.TryGetValue(index, out Stack<GameObject> stack) && stack.Count > 0) return stack.Pop();
        return Instantiate(chunks[index].prefab, transform);
    }

    void Release(Live live)
    {
        live.instance.SetActive(false);
        if (!_pool.TryGetValue(live.index, out Stack<GameObject> stack))
            _pool[live.index] = stack = new Stack<GameObject>();
        stack.Push(live.instance);
    }
}
