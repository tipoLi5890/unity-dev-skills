// ParallaxTiles.cs — keeps one parallax layer's view covered with tiles, endlessly, from a few
// sprites: a seamless repeat, a mirrored strip, or shuffled props with seeded gaps.
//
// Put it on the same object as ParallaxLayer (which moves the layer by its factor; leave its
// wrapWidth at 0 — this component does the endless part). It pools SpriteRenderer children,
// places tile i where TileSequence says, and recycles tiles that leave the view. Tile i always
// holds the same art at the same layer-local x, so recycling, Snap() and walking back never pop.
//
// Pixel-perfect: when the ParallaxLayer beside it snaps (pixelsPerUnit > 0), every tile edge,
// and gap is rounded to the same 1 / pixelsPerUnit grid; give the sprites that PPU and
// whole-pixel widths, and the layer root snaps the rest (unity-2d-pixel-perfect).
//
// Sprites may have any pivot: tiles are placed by their bounds. The renderers it creates copy the
// sorting layer, order and material set here; children that already exist (the rig builder bakes
// the first view into the prefab) are adopted as the pool.
using System.Collections.Generic;
using UnityEngine;

namespace UnityDev.Rendering2D
{
    // After ParallaxLayer (200), which runs after the Cinemachine Brain (100): the layer has its
    // final position for the frame before the tiles are laid out in its local space.
    [DefaultExecutionOrder(210)]
    public sealed class ParallaxTiles : MonoBehaviour
    {
        [Tooltip("The output camera. Empty means Camera.main.")]
        public Camera outputCamera;

        [Tooltip("The tile sprites. Repeat cycles them, Mirror uses the first, Shuffle draws them from a seeded bag.")]
        public Sprite[] variants = new Sprite[0];

        public ParallaxTiling tiling = ParallaxTiling.Mirror;

        [Tooltip("Seed for the shuffle and the gaps. The same seed always lays out the same strip.")]
        public int seed = 1;

        [Tooltip("Empty space between tiles, world units: x = least, y = most. (0, 0) = tiles touch.")]
        public Vector2 gap = Vector2.zero;

        [Tooltip("Extra world units covered beyond each side of the view.")]
        public float margin = 0.5f;

        public string sortingLayerName = "Default";
        public int sortingOrder;
        [Tooltip("Material for the tile renderers. Empty keeps the renderer's default sprite material.")]
        public Material material;

        readonly Dictionary<int, SpriteRenderer> _active = new Dictionary<int, SpriteRenderer>();
        readonly Stack<SpriteRenderer> _free = new Stack<SpriteRenderer>();
        readonly List<int> _drop = new List<int>();
        TileSequence _sequence;
        Sprite[] _live = new Sprite[0];      // variants without the empty slots, in sequence order
        Material _adoptedMaterial;
        bool _adopted;

        public TileSequence Sequence { get { if (_sequence == null) Rebuild(); return _sequence; } }
        public int ActiveTiles => _active.Count;
        public IEnumerable<KeyValuePair<int, SpriteRenderer>> Tiles => _active;

        /// <summary>Re-read the sprites, mode, seed and gaps. Call after changing any of them.</summary>
        public void Rebuild()
        {
            var live = new List<Sprite>();
            foreach (Sprite s in variants) if (s != null) live.Add(s);
            _live = live.ToArray();
            var widths = new float[_live.Length];
            for (int k = 0; k < _live.Length; k++) widths[k] = _live[k].bounds.size.x;
            _sequence = _live.Length == 0 ? null : new TileSequence(widths, tiling, seed, gap.x, gap.y, Grid());
            foreach (SpriteRenderer r in _active.Values) Release(r);
            _active.Clear();
        }

        void LateUpdate() => Refresh();

        /// <summary>Cover the output camera's view (plus margin).</summary>
        public void Refresh()
        {
            Camera cam = outputCamera != null ? outputCamera : Camera.main;
            if (cam == null) return;
            float half;
            if (cam.orthographic) half = cam.orthographicSize * cam.aspect;
            else
            {
                float depth = Mathf.Abs(transform.position.z - cam.transform.position.z);
                half = depth * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad) * cam.aspect;
            }
            float cx = cam.transform.position.x;
            Refresh(cx - half, cx + half);
        }

        /// <summary>Cover [worldLeft, worldRight] (plus margin): editor baking and tests.</summary>
        public void Refresh(float worldLeft, float worldRight)
        {
            TileSequence seq = Sequence;
            if (seq == null) return;
            if (!_adopted) Adopt();

            float sx = Mathf.Abs(transform.lossyScale.x) > 1e-6f ? transform.lossyScale.x : 1f;
            float a = (worldLeft - margin - transform.position.x) / sx;
            float b = (worldRight + margin - transform.position.x) / sx;
            seq.Range(Mathf.Min(a, b), Mathf.Max(a, b), out int first, out int last);

            _drop.Clear();
            foreach (int i in _active.Keys) if (i < first || i > last) _drop.Add(i);
            foreach (int i in _drop) { Release(_active[i]); _active.Remove(i); }

            for (int i = first; i <= last; i++)
            {
                if (_active.ContainsKey(i)) continue;
                TilePlacement p = seq.At(i);
                Sprite s = _live[p.variant];
                SpriteRenderer r = Take();
                r.sprite = s;
                r.flipX = p.flip;
                Bounds bb = s.bounds;
                // flipX mirrors about the pivot: a flipped tile spans [-max.x, -min.x] around it.
                float lx = p.flip ? p.x + bb.max.x : p.x - bb.min.x;
                r.transform.localPosition = new Vector3(lx, 0f, 0f);
                r.gameObject.name = "tile " + i;
                _active.Add(i, r);
            }
        }

        float Grid()
        {
            var layer = GetComponent<ParallaxLayer>();
            return layer != null && layer.pixelsPerUnit > 0f ? 1f / layer.pixelsPerUnit : 0f;
        }

        // Children already under the layer (a baked first view) become the pool.
        void Adopt()
        {
            _adopted = true;
            foreach (Transform child in transform)
            {
                var r = child.GetComponent<SpriteRenderer>();
                if (r == null || _active.ContainsValue(r)) continue;
                if (_adoptedMaterial == null) _adoptedMaterial = r.sharedMaterial;
                Release(r);
            }
        }

        SpriteRenderer Take()
        {
            SpriteRenderer r = _free.Count > 0 ? _free.Pop() : null;
            if (r == null)
            {
                var go = new GameObject("tile");
                go.transform.SetParent(transform, false);
                r = go.AddComponent<SpriteRenderer>();
            }
            r.sortingLayerName = sortingLayerName;
            r.sortingOrder = sortingOrder;
            Material m = material != null ? material : _adoptedMaterial;
            if (m != null) r.sharedMaterial = m;
            r.gameObject.SetActive(true);
            return r;
        }

        void Release(SpriteRenderer r)
        {
            if (r == null) return;
            r.gameObject.SetActive(false);
            _free.Push(r);
        }

        void OnValidate()
        {
            _sequence = null;
            var layer = GetComponent<ParallaxLayer>();
            if (layer != null && layer.wrapWidth > 0f)
                Debug.LogWarning($"{name}: ParallaxTiles does the endless part; set ParallaxLayer.wrapWidth to 0 or the two wraps fight.", this);
        }
    }
}
