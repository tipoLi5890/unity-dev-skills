// WaveSpawner — waves as data: each wave is a budget spent on a table of entries, released one at
// a time at spawn points the camera cannot see, under a cap on how many are alive at once, from a
// seeded generator so the same seed gives the same run.
//
// Drop into a Runtime assembly and add it to one object in the level. No package needed.
// It creates with Instantiate and removes with Destroy until the game assigns Create and Remove;
// point both at a pool and nothing here changes.
//
//   spawner.Create = (prefab, position, rotation) => pool.Take(prefab, position, rotation);
//   spawner.Remove = instance => pool.Return(instance);
//   health.Died += () => spawner.Despawn(gameObject);       // whoever ends a sentry tells the spawner
//
// Register with the probe where the game wires its harness:
//   GameProbe.Count("sentries", () => spawner.Live);
//   GameProbe.Register("wave", () => spawner.Wave);
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>One thing a wave may contain, and what it costs the wave's budget.</summary>
[Serializable]
public sealed class SpawnEntry
{
    public GameObject prefab;
    [Tooltip("Budget points one of these costs. A sentry is 1; a heavy one 3.")]
    public int cost = 1;
    [Tooltip("Relative chance among the entries the wave can afford.")]
    public int weight = 1;
    [Tooltip("First wave this entry may appear in. Wave numbers start at 1.")]
    public int fromWave = 1;
}

/// <summary>One authored wave. Waves past the end of the list are generated from the growth numbers.</summary>
[Serializable]
public sealed class WaveDefinition
{
    [Tooltip("Budget points this wave spends.")]
    public int budget = 6;
    [Tooltip("Seconds between two spawns of this wave.")]
    public float spawnInterval = 0.5f;
    [Tooltip("Seconds of rest before this wave starts.")]
    public float restBefore = 3f;
}

/// <summary>The choice of what a wave contains: plain C#, no scene, the same list for the same seed.</summary>
public static class WavePlanner
{
    /// <summary>
    /// Spend <paramref name="budget"/> on entries allowed in <paramref name="wave"/>, appending
    /// entry indices to <paramref name="into"/>. Returns the budget left over — less than the
    /// cheapest allowed entry, or all of it when nothing is allowed.
    /// </summary>
    public static int Fill(IList<SpawnEntry> entries, int wave, int budget, System.Random random, List<int> into)
    {
        while (true)
        {
            int total = 0;
            for (int i = 0; i < entries.Count; i++)
                if (Affordable(entries[i], wave, budget)) total += Mathf.Max(1, entries[i].weight);
            if (total == 0) return budget;

            int roll = random.Next(total);
            for (int i = 0; i < entries.Count; i++)
            {
                if (!Affordable(entries[i], wave, budget)) continue;
                roll -= Mathf.Max(1, entries[i].weight);
                if (roll >= 0) continue;
                into.Add(i);
                budget -= Mathf.Max(1, entries[i].cost);
                break;
            }
        }
    }

    static bool Affordable(SpawnEntry entry, int wave, int budget)
        => entry != null && entry.prefab != null && entry.fromWave <= wave && Mathf.Max(1, entry.cost) <= budget;
}

[DisallowMultipleComponent]
public sealed class WaveSpawner : MonoBehaviour
{
    [Header("Waves")]
    public SpawnEntry[] entries;
    [Tooltip("Authored waves, in order. May be empty: every wave is then generated.")]
    public WaveDefinition[] waves;
    [Tooltip("Keep going after the authored waves, with a budget that grows.")]
    public bool endless = true;
    [Tooltip("Budget of the first generated wave when no wave is authored.")]
    public int firstBudget = 6;
    [Tooltip("Budget points added per generated wave.")]
    public int budgetGrowth = 2;
    [Tooltip("Same seed, same waves. Change it for a different run; print it with every bug report.")]
    public int seed = 12345;
    [Tooltip("Wait for every live spawn to be removed before the next wave's rest starts.")]
    public bool waitForClear = true;

    [Header("Limits")]
    [Tooltip("Most spawns alive at once. A wave larger than this trickles in as slots free up.")]
    public int liveCap = 12;

    [Header("Where")]
    public Transform[] spawnPoints;
    [Tooltip("Spawn points inside this camera's view are skipped. Leave empty to allow any point.")]
    public Camera hideFrom;
    [Tooltip("Viewport margin around the screen that still counts as visible. 0.1 is a tenth of the screen.")]
    public float viewMargin = 0.1f;
    [Tooltip("Spawn points nearer than minDistance to this are skipped. Usually the runner.")]
    public Transform avoid;
    public float minDistance = 6f;

    /// <summary>Creates one instance. Default: Instantiate. Assign a pool's take.</summary>
    public Func<GameObject, Vector3, Quaternion, GameObject> Create;
    /// <summary>Removes one instance. Default: Destroy. Assign a pool's return.</summary>
    public Action<GameObject> Remove;

    /// <summary>The wave being spawned or fought, from 1. 0 before the first.</summary>
    public int Wave { get; private set; }
    public int Live => _live.Count;
    /// <summary>Spawns of the current wave still waiting for a slot or a point.</summary>
    public int Pending => _queue.Count;
    public int SpawnedTotal { get; private set; }
    /// <summary>Spawn attempts postponed because every point was in view or too near. Climbing without end means the level has no hidden point.</summary>
    public int Postponed { get; private set; }
    public bool Finished { get; private set; }

    public event Action<int> WaveStarted;
    public event Action<int> WaveCleared;
    /// <summary>(instance, wave) after each spawn — where the game hands the instance its target.</summary>
    public event Action<GameObject, int> Spawned;

    readonly List<GameObject> _live = new List<GameObject>();
    readonly List<int> _queue = new List<int>();
    readonly List<int> _candidates = new List<int>();
    System.Random _random;
    WaveDefinition _generated;
    WaveDefinition _current;
    float _timer;
    bool _resting;
    int _lastBudget;

    void Start()
    {
        _random = new System.Random(seed);
        _generated = new WaveDefinition();
        BeginRest();
    }

    // The fixed step, so spawning pauses with the game and a seeded run repeats step for step.
    void FixedUpdate()
    {
        if (Finished || _random == null) return;
        Prune();
        _timer -= Time.fixedDeltaTime;

        if (_resting)
        {
            if (_timer > 0f) return;
            _resting = false;
            Wave++;
            _queue.Clear();
            _lastBudget = _current.budget;
            WavePlanner.Fill(entries, Wave, _current.budget, _random, _queue);
            _timer = 0f;
            WaveStarted?.Invoke(Wave);
            return;
        }

        if (_queue.Count > 0)
        {
            if (_timer > 0f || _live.Count >= liveCap) return;
            if (TrySpawn(entries[_queue[0]])) _queue.RemoveAt(0);
            else Postponed++;
            _timer = _current.spawnInterval;
            return;
        }

        if (waitForClear && _live.Count > 0) return;
        WaveCleared?.Invoke(Wave);
        BeginRest();
    }

    /// <summary>Tell the spawner an instance is gone, and remove it through <see cref="Remove"/>.</summary>
    public void Despawn(GameObject instance)
    {
        if (instance == null || !_live.Remove(instance)) return;
        if (Remove != null) Remove(instance); else Destroy(instance);
    }

    void BeginRest()
    {
        int next = Wave;       // index of the wave about to start
        if (waves != null && next < waves.Length && waves[next] != null) _current = waves[next];
        else if (!endless && waves != null && waves.Length > 0) { Finished = true; return; }
        else
        {
            WaveDefinition last = waves != null && waves.Length > 0 ? waves[waves.Length - 1] : null;
            _generated.budget = (Wave == 0 ? firstBudget : _lastBudget) + (Wave == 0 ? 0 : budgetGrowth);
            _generated.spawnInterval = last != null ? last.spawnInterval : 0.5f;
            _generated.restBefore = last != null ? last.restBefore : 3f;
            _current = _generated;
        }
        _resting = true;
        _timer = _current.restBefore;
    }

    bool TrySpawn(SpawnEntry entry)
    {
        if (spawnPoints == null || spawnPoints.Length == 0) return false;
        _candidates.Clear();
        for (int i = 0; i < spawnPoints.Length; i++)
            if (spawnPoints[i] != null && Hidden(spawnPoints[i].position)) _candidates.Add(i);
        if (_candidates.Count == 0) return false;

        Transform point = spawnPoints[_candidates[_random.Next(_candidates.Count)]];
        GameObject instance = Create != null
            ? Create(entry.prefab, point.position, point.rotation)
            : Instantiate(entry.prefab, point.position, point.rotation);
        if (instance == null) return false;
        _live.Add(instance);
        SpawnedTotal++;
        Spawned?.Invoke(instance, Wave);
        return true;
    }

    bool Hidden(Vector3 position)
    {
        if (avoid != null && (position - avoid.position).sqrMagnitude < minDistance * minDistance) return false;
        if (hideFrom == null) return true;
        Vector3 v = hideFrom.WorldToViewportPoint(position);
        bool inView = v.z > 0f && v.x > -viewMargin && v.x < 1f + viewMargin && v.y > -viewMargin && v.y < 1f + viewMargin;
        return !inView;
    }

    // An instance destroyed or returned to a pool without Despawn still frees its slot.
    void Prune()
    {
        for (int i = _live.Count - 1; i >= 0; i--)
            if (_live[i] == null || !_live[i].activeInHierarchy) _live.RemoveAt(i);
    }
}
