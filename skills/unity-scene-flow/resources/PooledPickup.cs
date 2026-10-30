// PooledPickup.cs — marks an instance as PickupObjectPool's and carries what the pool needs to
// take it back. The pool adds it to each instance it makes; it lives in the same Runtime assembly
// as PickupObjectPool.cs.
using UnityEngine;

/// <summary>Marks an instance as the pool's, and carries what the pool needs to take it back.</summary>
[DisallowMultipleComponent]
public sealed class PooledPickup : MonoBehaviour
{
    /// <summary>The id the spawn data gave this use of the instance — what the save records.</summary>
    public string Id { get; internal set; } = "";

    /// <summary>True between Spawn and Despawn.</summary>
    public bool InUse { get; internal set; }

    /// <summary>How many times this instance has been handed out. 2 or more is the pool working.</summary>
    public int Uses { get; internal set; }

    internal PickupObjectPool owner;
    internal Vector3 restScale = Vector3.one;

    /// <summary>Return to the pool. Safe to call twice: the second call does nothing.</summary>
    public void Release()
    {
        if (owner != null) owner.Despawn(this);
    }
}
