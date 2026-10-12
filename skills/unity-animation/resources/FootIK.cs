// FootIK — plants a Humanoid's feet on the ground under them, from two raycasts per frame.
//
// Drop into a Runtime folder and add to the GameObject that holds the Animator. Three things
// must be true or OnAnimatorIK is never called, and nothing warns:
//   - the Avatar is Humanoid (Animator.isHuman);
//   - the layer has IK Pass ticked (AnimatorControllerLayer.iKPass from an Editor script);
//   - this component sits on the same GameObject as the Animator.
//
// The component only reads the pose and the ground. Whether the runner is grounded is the
// game's fact: write `planted` from the same bridge that writes the Animator parameters, so a
// jump releases the feet on the frame the game says so and not when a ray happens to miss.
using UnityEngine;

[RequireComponent(typeof(Animator))]
public sealed class FootIK : MonoBehaviour
{
    [Tooltip("Layers the feet may stand on. Exclude the character's own layer.")]
    public LayerMask groundMask = ~0;

    [Tooltip("The Animator layer whose IK Pass drives this. Other layers are ignored.")]
    public int ikLayer = 0;

    [Tooltip("Written by the game: false while airborne, and the feet go back to the clip.")]
    public bool planted = true;

    [Tooltip("Ray start above the animated foot, in units. About knee height.")]
    public float castUp = 0.5f;

    [Tooltip("How far below the animated foot a step may reach, in units.")]
    public float castDown = 0.45f;

    [Tooltip("Largest distance the hips may sink to let the lower foot reach, in units.")]
    public float maxHipDrop = 0.35f;

    [Tooltip("Seconds for the weight and the hip offset to follow. 0.08-0.15 hides ray noise.")]
    public float smoothTime = 0.1f;

    [Range(0f, 1f)] public float rotationWeight = 0.8f;

    Animator _anim;
    float _weight, _weightVel;
    float _hip, _hipVel;

    void Awake()
    {
        _anim = GetComponent<Animator>();
        if (!_anim.isHuman)
        {
            Debug.LogWarning("[ANIM] FootIK on " + name + ": the Avatar is not Humanoid, " +
                             "OnAnimatorIK is never called for it");
            enabled = false;
        }
    }

    void OnAnimatorIK(int layerIndex)
    {
        if (layerIndex != ikLayer) return;

        _weight = Mathf.SmoothDamp(_weight, planted ? 1f : 0f, ref _weightVel, smoothTime);

        float dropL, dropR;
        bool hitL = Solve(AvatarIKGoal.LeftFoot, _anim.leftFeetBottomHeight, out dropL);
        bool hitR = Solve(AvatarIKGoal.RightFoot, _anim.rightFeetBottomHeight, out dropR);

        // Lower the hips by the deeper of the two reaches, or the leg on the low side has to
        // stretch past its length and the solver leaves the foot floating.
        float wanted = 0f;
        if (planted && (hitL || hitR))
            wanted = Mathf.Clamp(Mathf.Max(hitL ? dropL : 0f, hitR ? dropR : 0f), 0f, maxHipDrop);
        _hip = Mathf.SmoothDamp(_hip, wanted, ref _hipVel, smoothTime);

        // bodyPosition is only writable inside OnAnimatorIK; outside it the write is discarded.
        _anim.bodyPosition += Vector3.down * _hip;
    }

    /// <summary>Sets one foot's goal. Returns false when no ground is within reach; drop is how
    /// far below the character's own ground plane the surface under this foot lies (negative
    /// when it is above).</summary>
    bool Solve(AvatarIKGoal goal, float soleHeight, out float drop)
    {
        drop = 0f;
        Vector3 up = transform.up;
        Vector3 animated = _anim.GetIKPosition(goal);        // the pose the clip asked for
        Vector3 origin = animated + up * castUp;

        RaycastHit hit;
        bool found = Physics.Raycast(origin, -up, out hit, castUp + castDown + soleHeight,
                                     groundMask, QueryTriggerInteraction.Ignore);
        if (!found)
        {
            _anim.SetIKPositionWeight(goal, 0f);
            _anim.SetIKRotationWeight(goal, 0f);
            return false;
        }

        // The goal is the ankle, not the sole: lift it by the rig's own sole height.
        Vector3 target = hit.point + up * soleHeight;
        drop = Vector3.Dot(transform.position - hit.point, up);

        // Keep whatever height the clip gives the foot above its own ground plane, so a stride
        // still lifts the foot instead of dragging it along the surface.
        float lift = Mathf.Max(0f, Vector3.Dot(animated - transform.position, up) - soleHeight);
        target += up * lift;

        Quaternion tilt = Quaternion.FromToRotation(up, hit.normal) * _anim.GetIKRotation(goal);

        _anim.SetIKPositionWeight(goal, _weight);
        _anim.SetIKRotationWeight(goal, _weight * rotationWeight);
        _anim.SetIKPosition(goal, target);
        _anim.SetIKRotation(goal, tilt);
        return true;
    }
}
