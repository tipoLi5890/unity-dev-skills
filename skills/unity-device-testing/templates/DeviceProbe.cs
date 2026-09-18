// DeviceProbe — a dev-only scene's single MonoBehaviour: drive the feature under test through its
// PUBLIC API and report in a shape a script can assert on (reference/device-probe.md).
//
//   [Probe] state A -> B (…)        every transition, old -> new
//   [Probe] <event> <payload>       every external event
//   [Probe] diag k=v k=v …          once a second
//   [Probe] error <Type>: <msg>     every error
//
// Fill the three HOOK sections. Everything else is plumbing you should not need to touch.
// Put it on one GameObject in a scene of its own, outside the shipped build list.
using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;

public sealed class DeviceProbe : MonoBehaviour
{
    const string Tag = "[Probe] ";                 // the driver greps for this — keep it stable

    // ── HOOK 1: the feature under test ────────────────────────────────────────────────────
    // Replace this stand-in with the real object. Keep the probe on the PUBLIC API: a probe that
    // needs internals is testing something users cannot reach.
    enum State { Stopped, Starting, Running, Faulted }
    State _state = State.Stopped;
    string _mode = "A";                            // one axis of configuration, switched by a button
    static readonly string[] Modes = { "A", "B" };

    async Task StartFeature()
    {
        SetState(State.Starting);
        await Task.Delay(200);                     // … real start goes here; log what was NEGOTIATED
        Log($"running mode={_mode} requested=… actual=…");
        SetState(State.Running);
    }

    void StopFeature() { if (_state != State.Stopped) SetState(State.Stopped); }

    // ── HOOK 2: the once-a-second numbers (k=v, stable key order) ─────────────────────────
    string DiagLine() => $"mode={_mode} state={_state} frames={Time.frameCount}";

    // ── HOOK 3: one unattended sequence over every configuration ──────────────────────────
    async Task RunSequence()
    {
        foreach (var m in Modes)
        {
            try
            {
                Log($"step {m} requested");
                StopFeature(); _mode = m;
                await StartFeature();
                await Task.Delay(2000);            // settle
                // … record / measure for a fixed time, then:
                string file = WriteText($"result_{Platform}_{m}.txt", DiagLine());
                Log($"step {m} wrote {file}");
            }
            catch (Exception e) { Log($"step {m} FAILED {e.GetType().Name}: {e.Message}"); }
        }
        Log("sequence DONE dir=" + Application.persistentDataPath);
    }

    // ── plumbing ──────────────────────────────────────────────────────────────────────────
    readonly List<string> _lines = new List<string>();
    string _lastError = ""; float _nextDiag; bool _busy; GUIStyle _label, _button;
    static string Platform => Application.platform == RuntimePlatform.IPhonePlayer ? "ios" : "android";

    async void Start()
    {
        Screen.sleepTimeout = SleepTimeout.NeverSleep;     // a run that waits for a human keeps the screen
        Log($"build app={Application.version} unity={Application.unityVersion} platform={Platform}");
        await Guarded(StartFeature);
    }

    void Update()
    {
        if (Time.unscaledTime < _nextDiag) return;
        _nextDiag = Time.unscaledTime + 1f;
        if (_state == State.Running) Debug.Log(Tag + "diag " + DiagLine());   // not into _lines: it would scroll the events away
    }

    void OnDestroy() => StopFeature();

    void SetState(State next)
    {
        var prev = _state; _state = next;
        Log($"state {prev} -> {next}");
    }

    async Task Guarded(Func<Task> work)
    {
        if (_busy) return;
        _busy = true;
        try { await work(); }
        catch (Exception e) { _lastError = e.GetType().Name + ": " + e.Message; Log("error " + _lastError); SetState(State.Faulted); }
        finally { _busy = false; }
    }

    async void NextMode()
    {
        int i = (Array.IndexOf(Modes, _mode) + 1) % Modes.Length;
        Log("mode -> " + Modes[i]);                        // the driver waits on THIS line, not on the tap
        StopFeature(); _mode = Modes[i];
        await Guarded(StartFeature);
    }

    string WriteText(string name, string body)
    {
        string path = Path.Combine(Application.persistentDataPath, name);
        File.WriteAllText(path, body);
        return path;                                       // always logged in full: the driver pulls exactly this
    }

    void Log(string msg)
    {
        string line = DateTime.Now.ToString("HH:mm:ss.fff ") + msg;
        _lines.Add(line); if (_lines.Count > 20) _lines.RemoveAt(0);
        Debug.Log(Tag + msg);
    }

    void OnGUI()
    {
        if (_label == null)
        {
            int size = Mathf.Max(24, Screen.height / 36);
            _label  = new GUIStyle(GUI.skin.label)  { fontSize = size, richText = true };
            _button = new GUIStyle(GUI.skin.button) { fontSize = size };
            _label.normal.textColor = Color.white;
        }
        float h = _label.fontSize * 1.5f, y = 20f, w = Screen.width - 40f;
        GUI.Label(new Rect(20, y, w, h), $"<b>{_state}</b>  {DiagLine()}", _label); y += h;
        GUI.Label(new Rect(20, y, w, h), "lastError: " + _lastError, _label);       y += h * 1.2f;
        foreach (var l in _lines) { GUI.Label(new Rect(20, y, w, h), l, _label); y += h; }

        // Bottom row: one large button per axis. Android drivers tap by coordinate; on iOS a human does.
        float by = Screen.height - h * 2.5f, bw = Screen.width / 2f - 30f;
        if (GUI.Button(new Rect(20, by, bw, h * 2f), "mode: " + _mode + "  (next)", _button)) NextMode();
        if (GUI.Button(new Rect(Screen.width / 2f + 10, by, bw, h * 2f), _busy ? "running…" : "run sequence", _button) && !_busy)
            _ = Guarded(RunSequence);
    }
}
