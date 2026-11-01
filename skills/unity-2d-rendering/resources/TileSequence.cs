// TileSequence.cs — which tile goes where along an endless parallax strip, as a pure function of
// (seed, tile index). Plain C#, no scene: ParallaxTiles places renderers from it, and the tests
// check it directly.
//
// Every tile owns one slot of `Pitch` world units: tile i sits in [i * Pitch, (i + 1) * Pitch),
// so tile 0 starts at the layer's origin. What the slot holds never depends on what was placed before,
// so a renderer recycled from the far side, a Snap(), a respawn or walking back the way you came
// all show the same art at the same place.
//
//   Repeat   variants in order, 0 1 2 0 1 2 …        art that tiles at its own width
//   Mirror   variant 0, every odd tile flipped        continuous art that does not tile (sky, road)
//   Shuffle  a seeded shuffle bag: every variant once per round, never the same one twice in a
//            row, nothing flipped. The fix for a props strip whose mirror tiling puts the same
//            prop twice side by side.
//
// Gaps: with gapMax > 0 each slot is the widest variant plus gapMax, and the tile sits at a seeded
// offset inside it, never closer than gapMin to the next one. With gapMax = 0 the slot is the
// widest variant and the tiles touch: give a contiguous strip variants of one width.
using System;
using UnityEngine;

namespace UnityDev.Rendering2D
{
    public enum ParallaxTiling { Repeat, Mirror, Shuffle }

    public struct TilePlacement
    {
        public int index;
        public int variant;
        public bool flip;
        public float x;       // left edge of the tile, layer-local world units
        public float width;
    }

    public sealed class TileSequence
    {
        readonly float[] _widths;
        readonly ParallaxTiling _mode;
        readonly uint _seed;
        readonly float _gapMin, _gapMax, _grid;

        public float Pitch { get; }
        public int VariantCount => _widths.Length;

        /// <param name="widths">World width of each variant, in the order of the sprites.</param>
        /// <param name="grid">World size of one art pixel (1 / pixelsPerUnit) to keep every edge on
        /// the pixel grid; 0 = no rounding.</param>
        public TileSequence(float[] widths, ParallaxTiling mode, int seed, float gapMin = 0f, float gapMax = 0f, float grid = 0f)
        {
            if (widths == null || widths.Length == 0) throw new ArgumentException("at least one variant width");
            float widest = 0f;
            foreach (float w in widths)
            {
                if (!(w > 0f)) throw new ArgumentException("every variant width must be > 0");
                widest = Mathf.Max(widest, w);
            }
            _widths = (float[])widths.Clone();
            _mode = mode;
            _seed = (uint)seed;
            _grid = Mathf.Max(0f, grid);
            _gapMax = Mathf.Max(0f, gapMax);
            _gapMin = Mathf.Clamp(gapMin, 0f, _gapMax);
            Pitch = _grid > 0f ? Mathf.Ceil((widest + _gapMax) / _grid - 1e-3f) * _grid : widest + _gapMax;
        }

        public TilePlacement At(int index)
        {
            int v = Variant(index);
            float w = _widths[v];
            float offset = 0f;
            if (_gapMax > 0f)
            {
                float room = Mathf.Max(0f, Pitch - w - _gapMin);
                offset = Hash01(_seed, 0x51EDu, index) * room;
                if (_grid > 0f) offset = Mathf.Floor(offset / _grid) * _grid;
            }
            return new TilePlacement
            {
                index = index,
                variant = v,
                flip = _mode == ParallaxTiling.Mirror && (index & 1) != 0,
                x = index * Pitch + offset,
                width = w,
            };
        }

        /// <summary>The first and last slot that can touch [left, right] (layer-local units).</summary>
        public void Range(float left, float right, out int first, out int last)
        {
            first = Mathf.FloorToInt(left / Pitch);
            last = Mathf.FloorToInt(right / Pitch);
        }

        int Variant(int index)
        {
            int n = _widths.Length;
            if (n == 1) return 0;
            switch (_mode)
            {
                case ParallaxTiling.Mirror: return 0;
                case ParallaxTiling.Repeat: return Mod(index, n);
            }
            // Shuffle. Two variants can only alternate without repeating.
            if (n == 2) return Mod(index + (int)(_seed & 1u), 2);
            int round = FloorDiv(index, n);
            int[] bag = Bag(round);
            int k = Mod(index, n);
            // The first of a round must not repeat the last of the round before. Swapping
            // positions 0 and 1 leaves position n - 1 alone (n >= 3), so the check never chains.
            if (bag[0] == Bag(round - 1)[n - 1]) { int t = bag[0]; bag[0] = bag[1]; bag[1] = t; }
            return bag[k];
        }

        int[] Bag(int round)
        {
            int n = _widths.Length;
            var bag = new int[n];
            for (int i = 0; i < n; i++) bag[i] = i;
            for (int i = n - 1; i > 0; i--)
            {
                int j = (int)(Hash(_seed, 0xB5u, round * 64 + i) % (uint)(i + 1));
                int t = bag[i]; bag[i] = bag[j]; bag[j] = t;
            }
            return bag;
        }

        static int Mod(int a, int n) { int r = a % n; return r < 0 ? r + n : r; }
        static int FloorDiv(int a, int n) => (a - Mod(a, n)) / n;

        // A small integer hash (lowbias32): the same numbers on every platform and runtime,
        // unlike System.Random, whose sequence is not a promise.
        static uint Hash(uint seed, uint salt, int index)
        {
            uint x = seed * 0x9E3779B9u ^ salt * 0x85EBCA6Bu ^ (uint)index * 0xC2B2AE35u;
            x ^= x >> 16; x *= 0x7FEB352Du;
            x ^= x >> 15; x *= 0x846CA68Bu;
            x ^= x >> 16;
            return x;
        }

        static float Hash01(uint seed, uint salt, int index) => (Hash(seed, salt, index) >> 8) / 16777216f;
    }
}
