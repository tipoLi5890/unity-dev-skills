// Supplies sprite atlases on demand at runtime.
//
// The third of the three pieces late binding needs. Put it on an object in the first scene that
// survives scene loads. Without it, every atlas built with includeInBuild = false is missing and
// the sprites that lived in it draw nothing — with no error anywhere.
//
// Timing is the whole game here. SpriteAtlasManager.atlasRequested fires once, when a sprite first
// needs its atlas, and the request is not retried. Subscribing in Awake on a DontDestroyOnLoad
// object is early enough; subscribing in Start, or from a component the second scene creates, is
// not — those sprites stay unbound for the session.
//
// SpriteAtlasManager declares exactly two static events, atlasRequested and atlasRegistered,
// plus CreateSpriteAtlas. Addressables supplies LoadAssetAsync and Release on
// UnityEngine.AddressableAssets.Addressables.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.U2D;

#if UNITY_ADDRESSABLES
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;
#endif

[DisallowMultipleComponent]
public sealed class AtlasSupplier : MonoBehaviour
{
    static AtlasSupplier _instance;

#if UNITY_ADDRESSABLES
    readonly Dictionary<string, AsyncOperationHandle<SpriteAtlas>> _handles =
        new Dictionary<string, AsyncOperationHandle<SpriteAtlas>>();
#endif

    void Awake()
    {
        if (_instance != null && _instance != this)
        {
            Destroy(gameObject);
            return;
        }

        _instance = this;
        DontDestroyOnLoad(gameObject);

        SpriteAtlasManager.atlasRequested  += OnAtlasRequested;
        SpriteAtlasManager.atlasRegistered += OnAtlasRegistered;
    }

    void OnDestroy()
    {
        if (_instance != this) return;

        SpriteAtlasManager.atlasRequested  -= OnAtlasRequested;
        SpriteAtlasManager.atlasRegistered -= OnAtlasRegistered;
        _instance = null;

#if UNITY_ADDRESSABLES
        // Unsubscribing without releasing leaks the atlas textures for the rest of the process.
        foreach (var handle in _handles.Values)
            if (handle.IsValid()) Addressables.Release(handle);
        _handles.Clear();
#endif
    }

    /// <summary>
    /// The tag is the atlas name the prebuild step used as its Addressables address, so it is
    /// also the key here — no mapping asset to keep in sync.
    /// </summary>
    void OnAtlasRequested(string tag, Action<SpriteAtlas> reply)
    {
#if UNITY_ADDRESSABLES
        if (_handles.TryGetValue(tag, out var known))
        {
            // Already loaded: answer now. Already loading: chain onto the same handle rather than
            // starting a second load of the same bundle.
            if (known.IsDone) { reply(known.Status == AsyncOperationStatus.Succeeded ? known.Result : null); }
            else              { known.Completed += op => reply(op.Status == AsyncOperationStatus.Succeeded ? op.Result : null); }
            return;
        }

        var handle = Addressables.LoadAssetAsync<SpriteAtlas>(tag);
        _handles[tag] = handle;
        handle.Completed += op =>
        {
            if (op.Status == AsyncOperationStatus.Succeeded)
            {
                reply(op.Result);
            }
            else
            {
                Debug.LogError($"[atlas] could not load '{tag}' — sprites from it will not draw.");
                reply(null);   // answer even on failure; the request is never repeated
            }
        };
#else
        Debug.LogError($"[atlas] '{tag}' was requested but Addressables is not available in this build.");
        reply(null);
#endif
    }

    void OnAtlasRegistered(SpriteAtlas atlas)
    {
        Debug.Log($"[atlas] bound {atlas.tag} ({atlas.spriteCount} sprites)");
    }

    /// <summary>
    /// Optional: pull an atlas in before anything asks for it, to keep the first frame that uses
    /// it from popping. Safe to call more than once per tag.
    /// </summary>
    public static void Preload(string tag)
    {
#if UNITY_ADDRESSABLES
        if (_instance == null)
        {
            Debug.LogError("[atlas] no AtlasSupplier in the scene — nothing to preload into.");
            return;
        }

        if (!_instance._handles.ContainsKey(tag))
            _instance._handles[tag] = Addressables.LoadAssetAsync<SpriteAtlas>(tag);
#endif
    }
}
