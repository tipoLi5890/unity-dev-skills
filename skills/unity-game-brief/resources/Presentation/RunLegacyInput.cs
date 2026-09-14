// A keyboard stand-in for the three physical buttons, so the first interaction is playable
// in the Editor on the day it is written. It is deliberately the ONLY file that knows a
// device exists: everything downstream sees Launch / LaneLeft / LaneRight.
//
// Replace it with the project's real input funnel as soon as there is one — the funnel calls
// the same three methods, and nothing else changes.
using UnityEngine;

namespace Game.Presentation
{
    [RequireComponent(typeof(RunPresenter))]
    [AddComponentMenu("Courier/Run Legacy Input")]
    public sealed class RunLegacyInput : MonoBehaviour
    {
#if ENABLE_LEGACY_INPUT_MANAGER
        RunPresenter _presenter;

        void Awake() => _presenter = GetComponent<RunPresenter>();

        void Update()
        {
            if (_presenter == null) return;
            if (Input.GetKeyDown(KeyCode.Space)) _presenter.Launch();
            if (Input.GetKeyDown(KeyCode.A)) _presenter.LaneLeft();
            if (Input.GetKeyDown(KeyCode.D)) _presenter.LaneRight();
        }
#else
        // The project's Active Input Handling is set to the new Input System only, so
        // UnityEngine.Input is compiled out here. Said once, at Awake, not every frame.
        void Awake()
        {
            Debug.Log($"[RUN] legacy input is disabled in this project — drive {nameof(RunPresenter)} " +
                      "from the project's input funnel by calling Launch / LaneLeft / LaneRight.");
        }
#endif
    }
}
