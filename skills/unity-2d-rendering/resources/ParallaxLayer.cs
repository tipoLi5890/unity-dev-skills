// ParallaxLayer.cs — one background or foreground layer that follows a fraction of the
// camera's travel, with an optional endless horizontal wrap and an optional pixel-grid snap.
//
// Drop into any runtime folder and attach to the root of each layer (the object whose
// children are that layer's sprites). One component per layer; the gameplay layer has none.
//
// REQUIRES nothing beyond the engine. No Cinemachine type is referenced: the layer reads the
// output Camera's Transform after every camera driver has written it, so it works with a
// Cinemachine 2.x rig, a 3.x rig and a hand-written follow script alike.
//
//   factor 0      the layer stays in the world: it scrolls past at full speed (gameplay plane)
//   factor 0.5    the layer follows half the camera's travel: it scrolls at half speed
//   factor 1      the layer is locked to the camera: sky, a distant skyline
//   factor < 0    the layer moves against the camera: foreground, faster than the world
//
// Call Snap() in the frame the camera cuts (respawn, room change) so the layer keeps its
// place on screen instead of sliding across it.
using UnityEngine;

// The Cinemachine Brain positions the Camera in LateUpdate at execution order 100. A layer
// that ran before it would read last frame's camera and trail by one frame, which shows as
// a shimmer on every layer whenever the camera accelerates.
[DefaultExecutionOrder(200)]
public sealed class ParallaxLayer : MonoBehaviour
{
    [Tooltip("The output camera. Empty means Camera.main, resolved on the first frame one exists.")]
    public Camera outputCamera;

    [Tooltip("Fraction of the camera's travel this layer follows, per axis. 0 = world, 1 = locked to the camera.")]
    public Vector2 factor = new Vector2(0.5f, 0f);

    [Tooltip("Width in world units after which the art repeats. 0 = no wrap. The layer must be drawn at least one view width plus this value wide.")]
    public float wrapWidth = 0f;

    [Tooltip("Snap the layer to a 1 / pixelsPerUnit world grid. 0 = no snap. Set it to the art's pixels per unit under a pixel-perfect camera.")]
    public float pixelsPerUnit = 0f;

    Transform _cam;
    Vector3 _layerStart;   // where the layer was when the camera was at _camStart
    Vector3 _camStart;
    Vector3 _lastCam;
    float _camToLayerX;    // camera x minus layer x at the start, the centre the wrap holds
    bool _snapPending;

    // Anchors are taken on the first frame a camera exists, not in OnEnable: a scene built
    // from code, or a camera spawned after the level, would otherwise leave the layer inert.
    void OnEnable() { _cam = null; }

    bool Anchor()
    {
        Camera cam = outputCamera != null ? outputCamera : Camera.main;
        if (cam == null) return false;
        _cam = cam.transform;
        _layerStart = transform.position;
        _camStart = _lastCam = _cam.position;
        _camToLayerX = _camStart.x - _layerStart.x;
        _snapPending = false;
        return true;
    }

    /// <summary>
    /// Treat this frame's camera movement as a cut: the layer moves the whole distance with
    /// the camera, whatever its factor. Call it any time before this frame's LateUpdate.
    /// </summary>
    public void Snap() { _snapPending = true; }

    void LateUpdate()
    {
        if (_cam == null && !Anchor()) return;
        Vector3 camPos = _cam.position;

        if (_snapPending)
        {
            // Shift the anchor by the part of the jump the factor would not have followed.
            Vector3 jump = camPos - _lastCam;
            _layerStart.x += jump.x * (1f - factor.x);
            _layerStart.y += jump.y * (1f - factor.y);
            _snapPending = false;
        }
        _lastCam = camPos;

        Vector3 travel = camPos - _camStart;
        Vector3 pos = _layerStart;
        pos.x += travel.x * factor.x;
        pos.y += travel.y * factor.y;

        if (wrapWidth > 0f)
        {
            // How far the camera has drifted from the layer's centre, in whole repeats.
            float drift = (camPos.x - pos.x) - _camToLayerX;
            pos.x += Mathf.Round(drift / wrapWidth) * wrapWidth;
        }

        if (pixelsPerUnit > 0f)
        {
            pos.x = Mathf.Round(pos.x * pixelsPerUnit) / pixelsPerUnit;
            pos.y = Mathf.Round(pos.y * pixelsPerUnit) / pixelsPerUnit;
        }

        transform.position = pos;
    }
}
