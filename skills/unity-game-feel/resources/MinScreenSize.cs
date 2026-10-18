// MinScreenSize.cs — keep a small object (a ball, a puck, a pickup) at least N pixels across on
// one camera, whatever its distance, without growing it past a cap.
//
// Drop into a Runtime assembly. No package needed. Two ways to use it:
//
//   // as a function, from your own LateUpdate after the camera has moved:
//   float d = MinScreenSize.Diameter(cam, ballPos, baseDiameter: 0.067f * 1.6f, minPx: 11f, maxDiameter: 0.067f * 4.2f);
//   ballVisual.localScale = Vector3.one * d;
//
//   // as a component on the visual (a child of the simulated object, never the object itself):
//   MinScreenSize on "BallMesh", camera assigned, baseDiameter 0.107, minPx 11, maxDiameter 0.28
//
// Pixels are counted on a fixed reference height (1080 lines by default), not Screen.height, so the
// object is the same share of the frame at every resolution and in the Editor's Game view. The
// camera's viewport height (rect.height) is included: in a half-height split screen the object is
// sized for that half. Perspective cameras only; an orthographic camera keeps one size anyway.
//
// One transform can have one size. With two cameras (split screen) give each camera its own copy
// of the visual on a layer only that camera draws, each with its own MinScreenSize.
//
// The visual's mesh is assumed one unit across (Unity's sphere primitive is). Scale only the
// visual. Colliders and the simulation keep the real size, or the game changes.
using UnityEngine;

[DefaultExecutionOrder(1000)]   // after camera rigs that move in LateUpdate at the default order
public sealed class MinScreenSize : MonoBehaviour
{
    [Tooltip("The camera this visual is drawn by.")]
    public Camera cam;
    [Tooltip("Diameter in world units when close: real size times any constant display scale.")]
    public float baseDiameter = 0.1f;
    [Tooltip("Never smaller than this many pixels on the reference height.")]
    public float minPx = 11f;
    [Tooltip("Never larger than this in world units, so a far object does not become a beach ball.")]
    public float maxDiameter = 0.3f;
    [Tooltip("Reference screen height in pixels.")]
    public float referenceHeight = 1080f;

    /// <summary>The world-space diameter after the pixel floor and the cap, for this camera.</summary>
    public static float Diameter(Camera cam, Vector3 worldPos, float baseDiameter, float minPx,
                                 float maxDiameter, float referenceHeight = 1080f)
    {
        if (cam == null || cam.orthographic) return baseDiameter;
        float dist = Vector3.Distance(cam.transform.position, worldPos);
        return Mathf.Clamp(minPx * WorldPerPixel(cam, dist, referenceHeight), baseDiameter,
                           Mathf.Max(baseDiameter, maxDiameter));
    }

    /// <summary>World units covered by one reference pixel at this distance from this camera.</summary>
    public static float WorldPerPixel(Camera cam, float distance, float referenceHeight = 1080f)
    {
        float halfFov = cam.fieldOfView * 0.5f * Mathf.Deg2Rad;
        return 2f * distance * Mathf.Tan(halfFov) / (referenceHeight * Mathf.Max(0.1f, cam.rect.height));
    }

    /// <summary>Pixels across on the reference height for an object of this diameter.</summary>
    public static float PixelsAcross(Camera cam, Vector3 worldPos, float diameter, float referenceHeight = 1080f)
    {
        if (cam == null) return 0f;
        float dist = Vector3.Distance(cam.transform.position, worldPos);
        return diameter / Mathf.Max(1e-6f, WorldPerPixel(cam, dist, referenceHeight));
    }

    void LateUpdate()
    {
        if (cam == null) return;
        float d = Diameter(cam, transform.position, baseDiameter, minPx, maxDiameter, referenceHeight);
        // The visual is a child: undo the parent's scale so d is the world diameter.
        var parentScale = transform.parent != null ? transform.parent.lossyScale.x : 1f;
        transform.localScale = Vector3.one * (d / Mathf.Max(1e-6f, parentScale));
    }
}
