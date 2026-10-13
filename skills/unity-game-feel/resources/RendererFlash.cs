// RendererFlash.cs — flash a character's renderers one colour for a few frames and put back
// exactly what was there, whatever interrupts it.
//
// Drop into a Runtime assembly. No package needed. Add it to the root of the thing that
// flashes; with no renderers assigned it takes every Renderer under it.
//
//   flash.Flash();                              // the configured colour and time
//   flash.Flash(Color.red, 0.12f, 0.4f);        // 40 % of the way to red: a softened flash
//
// Three ways to do it, and the choice is a cost:
//   PropertyBlock  one colour property through a MaterialPropertyBlock. No material is created.
//                  A renderer that carries a property block is not batched by the SRP Batcher
//                  while it carries one, so this is for a handful of objects for a few frames.
//   MaterialSwap   every material replaced by flashMaterial, then the originals put back. All
//                  flashing objects share one material and batch together: use it for a crowd,
//                  and for a sprite that must turn solid white (a tint can only darken).
//   SpriteTint     SpriteRenderer.color. Free, and limited to multiplying: red, never white.
//
// What it restores is captured when a flash starts from rest, never when one is already
// showing — a flash that captures a flashing renderer keeps the flash colour for good.
using System.Collections.Generic;
using UnityEngine;

public enum FlashMode { PropertyBlock, MaterialSwap, SpriteTint }

[AddComponentMenu("Courier/Renderer Flash")]
public sealed class RendererFlash : MonoBehaviour
{
    [Tooltip("Empty: every Renderer under this object, found once in Awake.")]
    public Renderer[] renderers;
    public FlashMode mode = FlashMode.PropertyBlock;
    public Color colour = Color.white;
    [Tooltip("Seconds. 0.08 is five frames at 60: long enough to see, short enough to read as a hit.")]
    public float seconds = 0.08f;
    [Tooltip("PropertyBlock mode. _BaseColor on URP Lit and Unlit; a material without it falls back to _Color.")]
    public string colourProperty = "_BaseColor";
    [Tooltip("MaterialSwap mode: an unlit material of the flash colour. Its shader must draw the sprite's or mesh's shape.")]
    public Material flashMaterial;
    [Tooltip("On: the flash ends on time during a hit stop. Off: it is held for as long as time is.")]
    public bool unscaledTime = true;

    static readonly int FallbackColour = Shader.PropertyToID("_Color");

    MaterialPropertyBlock[] _saved;
    bool[] _hadBlock;
    int[] _propertyId;
    Color[] _spriteColour;
    List<Material>[] _materials;
    readonly List<Material> _swap = new List<Material>();
    MaterialPropertyBlock _work;
    bool _flashing;
    float _until;

    public bool IsFlashing => _flashing;

    /// <summary>Flashes started from rest; one that extends a showing flash is not counted.</summary>
    public int Flashes { get; private set; }

    void Awake() => Collect();

    /// <summary>Call after assigning <see cref="renderers"/> from code, or after the hierarchy under this object changed.</summary>
    public void Collect()
    {
        if (_flashing) Restore();
        if (renderers == null || renderers.Length == 0) renderers = GetComponentsInChildren<Renderer>(true);
        int n = renderers.Length;
        _saved = new MaterialPropertyBlock[n];
        _hadBlock = new bool[n];
        _propertyId = new int[n];
        _spriteColour = new Color[n];
        _materials = new List<Material>[n];
        for (int i = 0; i < n; i++)
        {
            _saved[i] = new MaterialPropertyBlock();
            _materials[i] = new List<Material>(2);
        }
        if (_work == null) _work = new MaterialPropertyBlock();
    }

    public void Flash() => Flash(colour, seconds, 1f);

    /// <summary>
    /// <paramref name="strength"/> 1 shows the colour itself; under 1 blends from the renderer's
    /// own colour towards it, which is how a reduce-flash setting softens every flash at once.
    /// 0 does nothing. MaterialSwap cannot blend: it shows the flash material or nothing.
    /// </summary>
    public void Flash(Color flashColour, float duration, float strength = 1f)
    {
        if (!isActiveAndEnabled || duration <= 0f || strength <= 0f) return;
        if (_saved == null) Collect();
        if (!_flashing)
        {
            Capture();
            Flashes++;
        }
        Show(flashColour, Mathf.Clamp01(strength));
        _flashing = true;
        float until = Now + duration;
        if (until > _until) _until = until;      // a second flash extends; it never shortens
    }

    /// <summary>End the flash now and put the original look back.</summary>
    public void Cancel()
    {
        if (_flashing) Restore();
    }

    float Now => unscaledTime ? Time.unscaledTime : Time.time;

    void Update()
    {
        if (_flashing && Now >= _until) Restore();
    }

    // A pooled object is disabled mid-flash and handed out again: it must come back clean.
    void OnDisable()
    {
        if (_flashing) Restore();
    }

    // The colour property the flash writes on this renderer — what a test reads back.
    public int PropertyIdFor(Renderer r)
    {
        int id = Shader.PropertyToID(colourProperty);
        Material m = r != null ? r.sharedMaterial : null;
        if (m != null && !m.HasColor(id) && m.HasColor(FallbackColour)) return FallbackColour;
        return id;
    }

    void Capture()
    {
        for (int i = 0; i < renderers.Length; i++)
        {
            Renderer r = renderers[i];
            if (r == null) continue;
            switch (mode)
            {
                case FlashMode.PropertyBlock:
                    _propertyId[i] = PropertyIdFor(r);
                    _hadBlock[i] = r.HasPropertyBlock();
                    if (_hadBlock[i]) r.GetPropertyBlock(_saved[i]);
                    break;
                case FlashMode.MaterialSwap:
                    r.GetSharedMaterials(_materials[i]);
                    break;
                case FlashMode.SpriteTint:
                    if (r is SpriteRenderer sprite) _spriteColour[i] = sprite.color;
                    break;
            }
        }
    }

    void Show(Color flashColour, float strength)
    {
        for (int i = 0; i < renderers.Length; i++)
        {
            Renderer r = renderers[i];
            if (r == null) continue;
            switch (mode)
            {
                case FlashMode.PropertyBlock:
                {
                    // Start from the block that was there, so a per-instance tint or a texture
                    // offset set by someone else survives the flash.
                    if (_hadBlock[i]) r.GetPropertyBlock(_work); else _work.Clear();
                    Color rest = RestColour(r, i);
                    _work.SetColor(_propertyId[i], Color.Lerp(rest, flashColour, strength));
                    r.SetPropertyBlock(_work);
                    break;
                }
                case FlashMode.MaterialSwap:
                {
                    if (flashMaterial == null) break;
                    _swap.Clear();
                    for (int k = 0; k < _materials[i].Count; k++) _swap.Add(flashMaterial);
                    r.SetSharedMaterials(_swap);
                    break;
                }
                case FlashMode.SpriteTint:
                    if (r is SpriteRenderer sprite) sprite.color = Color.Lerp(_spriteColour[i], flashColour, strength);
                    break;
            }
        }
    }

    Color RestColour(Renderer r, int i)
    {
        int id = _propertyId[i];
        if (_hadBlock[i] && _saved[i].HasColor(id)) return _saved[i].GetColor(id);
        Material m = r.sharedMaterial;
        return m != null && m.HasColor(id) ? m.GetColor(id) : Color.white;
    }

    void Restore()
    {
        _flashing = false;
        _until = 0f;
        if (renderers == null) return;
        for (int i = 0; i < renderers.Length; i++)
        {
            Renderer r = renderers[i];
            if (r == null) continue;
            switch (mode)
            {
                case FlashMode.PropertyBlock:
                    // null removes the block: the renderer is batched again, which a block
                    // holding the original colour would not give back.
                    r.SetPropertyBlock(_hadBlock[i] ? _saved[i] : null);
                    break;
                case FlashMode.MaterialSwap:
                    if (_materials[i].Count > 0) r.SetSharedMaterials(_materials[i]);
                    break;
                case FlashMode.SpriteTint:
                    if (r is SpriteRenderer sprite) sprite.color = _spriteColour[i];
                    break;
            }
        }
    }
}
