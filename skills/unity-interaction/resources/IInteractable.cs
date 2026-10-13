// IInteractable — the contract every usable thing implements, the base class most of them derive
// from, and the half of an interactor that is the same in 2D and 3D: one selected target, scored
// and held with hysteresis, one press spent on it, an optional hold.
//
// Drop into a Runtime assembly beside RunInput.cs (skill unity-input → resources/). No package
// needed. Interactor2D.cs and Interactor3D.cs derive from InteractorBase here and add only the
// detection; Pickup.cs and GateSwitch.cs derive from InteractableBase.
//
// The split it exists to enforce:
//   the interactor   knows who is in reach and which one is selected; it never changes the world
//   the interactable knows what using it means, and refuses on its own when it is not allowed
//
// Register with the probe where the game wires its harness:
//   GameProbe.Register("target", () => interactor.TargetName);
//   GameProbe.Count("interactions", () => interactor.Interactions);
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Events;

public interface IInteractable
{
    /// <summary>May this actor use it now? Cheap and free of side effects: it is asked every scan.</summary>
    bool CanInteract(GameObject actor);

    /// <summary>
    /// Use it. Called on every press aimed at it, allowed or not: the implementation checks
    /// <see cref="CanInteract"/> itself and treats a call it does not allow as a refusal.
    /// </summary>
    void Interact(GameObject actor);

    /// <summary>The verb for the prompt, or a localisation key. Empty hides the prompt.</summary>
    string Prompt { get; }

    /// <summary>Higher wins over anything geometry can say. 0 for almost everything.</summary>
    int Priority { get; }

    /// <summary>Seconds the press must be sustained. 0 is a tap.</summary>
    float HoldSeconds { get; }

    /// <summary>Where the prompt sits and what line of sight is tested against. Null means the collider.</summary>
    Transform Anchor { get; }
}

/// <summary>Anything that can show it carries a key: an inventory, a bag, a test double.</summary>
public interface IKeyHolder
{
    bool HasKey(string keyId);
    /// <summary>Spend one. False when there is none.</summary>
    bool UseKey(string keyId);
}

/// <summary>
/// The base most interactables derive from. It owns the guard — enabled, cooled down, allowed —
/// so a second press, a second interactor or a replayed command cannot fire the effect twice.
/// </summary>
public abstract class InteractableBase : MonoBehaviour, IInteractable
{
    [Header("Interactable")]
    [Tooltip("The verb shown in the prompt, or a localisation key.")]
    public string prompt = "Use";
    [Tooltip("Higher wins the selection outright. Leave 0 unless two things overlap by design.")]
    public int priority = 0;
    [Tooltip("Seconds the press must be sustained. 0 is a tap.")]
    public float holdSeconds = 0f;
    [Tooltip("Seconds after a use during which it refuses. Stops a double press.")]
    public float cooldownSeconds = 0.25f;
    [Tooltip("Where the prompt sits and what line of sight is tested against. Empty means this transform.")]
    public Transform anchor;

    [Header("Events out — audio, feel, UI. Nothing in here changes game state.")]
    public UnityEvent onInteracted;
    public UnityEvent onRefused;

    /// <summary>Raised after the state change, with the actor.</summary>
    public event Action<GameObject> Interacted;
    /// <summary>Raised when a press was aimed at it and it did not allow it.</summary>
    public event Action<GameObject> Refused;

    /// <summary>How many times the effect ran. A probe count.</summary>
    public int Uses { get; private set; }

    float _readyAt;

    public virtual string Prompt => prompt;
    public int Priority => priority;
    public float HoldSeconds => holdSeconds;
    public Transform Anchor => anchor != null ? anchor : transform;

    public bool CanInteract(GameObject actor)
        => isActiveAndEnabled && Time.time >= _readyAt && Allows(actor);

    public void Interact(GameObject actor)
    {
        if (!CanInteract(actor) || !OnInteract(actor))
        {
            onRefused?.Invoke();
            Refused?.Invoke(actor);
            return;
        }
        _readyAt = Time.time + cooldownSeconds;
        Uses++;
        onInteracted?.Invoke();
        Interacted?.Invoke(actor);
    }

    /// <summary>The rule of this interactable: locked, already used, busy. No side effects.</summary>
    protected virtual bool Allows(GameObject actor) => true;

    /// <summary>Change the state. Return false when nothing happened, and the press counts as refused.</summary>
    protected abstract bool OnInteract(GameObject actor);
}

/// <summary>One thing in reach, as the detection reports it.</summary>
public struct InteractionCandidate
{
    public IInteractable target;
    /// <summary>From the actor to the nearest point of the target, in units.</summary>
    public float distance;
    /// <summary>Degrees off the facing. 0 when the detection has no facing.</summary>
    public float angle;
}

/// <summary>
/// Selection, press and hold. A subclass fills <see cref="Gather"/> and nothing else. It reads
/// <see cref="IRunInputSource"/> on its own GameObject in FixedUpdate and never a device.
/// </summary>
public abstract class InteractorBase : MonoBehaviour
{
    [Header("Reach")]
    [Tooltip("Units from the actor to the nearest point of the target.")]
    public float range = 2f;
    [Tooltip("The selected target is kept out to range × this, so it does not blink at the rim.")]
    public float keepRangeFactor = 1.15f;
    [Tooltip("Degrees past the cone at which the selected target is still kept.")]
    public float keepAngleMargin = 10f;

    [Header("Selection")]
    [Tooltip("Seconds between scans. 0 scans every fixed step.")]
    public float scanInterval = 0.1f;
    [Tooltip("Score a challenger must win by to take the selection. 0 lets two equal targets flicker.")]
    public float switchMargin = 0.15f;
    [Tooltip("Weight of 'in front' against 'near'. Distance has weight 1.")]
    public float angleWeight = 0.5f;
    [Tooltip("Score per priority step. Above 1.5 a step outranks any distance and angle.")]
    public float priorityWeight = 2f;
    [Tooltip("Score taken from a target that would refuse, so a usable one next to it wins.")]
    public float unavailablePenalty = 1f;

    [Header("Press")]
    [Tooltip("Spend RunButton.Interact from the RunInputSource on this object. Off when something else calls TryInteract.")]
    public bool readInput = true;
    [Tooltip("A hold is abandoned when the move input exceeds this. 1 or more never cancels on movement.")]
    public float holdCancelMove = 0.5f;

    /// <summary>
    /// Is the interact control still down? Unassigned, a hold is a channel: the press starts it,
    /// it finishes by itself, and movement, a lost target or a second press cancels it. Assign
    /// it when the game's input exposes a held level, and letting go cancels as well.
    /// </summary>
    public Func<bool> Held;

    /// <summary>(previous, current). Either may be null. The prompt listens to this.</summary>
    public event Action<IInteractable, IInteractable> TargetChanged;
    /// <summary>A press was delivered to a target that ran its effect.</summary>
    public event Action<IInteractable> Interacted;
    /// <summary>A press was delivered to a target that refused it.</summary>
    public event Action<IInteractable> Refused;
    public event Action<IInteractable> HoldStarted;
    public event Action<IInteractable> HoldCancelled;

    /// <summary>The one selected target, or null.</summary>
    public IInteractable Target { get; private set; }
    /// <summary>The selected target's object name, or "" — a probe value.</summary>
    public string TargetName
    {
        get
        {
            if (!Alive(Target)) return "";
            var c = Target as Component;
            return c != null ? c.name : Target.GetType().Name;
        }
    }
    /// <summary>What CanInteract said at the last scan. The prompt dims or hides on false.</summary>
    public bool TargetAvailable { get; private set; }
    /// <summary>0..1 while a hold is running, else 0.</summary>
    public float HoldProgress { get; private set; }
    public bool Holding => _holding != null;
    /// <summary>Presses delivered to a target that ran its effect.</summary>
    public int Interactions { get; private set; }
    /// <summary>Presses delivered to a target that refused them, before or inside its effect (a full bag).</summary>
    public int Refusals { get; private set; }
    /// <summary>How many times the selection changed. A flicker shows up here.</summary>
    public int TargetChanges { get; private set; }

    readonly List<InteractionCandidate> _candidates = new List<InteractionCandidate>(8);
    IRunInputSource _input;
    IInteractable _holding;
    float _heldFor;
    float _nextScan;

    /// <summary>Degrees either side of the facing. 180 or more means no cone.</summary>
    protected abstract float HalfAngle { get; }
    /// <summary>False when the detection's own volume is the range (a trigger sensor).</summary>
    protected virtual bool GateByRange => true;
    /// <summary>Report everything in reach out to <see cref="KeepRange"/>. Use <see cref="Add"/>.</summary>
    protected abstract void Gather(List<InteractionCandidate> into);

    /// <summary>How far a subclass has to look so the kept target is still reported.</summary>
    protected float KeepRange => range * Mathf.Max(1f, keepRangeFactor);

    /// <summary>Add a candidate, keeping the nearest report when one target has several colliders.</summary>
    protected static void Add(List<InteractionCandidate> into, IInteractable target, float distance, float angle)
    {
        if (!Alive(target)) return;
        for (int i = 0; i < into.Count; i++)
        {
            if (!ReferenceEquals(into[i].target, target)) continue;
            if (distance < into[i].distance)
                into[i] = new InteractionCandidate { target = target, distance = distance, angle = angle };
            return;
        }
        into.Add(new InteractionCandidate { target = target, distance = distance, angle = angle });
    }

    /// <summary>A destroyed component still compares unequal to null through an interface.</summary>
    protected static bool Alive(IInteractable target)
    {
        if (target == null) return false;
        var o = target as UnityEngine.Object;
        return !(target is UnityEngine.Object) || o != null;
    }

    protected virtual void OnDisable()
    {
        CancelHold();
        SetTarget(null);
    }

    void FixedUpdate()
    {
        // A target destroyed or pooled between scans is dropped on the step it happens.
        if (Time.time >= _nextScan || (Target != null && !Alive(Target)))
        {
            _nextScan = Time.time + scanInterval;
            Scan();
        }

        IRunInputSource input = null;
        if (readInput && RunInputSource.Resolve(gameObject, ref _input)) input = _input;

        if (_holding != null)
        {
            StepHold(input);
            return;
        }

        // Condition first, then TryUse: a press made a moment before the target came into reach
        // is still honoured, and a press with nothing selected ages out in the source's buffer.
        if (Target != null && input != null && input.TryUse(RunButton.Interact)) Press();
    }

    /// <summary>
    /// Press on the selected target, for callers that do not go through RunInput: a hotspot
    /// queue, a sentry, a UI button. False when nothing is selected.
    /// </summary>
    public bool TryInteract()
    {
        if (!Alive(Target) || _holding != null) return false;
        Press();
        return true;
    }

    /// <summary>Run a scan now — after a teleport, or when a cutscene hands control back.</summary>
    public void Rescan()
    {
        _nextScan = Time.time + scanInterval;
        Scan();
    }

    public void CancelHold()
    {
        if (_holding == null) return;
        IInteractable was = _holding;
        _holding = null;
        _heldFor = 0f;
        HoldProgress = 0f;
        HoldCancelled?.Invoke(was);
    }

    void Press()
    {
        IInteractable target = Target;
        bool allowed = target.CanInteract(gameObject);
        if (allowed && target.HoldSeconds > 0f)
        {
            _holding = target;
            _heldFor = 0f;
            HoldProgress = 0f;
            HoldStarted?.Invoke(target);
            return;
        }
        Deliver(target, allowed);
    }

    void StepHold(IRunInputSource input)
    {
        bool lost = !ReferenceEquals(_holding, Target) || !Alive(_holding) || !_holding.CanInteract(gameObject);
        bool moved = input != null && input.Peek().move.magnitude > holdCancelMove;
        bool released = Held != null && !Held();
        // With no held level to read, the second press is the only way to say "stop".
        bool pressedAgain = Held == null && input != null && input.TryUse(RunButton.Interact);
        if (lost || moved || released || pressedAgain)
        {
            CancelHold();
            return;
        }

        _heldFor += Time.fixedDeltaTime;
        HoldProgress = Mathf.Clamp01(_heldFor / _holding.HoldSeconds);
        if (_heldFor < _holding.HoldSeconds) return;

        IInteractable done = _holding;
        _holding = null;
        _heldFor = 0f;
        HoldProgress = 0f;
        Deliver(done, true);
    }

    void Deliver(IInteractable target, bool allowed)
    {
        // Always delivered: a refused press is the interactable's to answer (a locked buzz).
        // The base class can still refuse inside OnInteract (a full bag); its Uses says which.
        var counted = target as InteractableBase;
        int usesBefore = counted != null ? counted.Uses : 0;
        target.Interact(gameObject);
        if (counted != null) allowed = counted.Uses > usesBefore;
        if (allowed)
        {
            Interactions++;
            Interacted?.Invoke(target);
        }
        else
        {
            Refusals++;
            Refused?.Invoke(target);
        }
        // The use usually changed what is allowed; do not wait a scan to show it.
        if (Alive(Target)) TargetAvailable = Target.CanInteract(gameObject);
    }

    void Scan()
    {
        _candidates.Clear();
        Gather(_candidates);

        float half = HalfAngle;
        bool cone = half < 180f;
        float keepRange = KeepRange;

        IInteractable best = null;
        float bestScore = float.NegativeInfinity;
        bool bestAvailable = false;

        for (int i = 0; i < _candidates.Count; i++)
        {
            InteractionCandidate c = _candidates[i];
            if (!Alive(c.target)) continue;
            bool current = ReferenceEquals(c.target, Target);

            // Two thresholds: a wider one for the target already held, so a runner standing on
            // the rim does not see the prompt blink.
            if (GateByRange && c.distance > (current ? keepRange : range)) continue;
            if (cone && c.angle > (current ? half + keepAngleMargin : half)) continue;

            bool available = c.target.CanInteract(gameObject);
            float score = 1f - Mathf.Clamp01(c.distance / keepRange);
            if (cone) score += angleWeight * (1f - Mathf.Clamp01(c.angle / (half + keepAngleMargin)));
            score += priorityWeight * c.target.Priority;
            if (!available) score -= unavailablePenalty;
            if (current) score += switchMargin;

            if (score <= bestScore) continue;
            bestScore = score;
            best = c.target;
            bestAvailable = available;
        }

        TargetAvailable = bestAvailable;
        SetTarget(best);
    }

    void SetTarget(IInteractable next)
    {
        // Compared by reference, so a target destroyed since the last scan still counts as a
        // change and the prompt hears about it; it is reported to listeners as null.
        if (ReferenceEquals(Target, next)) return;
        IInteractable previous = Alive(Target) ? Target : null;
        Target = next;
        if (next == null) TargetAvailable = false;
        TargetChanges++;
        TargetChanged?.Invoke(previous, next);
    }
}
