// AttackWindowBehaviour — a window of an Animator state, opened and closed by normalised time.
//
// Drop into a Runtime folder. Add it to a state in the Animator window (Add Behaviour), or from
// an Editor script with state.AddStateMachineBehaviour<AttackWindowBehaviour>(). Put a component
// implementing IAttackWindowReceiver on the GameObject that holds the Animator.
//
// The receiver gets exactly one OnWindowClose for every OnWindowOpen, including when the state
// is left half way through the window. That is the reason this is a StateMachineBehaviour and
// not a pair of AnimationEvents: an event placed at 55% never fires when the state is left at
// 40%, and the hitbox it was meant to switch off stays live.
//
// The window is presentation timing handed to gameplay as a NAMED event. Gameplay still owns
// what the window means: the receiver decides whether a hit lands, and a state that is never
// entered opens nothing.
using UnityEngine;

public interface IAttackWindowReceiver
{
    void OnWindowOpen(string windowId);

    /// <param name="interrupted">True when the state was left, or the Animator went away,
    /// before the close time was reached.</param>
    void OnWindowClose(string windowId, bool interrupted);
}

public sealed class AttackWindowBehaviour : StateMachineBehaviour
{
    [Tooltip("Passed to the receiver, so one receiver can serve several windows.")]
    public string windowId = "strike";

    [Range(0f, 1f)] public float open = 0.25f;
    [Range(0f, 1f)] public float close = 0.55f;

    [Tooltip("Close as soon as a transition OUT of the state starts. Off: close when it ends, " +
             "which is when OnStateExit runs — one cross-fade later.")]
    public bool closeWhenLeaving = true;

    // One instance exists per Animator and per state it sits on, and it is reused on every
    // re-entry — so every field below is reset in OnStateEnter, never assumed fresh.
    IAttackWindowReceiver _receiver;
    bool _open;
    bool _doneThisCycle;
    int _cycle;

    public bool IsOpen => _open;

    public override void OnStateEnter(Animator animator, AnimatorStateInfo stateInfo, int layerIndex)
    {
        // A self-transition re-enters without an exit in between on some graphs; close first so
        // the receiver never sees two opens in a row.
        if (_open) Close(true);
        _receiver = animator.GetComponent<IAttackWindowReceiver>();
        if (_receiver == null)
            Debug.LogWarning("[ANIM] AttackWindowBehaviour '" + windowId + "' on " + animator.name +
                             ": no IAttackWindowReceiver beside the Animator, the window is inert");
        _doneThisCycle = false;
        _cycle = 0;
    }

    public override void OnStateUpdate(Animator animator, AnimatorStateInfo stateInfo, int layerIndex)
    {
        float n = stateInfo.normalizedTime;
        int cycle = stateInfo.loop ? Mathf.FloorToInt(n) : 0;
        float t = stateInfo.loop ? n - cycle : Mathf.Min(n, 1f);

        if (cycle != _cycle)
        {
            if (_open) Close(false);
            _cycle = cycle;
            _doneThisCycle = false;
        }

        // OnStateExit runs when the transition out FINISHES. With a 0.15 s cross-fade into a hurt
        // state that is 0.15 s of live window on a runner who has already been hit.
        // The same test also stops a window OPENING while the state is already fading out.
        if (closeWhenLeaving && animator.IsInTransition(layerIndex)
            && animator.GetNextAnimatorStateInfo(layerIndex).fullPathHash != stateInfo.fullPathHash)
        {
            if (_open) Close(true);
            _doneThisCycle = true;
            return;
        }

        // Compared by ">=" on both edges, so a long frame that jumps over the whole window still
        // opens and closes it, in that order, on the same update.
        if (!_open && !_doneThisCycle && t >= open) Open();
        if (_open && t >= close)
        {
            Close(false);
            _doneThisCycle = true;
        }
    }

    public override void OnStateExit(Animator animator, AnimatorStateInfo stateInfo, int layerIndex)
    {
        if (_open) Close(true);
    }

    // OnStateExit does not run when the Animator goes away mid-window. This instance is
    // destroyed with it, which is the one case OnDisable is certain to cover; whether a plain
    // deactivate reaches here is a check to run on the project's own rig (events-and-windows §5).
    void OnDisable()
    {
        if (_open) Close(true);
    }

    void Open()
    {
        _open = true;
        if (_receiver != null) _receiver.OnWindowOpen(windowId);
    }

    void Close(bool interrupted)
    {
        _open = false;
        // The receiver is a component and may have been destroyed with its GameObject.
        var alive = _receiver as Object;
        if (_receiver != null && alive != null) _receiver.OnWindowClose(windowId, interrupted);
    }
}
