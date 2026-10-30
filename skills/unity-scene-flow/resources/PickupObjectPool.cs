// PickupObjectPool.cs — pickups that are reused instead of instantiated and destroyed, on
// UnityEngine.Pool.ObjectPool<T>. Spawn hands out an instance, Despawn takes it back, and a
// respawn after a checkpoint gets the very objects the runner collected a moment ago. Each
// instance carries a PooledPickup (PooledPickup.cs, same assembly).
//
// Drop into a Runtime assembly and put the component in the Boot scene, so the pool and its
// instances outlive the level: instances are parented under the pool, never under level
// objects. No package needed. Assign a prefab, or call Configure with a factory when the
// pickups are built in code.
//
// What the pool does NOT do is clean a pickup: everything gameplay changed on the instance is
// put back in OnRelease below, or in the pickup's own OnEnable — see reference/pooling.md.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Pool;

[AddComponentMenu("Courier/Pickup Pool")]
public sealed class PickupObjectPool : MonoBehaviour
{
    [Tooltip("What a pooled instance is made from. Leave empty and call Configure when instances are built in code.")]
    [SerializeField] GameObject prefab;

    [Tooltip("Starting size of the pool's internal stack. Nothing is created ahead of time by this number.")]
    [SerializeField] int defaultCapacity = 16;

    [Tooltip("The most idle instances the pool keeps. One released beyond this is destroyed.")]
    [SerializeField] int maxSize = 64;

    [Tooltip("Instances created in Start, so the first pickups of a level cost no Instantiate. 0 creates on demand.")]
    [SerializeField] int prewarm = 0;

    ObjectPool<PooledPickup> _pool;
    Func<GameObject> _factory;
    readonly List<PooledPickup> _live = new List<PooledPickup>();

    /// <summary>Instances the pool has made and not destroyed: live plus idle.</summary>
    public int CountAll => _pool != null ? _pool.CountAll : 0;
    public int CountActive => _pool != null ? _pool.CountActive : 0;
    public int CountInactive => _pool != null ? _pool.CountInactive : 0;

    /// <summary>Times the create callback ran. Flat while the level plays is the goal.</summary>
    public int Created { get; private set; }

    /// <summary>Instances destroyed because the pool was full. Above 0: maxSize is too small.</summary>
    public int Destroyed { get; private set; }

    /// <summary>Despawn calls for an instance that was already back.</summary>
    public int DoubleReleases { get; private set; }

    /// <summary>
    /// Set the factory and the sizes from code, before the first Spawn. Calling it again throws
    /// the old pool away, with every idle instance in it.
    /// </summary>
    public void Configure(Func<GameObject> factory, int capacity, int max)
    {
        if (_pool != null) _pool.Dispose();
        _pool = null;
        _factory = factory;
        defaultCapacity = Mathf.Max(1, capacity);
        maxSize = Mathf.Max(1, max);
    }

    void Start()
    {
        if (prewarm > 0) Prewarm(prewarm);
    }

    /// <summary>Create <paramref name="count"/> instances now — behind the loading screen.</summary>
    public void Prewarm(int count)
    {
        var made = new List<PooledPickup>(count);
        for (int i = 0; i < count; i++) made.Add(Items.Get());
        foreach (PooledPickup p in made) Despawn(p);
    }

    public PooledPickup Spawn(Vector3 position, string id = "")
    {
        PooledPickup p = Items.Get();
        p.Id = id ?? "";
        p.transform.SetPositionAndRotation(position, Quaternion.identity);
        return p;
    }

    public void Despawn(PooledPickup pickup)
    {
        if (pickup == null) return;
        // ObjectPool's own double-release check runs in the Editor only. In a player a second
        // Release puts the instance in the stack twice, and two Spawns then hand out one object.
        if (!pickup.InUse)
        {
            DoubleReleases++;
            return;
        }
        Items.Release(pickup);
    }

    /// <summary>Take back everything that is out — the first step of a checkpoint respawn.</summary>
    public void DespawnAll()
    {
        for (int i = _live.Count - 1; i >= 0; i--) Despawn(_live[i]);
    }

    ObjectPool<PooledPickup> Items
    {
        get
        {
            if (_pool == null)
                _pool = new ObjectPool<PooledPickup>(Create, OnGet, OnRelease, OnDestroyItem,
                                                     true, defaultCapacity, maxSize);
            return _pool;
        }
    }

    PooledPickup Create()
    {
        GameObject go;
        if (_factory != null) go = _factory();
        else if (prefab != null) go = Instantiate(prefab);
        else throw new InvalidOperationException("PickupObjectPool on '" + name + "' has no prefab and no factory");

        // Under the pool, so the instance lives in the pool's scene and not in the level's.
        go.transform.SetParent(transform, false);
        var pickup = go.GetComponent<PooledPickup>();
        if (pickup == null) pickup = go.AddComponent<PooledPickup>();
        pickup.owner = this;
        pickup.restScale = go.transform.localScale;
        Created++;
        return pickup;
    }

    void OnGet(PooledPickup pickup)
    {
        pickup.InUse = true;
        pickup.Uses++;
        _live.Add(pickup);
        pickup.gameObject.SetActive(true);
    }

    void OnRelease(PooledPickup pickup)
    {
        pickup.InUse = false;
        pickup.Id = "";
        _live.Remove(pickup);

        // Put back what gameplay may have changed. A pickup that was re-parented to the runner
        // would otherwise leave with the runner's scene.
        Transform t = pickup.transform;
        if (t.parent != transform) t.SetParent(transform, false);
        t.localScale = pickup.restScale;
        var body = pickup.GetComponent<Rigidbody>();
        if (body != null && !body.isKinematic)
        {
            body.linearVelocity = Vector3.zero;
            body.angularVelocity = Vector3.zero;
        }
        pickup.gameObject.SetActive(false);
    }

    void OnDestroyItem(PooledPickup pickup)
    {
        Destroyed++;
        if (pickup != null) Destroy(pickup.gameObject);
    }

    void OnDestroy()
    {
        if (_pool != null) _pool.Dispose();
    }
}
