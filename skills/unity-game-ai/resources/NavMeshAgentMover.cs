// NavMeshAgentMover — the IMover that hands the sentry's requests to a NavMeshAgent. The agent
// owns the transform; this file only translates "go there at this speed" into a destination.
//
// Drop into the Runtime assembly that holds SentryBrain.cs and add it to the sentry beside
// a NavMeshAgent. It is a separate file so the rest of the skill compiles in a project with no
// navigation at all.
// REQUIRES com.unity.modules.ai (built in: NavMeshAgent is an engine type) to compile, and
// com.unity.ai.navigation for the NavMeshSurface that bakes what the agent walks on.
//
// It never assigns transform.position, and it re-issues a destination only when the goal has
// moved: a destination set every step throws the corridor away and re-plans, which reads as a
// pause at every corner.
using UnityEngine;
using UnityEngine.AI;

[DisallowMultipleComponent]
[RequireComponent(typeof(NavMeshAgent))]
public sealed class NavMeshAgentMover : MonoBehaviour, IMover
{
    [Tooltip("Units. A new destination closer than this to the one already issued is ignored.")]
    public float reissueDistance = 0.5f;
    [Tooltip("Units of slack on arrival, added to the stopping distance.")]
    public float arriveTolerance = 0.1f;
    [Tooltip("Degrees per second the body turns to a facing while it stands still.")]
    public float standingTurnSpeed = 360f;

    NavMeshAgent _agent;
    Vector3 _issued;
    bool _hasDestination;

    public Vector3 Position => transform.position;
    public Vector3 Velocity => _agent != null ? _agent.velocity : Vector3.zero;

    public bool Arrived
    {
        get
        {
            if (!_hasDestination) return true;
            // remainingDistance is 0 before planning starts and Infinity while it runs: both
            // read as an answer unless pathPending is asked first.
            if (_agent.pathPending) return false;
            return _agent.remainingDistance <= _agent.stoppingDistance + arriveTolerance;
        }
    }

    void Awake() => _agent = GetComponent<NavMeshAgent>();

    public void MoveTo(Vector3 destination, float speed, float stoppingDistance)
    {
        if (!_agent.isOnNavMesh) return;      // not placed on a surface: SetDestination would log an error
        _agent.speed = speed;
        _agent.stoppingDistance = stoppingDistance;
        _agent.isStopped = false;
        if (_hasDestination && (destination - _issued).sqrMagnitude < reissueDistance * reissueDistance) return;
        _issued = destination;
        _hasDestination = _agent.SetDestination(destination);
    }

    public void Stop()
    {
        _hasDestination = false;
        if (!_agent.isOnNavMesh) return;
        _agent.isStopped = true;
        _agent.ResetPath();
    }

    public void Face(Vector3 direction)
    {
        // The agent turns the body while it moves; a facing is only shown when it stands.
        if (_agent.velocity.sqrMagnitude > 0.04f) return;
        direction.y = 0f;
        if (direction.sqrMagnitude < 1e-6f) return;
        transform.rotation = Quaternion.RotateTowards(
            transform.rotation, Quaternion.LookRotation(direction, Vector3.up), standingTurnSpeed * Time.deltaTime);
    }
}
