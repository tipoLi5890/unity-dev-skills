# Behaviour tree — priority as structure, in about a hundred lines

> Part of the `unity-game-ai` skill. A behaviour tree and a state machine answer the same
> question — what does this enemy do now — with opposite defaults: a state machine stays where it
> is until a transition says otherwise, a tree re-asks from the top every tick. This file is the
> smallest tree that is still correct about running nodes, when it beats `resources/StateMachine.cs`,
> and when to stop writing one and install a package. Worked setting: the **gate room** sentry.

## 1. Which one

| The behaviour is | Use | Why |
|---|---|---|
| A few modes with clear exits: patrol, chase, return | State machine | The graph is six lines of `AddTransition`; hysteresis sits on each arrow |
| A priority list: "attack if able, else take cover, else advance, else idle" | Behaviour tree | Priority is the order of children; adding an option is adding a child, not N transitions |
| Sequences that can be interrupted at any step: "walk to the switch, wait, press it, walk back" | Behaviour tree | A sequence remembers its step; a selector above it interrupts it |
| Modes on the outside, a priority list inside one of them | Both: a state whose `Tick` ticks a tree | The state machine holds Chase; the tree picks what a chasing sentry does |
| One of many options with no fixed order, weighed by the situation | Utility scoring — `reference/tactics-ai.md` | Neither structure expresses "the best of these" |

The count that decides it: a state machine with N states has up to N² arrows. At four states
the sentry has six and reads at a glance. At eight states with interrupts from each to each, the
arrows are the program and nobody can say what wins. That is the moment for a tree.

A tree does **not** replace the other two layers. It reads the same blackboard, on the same
decision tick, and asks the same `IMover` — it is a different shape for the middle box only.

## 2. Three statuses, three node kinds

Every node returns one of `Success`, `Failure`, `Running`.

| Node | Returns | Reads as |
|---|---|---|
| **Condition** (leaf) | Success or Failure, never Running | "Is the runner seen?" |
| **Action** (leaf) | Running while it works, then Success or Failure | "Walk to the last-seen position" |
| **Sequence** | Failure at the first child that fails; Running at the first that runs; Success when all succeed | And-then |
| **Selector** | The status of the first child that does not fail; Failure when all fail | Or-else, in priority order |
| **Decorator** | Its one child's status, changed | Not, cooldown, repeat, time limit |

## 3. The tree

Drop this into a Runtime assembly as `BehaviourTree.cs`. No MonoBehaviour, no package.

```csharp
using System;

public enum NodeStatus { Success, Failure, Running }

public abstract class BtNode<T>
{
    public abstract NodeStatus Tick(T context, float dt);
    /// <summary>Called on a node that returned Running and is not ticked again: a higher branch took over.</summary>
    public virtual void Abort(T context) { }
}

/// <summary>A leaf that asks a question. Never Running.</summary>
public sealed class BtCondition<T> : BtNode<T>
{
    readonly Func<T, bool> _test;
    public BtCondition(Func<T, bool> test) { _test = test; }
    public override NodeStatus Tick(T context, float dt) => _test(context) ? NodeStatus.Success : NodeStatus.Failure;
}

/// <summary>A leaf that does something, over one tick or many.</summary>
public sealed class BtAction<T> : BtNode<T>
{
    readonly Func<T, float, NodeStatus> _run;
    readonly Action<T> _abort;
    public BtAction(Func<T, float, NodeStatus> run, Action<T> abort = null) { _run = run; _abort = abort; }
    public override NodeStatus Tick(T context, float dt) => _run(context, dt);
    public override void Abort(T context) => _abort?.Invoke(context);
}

public abstract class BtComposite<T> : BtNode<T>
{
    protected readonly BtNode<T>[] Children;
    protected int RunningChild = -1;
    protected BtComposite(BtNode<T>[] children) { Children = children; }

    public override void Abort(T context)
    {
        if (RunningChild >= 0) Children[RunningChild].Abort(context);
        RunningChild = -1;
    }
}

/// <summary>All of these, in order. Remembers the running child: finished steps are not repeated.</summary>
public sealed class BtSequence<T> : BtComposite<T>
{
    public BtSequence(params BtNode<T>[] children) : base(children) { }

    public override NodeStatus Tick(T context, float dt)
    {
        for (int i = RunningChild >= 0 ? RunningChild : 0; i < Children.Length; i++)
        {
            NodeStatus status = Children[i].Tick(context, dt);
            if (status == NodeStatus.Success) continue;
            RunningChild = status == NodeStatus.Running ? i : -1;
            return status;
        }
        RunningChild = -1;
        return NodeStatus.Success;
    }
}

/// <summary>The first of these that does not fail. Asked from the top every tick, so order is priority.</summary>
public sealed class BtSelector<T> : BtComposite<T>
{
    public BtSelector(params BtNode<T>[] children) : base(children) { }

    public override NodeStatus Tick(T context, float dt)
    {
        for (int i = 0; i < Children.Length; i++)
        {
            NodeStatus status = Children[i].Tick(context, dt);
            if (status == NodeStatus.Failure) continue;
            // A lower-priority child was running and this one took over: tell it, once.
            if (RunningChild > i) Children[RunningChild].Abort(context);
            RunningChild = status == NodeStatus.Running ? i : -1;
            return status;
        }
        RunningChild = -1;
        return NodeStatus.Failure;
    }
}

/// <summary>Success becomes Failure and the reverse. Running passes through.</summary>
public sealed class BtInvert<T> : BtNode<T>
{
    readonly BtNode<T> _child;
    public BtInvert(BtNode<T> child) { _child = child; }

    public override NodeStatus Tick(T context, float dt)
    {
        NodeStatus status = _child.Tick(context, dt);
        if (status == NodeStatus.Running) return status;
        return status == NodeStatus.Success ? NodeStatus.Failure : NodeStatus.Success;
    }

    public override void Abort(T context) => _child.Abort(context);
}

/// <summary>After the child finishes, fail without asking it for a while: one bark per 5 s, one dodge per 2.</summary>
public sealed class BtCooldown<T> : BtNode<T>
{
    readonly BtNode<T> _child;
    readonly float _seconds;
    float _remaining;
    public BtCooldown(float seconds, BtNode<T> child) { _seconds = seconds; _child = child; }

    public override NodeStatus Tick(T context, float dt)
    {
        if (_remaining > 0f) { _remaining -= dt; return NodeStatus.Failure; }
        NodeStatus status = _child.Tick(context, dt);
        if (status != NodeStatus.Running) _remaining = _seconds;
        return status;
    }

    public override void Abort(T context) => _child.Abort(context);
}
```

## 4. Running-node memory — the part most small trees get wrong

The two composites treat a running child differently, and both choices are deliberate.

| Composite | On the next tick | Because |
|---|---|---|
| **Sequence** | Resumes at the child that was running | "Walk to the switch, wait 1 s, press it": re-running step one every tick walks to the switch forever |
| **Selector** | Starts again from the first child | That is what makes it reactive: while the sentry patrols (child 3), "the runner is seen" (child 1) is asked every tick and takes over the moment it holds |

Two consequences to design for:

- **A selector that takes over must tell the child it abandoned.** A patrol action left
  `Running` with a destination issued keeps walking unless something stops it. `Abort` is that
  call; it reaches the running leaf through every composite in between. An action that started
  something — a move, an animation, a reservation of a cell — passes an abort delegate that ends it.
- **A sequence does not re-check finished conditions.** `Sequence(seen?, chase)` asks `seen?`
  once and then runs `chase` until it finishes. Put the condition where it is re-asked: inside
  the action ("return Failure when the memory expires"), or as an inverted guard above it in the
  selector. The worked tree below does the first.

## 5. The sentry as a tree

The same blackboard, the same mover, the same decision tick as the state machine:

```csharp
BtNode<SentryBlackboard> Build(IMover mover)
{
    bool chasing = false;
    var chase = new BtAction<SentryBlackboard>(
        (b, dt) =>
        {
            // Re-asked every tick: start only on a full alert, keep going while the memory lasts.
            if (b.memory.Expired(b.now, 3f) || (!chasing && b.alert < 1f)) { chasing = false; return NodeStatus.Failure; }
            chasing = true;
            mover.MoveTo(b.memory.position, 4f, 1f);
            return NodeStatus.Running;
        },
        b => { chasing = false; mover.Stop(); });

    // One action, not Sequence(alert > 0?, stand): a running sequence resumes at its second
    // child and would never ask the alert again (§4).
    var look = new BtAction<SentryBlackboard>(
        (b, dt) =>
        {
            if (b.alert <= 0f) return NodeStatus.Failure;
            mover.Stop();
            return NodeStatus.Running;
        });

    var patrol = new BtAction<SentryBlackboard>(
        (b, dt) =>
        {
            mover.MoveTo(b.home, 2f, 0f);
            return mover.Arrived ? NodeStatus.Success : NodeStatus.Running;
        },
        b => mover.Stop());

    // Order is priority: chase beats look beats patrol.
    return new BtSelector<SentryBlackboard>(chase, look, patrol);
}

// On the decision tick, after perception has written the blackboard:
_tree.Tick(board, decisionInterval);
```

- **Tick the tree on the decision tick, not the frame.** Its actions are requests that persist —
  `MoveTo` keeps the mover walking between ticks — so nothing needs it more often. Pass the
  decision interval as `dt`, and every timer in a decorator is in seconds.
- **The look branch never finishes on its own**: it stays `Running` while the alert is above
  zero, and the selector re-asks `chase` above it each tick. The alert meter is still the
  hysteresis; a tree has no arrows to hang it on, so it lives in the blackboard.
- **Calling `MoveTo` every decision tick is fine**: 10 Hz is a re-path interval, and a mover
  ignores a destination that has not moved (`NavMeshAgentMover.reissueDistance`).
- **Build the tree once.** Nodes hold their running index and their timers; a tree rebuilt each
  tick has no memory, and one tree shared by two sentries has the wrong one.

## 6. Debugging a tree

A state machine has one name to print; a tree has a path. Expose the leaf:

```csharp
string _leaf;
BtAction<SentryBlackboard> Named(string name, Func<SentryBlackboard, float, NodeStatus> run, Action<SentryBlackboard> abort = null)
    => new BtAction<SentryBlackboard>((b, dt) => { NodeStatus s = run(b, dt); if (s == NodeStatus.Running) _leaf = name; return s; }, abort);

GameProbe.Register("sentry", () => _leaf);       // chase · look · patrol
```

The journey in `templates/SentryJourneyTest.cs` reads the `sentry` value by name. Give the
leaves the four state names it expects — the tree above needs a Return leaf between look and
patrol — and the same three tests judge a sentry driven by a tree.

| Symptom | Cause |
|---|---|
| The enemy restarts an action every tick | A condition above it flips each tick: the missing hysteresis. Or the tree is rebuilt per tick |
| It keeps walking after a higher branch took over | The action has no abort delegate |
| A sequence stalls on its second step | The step returns `Running` and nothing makes it finish: give it a time limit |
| The frame time climbs with the crowd | Conditions that cast. Perception writes the blackboard once per tick; conditions only read it — `reference/perception.md` |

## 7. When to add a package

The tree above is enough while one programmer authors every enemy in code. It stops being enough
when:

| Sign | What a package buys |
|---|---|
| Designers who do not write C# author or tune behaviour | A graph editor, and behaviour stored as an asset |
| More than about a dozen distinct enemy trees, sharing sub-trees | Sub-graphs as assets, blackboard variables set per instance in the Inspector |
| Debugging means asking "which node is it in" many times a day | A live view of the running path in the editor |
| Parallel branches, interrupts and events between agents are needed everywhere | They are built, tested and documented by someone else |

Unity's own is `com.unity.behavior` (the Behavior package). It is not in the editor's default
package set, so a project has it only if someone added it:

```bash
grep -n '"com.unity.behavior"' Packages/manifest.json     # nothing printed: not installed
```

Before adding it, read the package page for the minimum editor version it names and compare it
with `ProjectSettings/ProjectVersion.txt`. Adding it changes the middle layer only: perception
still writes a blackboard on a budget, and the mover still owns the transform. Keep
`resources/Perception.cs` and the `IMover` seam, expose them to the graph as its actions and
conditions, and the journey keeps passing with the brain replaced.

## Where each need is answered

| Need | Answer |
|---|---|
| The state machine a tree is weighed against | `reference/state-machine.md` |
| What the conditions read | `reference/perception.md` |
| What the actions ask of the mover | `reference/patrol-and-chase.md` |
| Scoring options with no fixed priority | `reference/tactics-ai.md` |
| Adding a package headlessly | `unity-new-project` → `reference/package-bootstrap.md` |
| Journeys and break switches | `unity-play-harness` → `reference/journeys.md` |
