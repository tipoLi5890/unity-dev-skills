// Encode one Sprite — not its whole atlas page — as PNG bytes.
//
// Why it is not two lines: a Sprite is a rect plus a mesh inside a shared
// texture, so GetPixels on the texture gives you the page and EncodeToPNG on
// the page gives you every neighbouring frame. The sprite's own triangles have
// to be drawn somewhere first. That somewhere is a temporary RenderTexture the
// size of the sprite's textureRect, and the drawing is immediate-mode GL with
// the UI material, which composites alpha the way the sprite is displayed.
//
// Editor-side helper: it destroys the material it creates. The source texture is
// bound and drawn, never read back on the CPU, so it does not need Read/Write
// enabled. Before relying on it, compare the PNG for one sprite against that
// sprite in the Sprite Editor.
using UnityEngine;

public static class SpriteToPng
{
    /// <summary>PNG bytes for a single sprite's own pixels. Caller writes the file.</summary>
    public static byte[] Encode(Sprite sprite)
    {
        if (sprite == null) throw new System.ArgumentNullException(nameof(sprite));
        if (sprite.texture == null)
            throw new System.Exception($"{sprite.name} has no source texture — aborted.");

        var frame = sprite.textureRect;
        int w = (int)frame.width, h = (int)frame.height;
        if (w <= 0 || h <= 0)
            throw new System.Exception($"{sprite.name} has an empty textureRect — aborted.");

        // The UI shader is what makes the alpha composite the way the sprite renders.
        var shader = Shader.Find("UI/Default");
        if (shader == null)
            throw new System.Exception("Shader \"UI/Default\" not found — aborted.");

        var target = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.ARGB32,
                                                RenderTextureReadWrite.Default);
        var previous = RenderTexture.active;
        var material = new Material(shader) { mainTexture = sprite.texture };
        Texture2D framed = null;

        try
        {
            RenderTexture.active = target;
            GL.Clear(true, true, Color.clear);

            var verts = sprite.vertices;      // sprite-local units, origin at the pivot
            var uvs   = sprite.uv;
            var tris  = sprite.triangles;

            // Fit the mesh's own bounds to the render target rather than assuming the
            // sprite is centred: a tight-packed sprite's vertices are not symmetric.
            var min = new Vector2(float.MaxValue, float.MaxValue);
            var max = new Vector2(float.MinValue, float.MinValue);
            foreach (var v in verts) { min = Vector2.Min(min, v); max = Vector2.Max(max, v); }
            var span = max - min;
            if (span.x <= 0f || span.y <= 0f)
                throw new System.Exception($"{sprite.name} has a degenerate mesh — aborted.");

            GL.PushMatrix();
            GL.LoadPixelMatrix(0, w, 0, h);
            material.SetPass(0);
            GL.Begin(GL.TRIANGLES);
            for (int i = 0; i < tris.Length; i++)
            {
                int idx = tris[i];
                var v = verts[idx];
                var uv = uvs[idx];
                GL.TexCoord2(uv.x, uv.y);
                GL.Vertex3((v.x - min.x) * w / span.x, (v.y - min.y) * h / span.y, 0f);
            }
            GL.End();
            GL.PopMatrix();

            framed = new Texture2D(w, h, TextureFormat.ARGB32, false);
            framed.ReadPixels(new Rect(0f, 0f, w, h), 0, 0);
            framed.Apply();
            return framed.EncodeToPNG();
        }
        finally
        {
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(target);
            Object.DestroyImmediate(material);
            if (framed != null) Object.DestroyImmediate(framed);
        }
    }
}
