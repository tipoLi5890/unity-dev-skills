// ParallaxTilesTests — EditMode tests for the endless parallax strip: TileSequence is a pure
// function of (seed, index); Shuffle never puts a variant next to itself and uses every variant
// each round; Mirror tiles touch and alternate; gaps stay inside their range; the pixel grid holds;
// and ParallaxTiles covers a view without holes whatever the sprite pivot, recycles its renderers,
// and shows the same art at the same place when the view comes back.
//
// Drop it into an EditMode test assembly that references the assembly holding TileSequence.cs,
// ParallaxTiles.cs and ParallaxLayer.cs. No scene or camera: the tests call Refresh(left, right).
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using UnityEngine;

namespace UnityDev.Rendering2D.Tests
{
    public class ParallaxTilesTests
    {
        const float Eps = 1e-3f;
        readonly List<Object> _made = new List<Object>();

        [TearDown]
        public void TearDown()
        {
            foreach (Object o in _made) if (o != null) Object.DestroyImmediate(o);
            _made.Clear();
        }

        Sprite MakeSprite(int w, int h, float ppu, Vector2 pivot)
        {
            var t = new Texture2D(w, h);
            _made.Add(t);
            var s = Sprite.Create(t, new Rect(0, 0, w, h), pivot, ppu);
            _made.Add(s);
            return s;
        }

        ParallaxTiles MakeStrip(ParallaxTiling tiling, Sprite[] sprites, Vector2 gap, float snapPpu = 0f)
        {
            var go = new GameObject("strip");
            _made.Add(go);
            if (snapPpu > 0f) go.AddComponent<ParallaxLayer>().pixelsPerUnit = snapPpu;
            var tiles = go.AddComponent<ParallaxTiles>();
            tiles.variants = sprites;
            tiles.tiling = tiling;
            tiles.gap = gap;
            tiles.margin = 0f;
            tiles.seed = 7;
            tiles.Rebuild();
            return tiles;
        }

        [Test]
        public void Sequence_IsAPureFunctionOfSeedAndIndex()
        {
            var w = new[] { 1f, 2f, 1.5f, 3f };
            var a = new TileSequence(w, ParallaxTiling.Shuffle, 42, 0.5f, 2f);
            var b = new TileSequence(w, ParallaxTiling.Shuffle, 42, 0.5f, 2f);
            var up = Enumerable.Range(-200, 401).Select(i => b.At(i)).ToList();
            for (int i = 200; i >= -200; i--)        // the order of asking does not matter
            {
                Assert.AreEqual(up[i + 200].variant, a.At(i).variant);
                Assert.AreEqual(up[i + 200].x, a.At(i).x, 1e-6f);
            }
            var c = new TileSequence(w, ParallaxTiling.Shuffle, 43, 0.5f, 2f);
            Assert.IsTrue(Enumerable.Range(0, 40).Any(i => a.At(i).variant != c.At(i).variant), "another seed lays out another strip");
        }

        [Test]
        public void Shuffle_NeverPutsAVariantNextToItself([Values(2, 3, 4, 6)] int n, [Values(1, 99, 12345)] int seed)
        {
            var seq = new TileSequence(Enumerable.Repeat(1f, n).ToArray(), ParallaxTiling.Shuffle, seed);
            for (int i = -300; i < 300; i++)
            {
                Assert.AreNotEqual(seq.At(i).variant, seq.At(i + 1).variant, $"tiles {i} and {i + 1}");
                Assert.IsFalse(seq.At(i).flip, "shuffled tiles are never flipped");
            }
            if (n < 3) return;
            for (int round = -20; round < 20; round++)
            {
                var seen = new HashSet<int>(Enumerable.Range(round * n, n).Select(i => seq.At(i).variant));
                Assert.AreEqual(n, seen.Count, $"round {round} uses every variant once");
            }
        }

        [Test]
        public void Mirror_TilesTouchAndAlternate()
        {
            var seq = new TileSequence(new[] { 10.24f }, ParallaxTiling.Mirror, 5);
            for (int i = -50; i < 50; i++)
            {
                TilePlacement p = seq.At(i), q = seq.At(i + 1);
                Assert.AreEqual(p.x + p.width, q.x, Eps, $"tile {i} meets tile {i + 1}");
                Assert.AreNotEqual(p.flip, q.flip);
            }
        }

        [Test]
        public void Gaps_StayInsideTheirRange_AndTilesNeverOverlap()
        {
            var w = new[] { 1f, 2.5f, 0.75f };
            var seq = new TileSequence(w, ParallaxTiling.Shuffle, 3, 1f, 4f);
            float most = 0f;
            for (int i = -200; i < 200; i++)
            {
                TilePlacement p = seq.At(i), q = seq.At(i + 1);
                float gap = q.x - (p.x + p.width);
                Assert.GreaterOrEqual(gap, 1f - Eps, $"gap after tile {i}");
                Assert.GreaterOrEqual(p.x, i * seq.Pitch - Eps);
                Assert.LessOrEqual(p.x + p.width, (i + 1) * seq.Pitch + Eps, "a tile stays in its slot");
                most = Mathf.Max(most, gap);
            }
            Assert.Greater(most, 2f, "the gaps vary");
        }

        [Test]
        public void PixelGrid_KeepsEveryEdgeOnAWholePixel()
        {
            const float ppu = 16f;
            var seq = new TileSequence(new[] { 37 / ppu, 12 / ppu }, ParallaxTiling.Shuffle, 11, 5 / ppu, 40 / ppu, 1f / ppu);
            for (int i = -100; i < 100; i++)
            {
                float px = seq.At(i).x * ppu;
                Assert.AreEqual(Mathf.Round(px), px, 1e-2f, $"tile {i} at {px} px");
            }
            Assert.AreEqual(Mathf.Round(seq.Pitch * ppu), seq.Pitch * ppu, 1e-3f);
        }

        // The union of the active tiles' world spans, sorted.
        static List<(float min, float max, Sprite s, bool flip)> Spans(ParallaxTiles tiles) =>
            tiles.Tiles.Select(kv => kv.Value).Where(r => r.gameObject.activeSelf)
                .Select(r => (r.bounds.min.x, r.bounds.max.x, r.sprite, r.flipX)).OrderBy(t => t.Item1).ToList();

        [Test]
        public void Mirror_CoversTheViewWithoutHoles_WhateverThePivot([Values(0f, 0.5f, 1f)] float pivotX)
        {
            Sprite s = MakeSprite(64, 32, 32f, new Vector2(pivotX, 0f));      // 2 x 1 world units
            ParallaxTiles tiles = MakeStrip(ParallaxTiling.Mirror, new[] { s }, Vector2.zero);
            tiles.transform.position = new Vector3(0.37f, 0f, 0f);
            tiles.Refresh(-5f, 7f);
            var spans = Spans(tiles);
            Assert.LessOrEqual(spans[0].min, -5f + Eps);
            Assert.GreaterOrEqual(spans[spans.Count - 1].max, 7f - Eps);
            for (int k = 1; k < spans.Count; k++)
            {
                Assert.AreEqual(spans[k - 1].max, spans[k].min, Eps, "no hole and no overlap between tiles");
                Assert.AreNotEqual(spans[k - 1].flip, spans[k].flip, "every other tile is mirrored");
            }
        }

        [Test]
        public void Shuffle_PropsNeverStandNextToTheirOwnCopy()
        {
            var props = new[] { MakeSprite(20, 30, 10f, Vector2.zero), MakeSprite(35, 20, 10f, Vector2.zero), MakeSprite(12, 40, 10f, Vector2.zero) };
            ParallaxTiles tiles = MakeStrip(ParallaxTiling.Shuffle, props, new Vector2(2f, 6f));
            tiles.Refresh(-200f, 200f);
            var spans = Spans(tiles);
            Assert.Greater(spans.Count, 20);
            for (int k = 1; k < spans.Count; k++)
            {
                Assert.AreNotSame(spans[k - 1].s, spans[k].s, $"neighbours {k - 1} and {k}");
                Assert.GreaterOrEqual(spans[k].min - spans[k - 1].max, 2f - Eps, "the least gap holds");
            }
        }

        [Test]
        public void Recycling_KeepsThePoolSmall_AndTheArtWhereItWas()
        {
            Sprite[] props = { MakeSprite(20, 20, 10f, Vector2.zero), MakeSprite(30, 20, 10f, Vector2.zero), MakeSprite(10, 20, 10f, Vector2.zero) };
            ParallaxTiles tiles = MakeStrip(ParallaxTiling.Shuffle, props, new Vector2(1f, 3f));
            tiles.Refresh(0f, 12f);
            var before = tiles.Tiles.ToDictionary(kv => kv.Key, kv => (kv.Value.sprite, kv.Value.transform.position.x));
            int pool = tiles.transform.childCount;
            for (float x = 0f; x < 500f; x += 0.7f) tiles.Refresh(x, x + 12f);
            for (float x = 500f; x > 0f; x -= 0.7f) tiles.Refresh(x, x + 12f);
            tiles.Refresh(0f, 12f);
            Assert.LessOrEqual(tiles.transform.childCount, pool + 2, "renderers are reused, not created per tile");
            var after = tiles.Tiles.ToDictionary(kv => kv.Key, kv => (kv.Value.sprite, kv.Value.transform.position.x));
            CollectionAssert.AreEquivalent(before.Keys, after.Keys);
            foreach (var kv in before)
            {
                Assert.AreSame(kv.Value.sprite, after[kv.Key].sprite, $"tile {kv.Key} shows the same prop");
                Assert.AreEqual(kv.Value.x, after[kv.Key].x, Eps, $"tile {kv.Key} stands in the same place");
            }
        }

        [Test]
        public void PixelSnap_FromTheLayer_PutsTilesOnTheGrid()
        {
            const float ppu = 16f;
            Sprite[] props = { MakeSprite(37, 20, ppu, Vector2.zero), MakeSprite(21, 20, ppu, Vector2.zero) };
            ParallaxTiles tiles = MakeStrip(ParallaxTiling.Shuffle, props, new Vector2(0.3f, 2.2f), ppu);
            tiles.Refresh(-30f, 30f);
            foreach (var kv in tiles.Tiles)
            {
                float px = kv.Value.transform.localPosition.x * ppu;
                Assert.AreEqual(Mathf.Round(px), px, 1e-2f, $"tile {kv.Key}");
            }
        }

        [Test]
        public void Repeat_CyclesVariantsInOrder()
        {
            var seq = new TileSequence(new[] { 1f, 1f, 1f }, ParallaxTiling.Repeat, 0);
            for (int i = -9; i < 9; i++) Assert.AreEqual(((i % 3) + 3) % 3, seq.At(i).variant);
        }
    }
}
