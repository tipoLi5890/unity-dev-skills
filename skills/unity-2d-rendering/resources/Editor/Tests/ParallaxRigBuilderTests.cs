// ParallaxRigBuilderTests — EditMode tests for the rig builder: a scene.json (scene_layers.py's
// shape) with an opaque sky and a props layer becomes a prefab whose sky is mirrored and whose
// props are shuffled one prop per tile, with the prop cut by the canvas edge left out, factors =
// 1 - scroll, the foreground in front of the play line, and the first view baked in; the same
// layers read from a PSD land on the same pixels; bad input is refused with a reason instead of a
// half-built rig.
//
// Drop it into an EditMode test assembly that references the editor assembly holding
// ParallaxRigBuilder.cs and the runtime one holding ParallaxLayer.cs and ParallaxTiles.cs. It
// writes under Assets/__ParallaxRigBuilderTest and deletes that folder afterwards.
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace UnityDev.Rendering2D.Tests
{
    public class ParallaxRigBuilderTests
    {
        const string Folder = "Assets/__ParallaxRigBuilderTest";
        const int W = 128, H = 64;

        [SetUp]
        public void SetUp()
        {
            if (!AssetDatabase.IsValidFolder(Folder)) AssetDatabase.CreateFolder("Assets", "__ParallaxRigBuilderTest");
            // Sky: opaque everywhere.
            Png("sky.png", (x, y) => new Color32(90, 140, (byte)(120 + y), 255));
            // Props: two boxes standing apart, and a third cut by the right edge of the canvas.
            Png("props.png", (x, y) =>
                (x >= 20 && x < 36 && y < 20) || (x >= 60 && x < 70 && y < 30) || (x >= 112 && y < 16)
                    ? new Color32(200, 120, 60, 255) : new Color32(0, 0, 0, 0));
        }

        [TearDown]
        public void TearDown() => AssetDatabase.DeleteAsset(Folder);

        static void Png(string name, System.Func<int, int, Color32> paint)
        {
            var t = new Texture2D(W, H, TextureFormat.RGBA32, false);
            var px = new Color32[W * H];
            for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) px[y * W + x] = paint(x, y);
            t.SetPixels32(px);
            File.WriteAllBytes($"{Folder}/{name}", t.EncodeToPNG());
            Object.DestroyImmediate(t);
        }

        static string Json(string body)
        {
            string path = $"{Folder}/scene.json";
            File.WriteAllText(path, body);
            return path;
        }

        // As scene_layers.py writes it, plus the keys the rig reads: scroll, pixels_per_unit, ground_px.
        const string Good = @"{""tool"": ""scene_layers"", ""width"": 128, ""height"": 64, ""order"": ""back_to_front"",
  ""pixels_per_unit"": 32, ""ground_px"": 60,
  ""layers"": [
    {""name"": ""sky"", ""png"": ""sky.png"", ""box"": [0, 0, 128, 64], ""depth"": 0, ""role"": ""strip"", ""tile"": true, ""scroll"": 0.1},
    {""name"": ""props"", ""png"": ""props.png"", ""box"": [20, 34, 128, 64], ""depth"": 1, ""role"": ""props"", ""tile"": false, ""scroll"": 1.3}
  ], ""props"": []}";

        static ParallaxRigBuilder.Options Opt(bool snap = false) => new ParallaxRigBuilder.Options { name = "street", pixelSnap = snap };

        [Test]
        public void Builds_MirroredSky_AndShuffledProps()
        {
            var r = ParallaxRigBuilder.Build(Json(Good), Folder, Opt(snap: true));
            Assert.IsTrue(r.ok, r.error);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(r.prefab);
            Assert.IsNotNull(prefab);
            Assert.AreEqual(2, prefab.transform.childCount);

            Transform sky = prefab.transform.Find("sky"), props = prefab.transform.Find("props");
            var skyTiles = sky.GetComponent<ParallaxTiles>();
            Assert.AreEqual(ParallaxTiling.Mirror, skyTiles.tiling);
            Assert.AreEqual(1, skyTiles.variants.Length);
            Assert.AreEqual(0.9f, sky.GetComponent<ParallaxLayer>().factor.x, 1e-4f);
            Assert.AreEqual(0f, sky.GetComponent<ParallaxLayer>().factor.y, 1e-4f, "no vertical parallax by default");
            Assert.AreEqual(32f, sky.GetComponent<ParallaxLayer>().pixelsPerUnit, "pixel snap on the layer");

            var propTiles = props.GetComponent<ParallaxTiles>();
            Assert.AreEqual(ParallaxTiling.Shuffle, propTiles.tiling);
            Assert.AreEqual(2, propTiles.variants.Length, "one tile per prop; the cut one is left out");
            Assert.AreEqual(1, r.layers[1].droppedEdgeProps);
            Assert.AreEqual(-0.3f, props.GetComponent<ParallaxLayer>().factor.x, 1e-4f, "faster than the world");
            Assert.Greater(propTiles.sortingOrder, 0, "the foreground draws in front of the play line");
            Assert.Less(skyTiles.sortingOrder, 0);
            Assert.AreEqual(-(H - 60) / 32f, sky.localPosition.y, 1e-4f, "the ground row lands on y = 0");

            Assert.Greater(sky.GetComponentsInChildren<SpriteRenderer>(true).Length, 0, "the first view is baked into the prefab");
            var tex = AssetImporter.GetAtPath(r.layers[1].tiles[0]) as TextureImporter;
            Assert.AreEqual(FilterMode.Point, tex.filterMode);
            Assert.AreEqual(32f, tex.spritePixelsPerUnit);
            Assert.AreEqual(16 + 4, propTiles.variants[0].texture.width, "a prop keeps a 2 px margin each side");
        }

        [Test]
        public void Rebuilding_KeepsThePrefabAndRemovesStaleTiles()
        {
            Assert.IsTrue(ParallaxRigBuilder.Build(Json(Good), Folder, Opt()).ok);
            string guid = AssetDatabase.AssetPathToGUID($"{Folder}/street.prefab");
            Png("props.png", (x, y) => x >= 50 && x < 60 && y < 10 ? new Color32(255, 0, 0, 255) : new Color32(0, 0, 0, 0));
            var r = ParallaxRigBuilder.Build(Json(Good), Folder, Opt());
            Assert.IsTrue(r.ok, r.error);
            Assert.AreEqual(guid, AssetDatabase.AssetPathToGUID(r.prefab), "scenes that use the rig keep their reference");
            Assert.IsFalse(File.Exists($"{Folder}/street_tiles/props_1.png"));
        }

        const string Head = @"{""width"": 128, ""height"": 64, ""layers"": ";

        [TestCase(@"[{""name"": ""sky"", ""png"": ""sky.png""}]}", "no scroll")]
        [TestCase(@"[{""name"": ""a"", ""png"": ""sky.png"", ""scroll"": 0.1}, {""name"": ""a"", ""png"": ""props.png"", ""scroll"": 1}]}", "named")]
        [TestCase(@"[{""name"": ""sky"", ""png"": ""nope.png"", ""scroll"": 0.1}]}", "not found")]
        [TestCase(@"[{""name"": ""sky"", ""png"": ""sky.png"", ""scroll"": 0.1, ""tiling"": ""spiral""}]}", "unknown tiling")]
        [TestCase(@"[{""name"": ""sky"", ""png"": ""sky.png"", ""scroll"": 0.1}], ""order"": ""front_to_back""}", "back_to_front")]
        public void RefusesBadInput_WithAReason(string layers, string reason)
        {
            var r = ParallaxRigBuilder.Build(Json(Head + layers), Folder, Opt());
            Assert.IsFalse(r.ok);
            StringAssert.Contains(reason, r.error);
            Assert.IsFalse(File.Exists($"{Folder}/street.prefab"), "no half-built rig");
        }

        [Test]
        public void WrongCanvasSize_IsRefused()
        {
            var r = ParallaxRigBuilder.Build(Json(@"{""width"": 100, ""height"": 64, ""layers"": [{""name"": ""sky"", ""png"": ""sky.png"", ""scroll"": 0.1}]}"), Folder, Opt());
            Assert.IsFalse(r.ok);
            StringAssert.Contains("expected the canvas 100x64", r.error);
        }

        [Test]
        public void ScrollOption_WinsOverTheJson()
        {
            var o = Opt();
            o.scroll["sky"] = 0.25f;
            var r = ParallaxRigBuilder.Build(Json(Good), Folder, o);
            Assert.IsTrue(r.ok, r.error);
            Assert.AreEqual(0.75f, r.layers[0].factorX, 1e-4f);
        }

        // A 32 x 16 PSD written by comfyui-asset-generation psd_write.py: "sky" (opaque, blue rising
        // by one per row from 120 at the bottom) and "props" (three boxes standing on the bottom row
        // at x 4-8, 15-18 and 28-31; the last touches the right edge). Layers are cropped to their box.
        const string Psd =
            "OEJQUwABAAAAAAAAAAQAAAAQAAAAIAAIAAMAAAAAAAAAAAAAA3AAAANoAAIAAAAAAAAAAAAAABAAAAAgAAT//wAAAEIAAAAA" +
            "AEIAAQAAAEIAAgAAAEI4QklNbm9ybf8ACAAAAAA0AAAAAAAAAAADc2t5OEJJTWx1bmkAAAAMAAAAAwBzAGsAeQAAOEJJTWx5" +
            "aWQAAAAEAAAAAgAAAAcAAAAEAAAAEAAAACAABP//AAAAXgAAAAAAXgABAAAAXgACAAAAXjhCSU1ub3Jt/wAIAAAAADwAAAAA" +
            "AAAAAAVwcm9wcwAAOEJJTWx1bmkAAAAQAAAABQBwAHIAbwBwAHMAADhCSU1seWlkAAAABAAAAAMAAQACAAIAAgACAAIAAgAC" +
            "AAIAAgACAAIAAgACAAIAAgAC4f/h/+H/4f/h/+H/4f/h/+H/4f/h/+H/4f/h/+H/4f8AAQACAAIAAgACAAIAAgACAAIAAgAC" +
            "AAIAAgACAAIAAgAC4VrhWuFa4VrhWuFa4VrhWuFa4VrhWuFa4VrhWuFa4VoAAQACAAIAAgACAAIAAgACAAIAAgACAAIAAgAC" +
            "AAIAAgAC4YzhjOGM4YzhjOGM4YzhjOGM4YzhjOGM4YzhjOGM4YwAAQACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgAC" +
            "4YfhhuGF4YThg+GC4YHhgOF/4X7hfeF84XvheuF54XgAAQAGAAYABgAIAAgACgAKAAoACvYA/f/0APYA/f/0APYA/f/0APz/" +
            "+wD9//QA/P/7AP3/9AD8//sA/f/4AP3//P/7AP3/+AD9//z/+wD9//gA/f/8//sA/f/4AP3/AAEABgAGAAYACAAIAAoACgAK" +
            "AAr2AP089AD2AP089AD2AP089AD8yPsA/Tz0APzI+wD9PPQA/Mj7AP08+AD9CvzI+wD9PPgA/Qr8yPsA/Tz4AP0K/Mj7AP08" +
            "+AD9CgABAAYABgAGAAgACAAKAAoACgAK9gD9WvQA9gD9WvQA9gD9WvQA/Hj7AP1a9AD8ePsA/Vr0APx4+wD9WvgA/cj8ePsA" +
            "/Vr4AP3I/Hj7AP1a+AD9yPx4+wD9WvgA/cgAAQAGAAYABgAIAAgACgAKAAoACvYA/cj0APYA/cj0APYA/cj0APw8+wD9yPQA" +
            "/Dz7AP3I9AD8PPsA/cj4AP0K/Dz7AP3I+AD9Cvw8+wD9yPgA/Qr8PPsA/cj4AP0KAAAAAAAAAAEAAgACAAIAAgACAAIAAgAG" +
            "AAYABgAKAAoADAAMAAwADAACAAIAAgACAAIAAgACAAYABgAGAAoACgAMAAwADAAMAAIAAgACAAIAAgACAAIABgAGAAYACgAK" +
            "AAwADAAMAAwAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAuFa4VrhWuFa4VrhWuFa8lr9PPRa8lr9PPRa8lr9PPRa" +
            "/Vr8yPta/Tz0Wv1a/Mj7Wv089Fr9WvzI+1r9PPha/Qr9WvzI+1r9PPha/Qr9WvzI+1r9PPha/Qr9WvzI+1r9PPha/QrhjOGM" +
            "4YzhjOGM4YzhjPKM/Vr0jPKM/Vr0jPKM/Vr0jP2M/Hj7jP1a9Iz9jPx4+4z9WvSM/Yz8ePuM/Vr4jP3I/Yz8ePuM/Vr4jP3I" +
            "/Yz8ePuM/Vr4jP3I/Yz8ePuM/Vr4jP3I4YfhhuGF4YThg+GC4YHygP3I9IDyf/3I9H/yfv3I9H79ffw8+339yPR9/Xz8PPt8" +
            "/cj0fP17/Dz7e/3I+Hv9Cv16/Dz7ev3I+Hr9Cv15/Dz7ef3I+Hn9Cv14/Dz7eP3I+Hj9CuH/4f/h/+H/4f/h/+H/4f/h/+H/" +
            "4f/h/+H/4f/h/+H/";

        [Test]
        public void PsdLayers_LandOnTheSamePixels()
        {
            File.WriteAllBytes($"{Folder}/street.psd", System.Convert.FromBase64String(Psd));
            var r = ParallaxRigBuilder.Build(Json(@"{""width"": 32, ""height"": 16, ""psd"": ""street.psd"", ""layers"": [
                {""name"": ""sky"", ""scroll"": 0.2}, {""name"": ""props"", ""scroll"": 1.2, ""tile"": false}]}"), Folder, Opt());
            Assert.IsTrue(r.ok, r.error);
            Assert.AreEqual("mirror", r.layers[0].tiling);
            Assert.AreEqual("shuffle", r.layers[1].tiling);
            Assert.AreEqual(2, r.layers[1].variants);
            Assert.AreEqual(1, r.layers[1].droppedEdgeProps);

            Color32[] Pixels(string path)
            {
                var t = new Texture2D(2, 2);
                t.LoadImage(File.ReadAllBytes(path));
                Assert.AreEqual(16, t.height);
                var px = t.GetPixels32();
                int w = t.width;
                Object.DestroyImmediate(t);
                return px.Length == w * 16 ? px : null;
            }
            Color32[] sky = Pixels(r.layers[0].tiles[0]);
            Assert.AreEqual(new Color32(90, 140, 120, 255), sky[0], "bottom-left of the sky");
            Assert.AreEqual(new Color32(90, 140, 135, 255), sky[15 * 32], "top-left of the sky");
            Color32[] prop = Pixels(r.layers[1].tiles[0]);              // x 2..10 of the canvas
            Assert.AreEqual(new Color32(200, 120, 60, 255), prop[0 * 9 + 2], "the first box's bottom-left");
            Assert.AreEqual(0, prop[6 * 9 + 2].a, "above the box is empty");
            Assert.AreEqual(255, prop[5 * 9 + 2].a, "the box is six rows tall");
        }
    }
}
