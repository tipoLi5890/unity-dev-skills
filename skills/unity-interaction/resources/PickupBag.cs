// PickupBag.cs — the smallest inventory that works: counts by item id. It is what a Pickup
// (Pickup.cs) is handed to, and what a locked gate asks for a key.
//
// Drop into the same Runtime assembly as Pickup.cs and IInteractable.cs. Add PickupBag to the
// runner. No package needed.
//
// Register with the probe where the game wires its harness:
//   GameProbe.Count("parcels", () => bag.CountOf("parcel"));
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Counts by item id. An inventory with slots, stacks and weights replaces this class and keeps
/// the two interfaces; nothing else in the game knows the difference.
/// </summary>
[DisallowMultipleComponent]
[AddComponentMenu("Courier/Pickup Bag")]
public sealed class PickupBag : MonoBehaviour, IPickupReceiver, IKeyHolder
{
    [Tooltip("Most of any one item the bag holds. 0 is no limit.")]
    public int capacityPerItem = 0;

    /// <summary>(itemId, new count). The HUD redraws on this, not every frame.</summary>
    public event Action<string, int> Changed;

    static readonly List<PickupBag> s_Bags = new List<PickupBag>();
    readonly Dictionary<string, int> _counts = new Dictionary<string, int>();

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics() => s_Bags.Clear();

    void OnEnable() => s_Bags.Add(this);
    void OnDisable() => s_Bags.Remove(this);

    /// <summary>The enabled bag closest to a point and within a radius, or null.</summary>
    public static PickupBag Nearest(Vector3 point, float radius)
    {
        PickupBag best = null;
        float bestSqr = radius * radius;
        for (int i = 0; i < s_Bags.Count; i++)
        {
            float sqr = (s_Bags[i].transform.position - point).sqrMagnitude;
            if (sqr > bestSqr) continue;
            bestSqr = sqr;
            best = s_Bags[i];
        }
        return best;
    }

    public int CountOf(string itemId) => _counts.TryGetValue(itemId, out int n) ? n : 0;

    public bool Receive(string itemId, int amount)
    {
        if (string.IsNullOrEmpty(itemId) || amount <= 0) return false;
        int have = CountOf(itemId);
        if (capacityPerItem > 0 && have + amount > capacityPerItem) return false;
        Set(itemId, have + amount);
        return true;
    }

    public bool Remove(string itemId, int amount)
    {
        int have = CountOf(itemId);
        if (amount <= 0 || have < amount) return false;
        Set(itemId, have - amount);
        return true;
    }

    public bool HasKey(string keyId) => CountOf(keyId) > 0;
    public bool UseKey(string keyId) => Remove(keyId, 1);

    /// <summary>For the save: write these pairs out, and feed them back through <see cref="Set"/> on load.</summary>
    public IEnumerable<KeyValuePair<string, int>> Items => _counts;

    public void Set(string itemId, int count)
    {
        if (count <= 0) _counts.Remove(itemId);
        else _counts[itemId] = count;
        Changed?.Invoke(itemId, Mathf.Max(0, count));
    }
}
