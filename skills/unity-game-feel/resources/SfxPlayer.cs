// SfxPlayer.cs — the event layer between gameplay and AudioSource: gameplay names an event,
// this decides whether it sounds, which clip, at what pitch, and on which pooled source.
//
// Drop into a Runtime assembly. No package needed (the built-in Audio module). Put one in the
// boot scene, fill Events, and assign the mixer group every effect routes to.
//
//   sfx.Play("pickup");                         // 2D, at the listener
//   sfx.Play("gate-open", gate.position);       // positioned, when the event's spatial blend is above 0
//
// Thirty pickups collected in one step ask for thirty sounds. Three things answer, in order:
//   cooldown   an event that played under cooldownSeconds ago is dropped
//   per event  an event already on maxVoices sources is dropped
//   voice cap  with every source busy, the request steals the least important voice when
//              that voice is strictly less important than it, and is dropped otherwise
// Thirty copies of one clip a few milliseconds apart are not thirty times as loud — they
// sum into a comb-filtered smear and clip the mix. One, repitched, is the sound of many.
//
// Voices are tracked by this component's own clock and not by AudioSource.isPlaying, which
// reads false in a run with no audio device (a batch-mode test) and for one frame after Play.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Audio;

[Serializable]
public sealed class SfxEvent
{
    public string name = "pickup";
    [Tooltip("One is picked per play, never the same twice running when there are two or more.")]
    public AudioClip[] clips;
    [Range(0f, 1f)] public float volume = 1f;
    [Tooltip("Random spread of the volume, 0.1 = plus or minus 10 %.")]
    [Range(0f, 0.5f)] public float volumeVariance = 0.1f;
    [Range(0.1f, 3f)] public float pitch = 1f;
    [Tooltip("Random spread of the pitch. 0.08 hides repetition without changing the note.")]
    [Range(0f, 0.5f)] public float pitchVariance = 0.08f;
    [Tooltip("Seconds before this event may sound again. 0.05 lets a fast run of pickups tick without smearing.")]
    public float cooldownSeconds = 0.05f;
    [Tooltip("Sources this one event may hold at once.")]
    public int maxVoices = 3;
    [Tooltip("Higher wins a full pool. 0 pickups and footsteps, 1 hits, 2 the gate, the launch, a fail.")]
    public int priority;
    [Tooltip("0 = 2D, the same in both ears wherever it happens. 1 = positioned in the world.")]
    [Range(0f, 1f)] public float spatialBlend;

    [NonSerialized] internal float lastPlayed = float.NegativeInfinity;
    [NonSerialized] internal int lastClip = -1;
    [NonSerialized] internal int voices;
}

[AddComponentMenu("Courier/Sfx Player")]
public sealed class SfxPlayer : MonoBehaviour
{
    public SfxEvent[] events = new SfxEvent[0];
    [Tooltip("Sources in the pool, and so sounds at once. Eight is a safe phone number and still reads as busy.")]
    public int voiceCap = 8;
    [Tooltip("Every pooled source routes here. Leave empty and effects bypass the mixer and its volume slider.")]
    public AudioMixerGroup output;
    [Tooltip("Distance at full volume, and distance at silence, for positioned events. Linear rolloff: silence at the far distance is exact.")]
    public float minDistance = 2f;
    public float maxDistance = 25f;
    [Tooltip("On for interface sounds that must play while AudioListener.pause is set.")]
    public bool ignoreListenerPause;

    struct Voice
    {
        public AudioSource source;
        public SfxEvent playing;
        public float end;          // Time.unscaledTime
        public int priority;
    }

    readonly Dictionary<string, SfxEvent> _byName = new Dictionary<string, SfxEvent>();
    Voice[] _voices = new Voice[0];
    bool _indexed;

    /// <summary>Calls to Play, whether or not they sounded.</summary>
    public int Requested { get; private set; }
    /// <summary>Calls that started a clip.</summary>
    public int Played { get; private set; }
    /// <summary>Calls dropped by the cooldown, the per-event limit or the voice cap.</summary>
    public int Dropped { get; private set; }
    /// <summary>Calls that named an event with no entry or no clip. Not zero means a typo.</summary>
    public int Unknown { get; private set; }

    public int ActiveVoices
    {
        get
        {
            Sweep(Time.unscaledTime);
            int n = 0;
            for (int i = 0; i < _voices.Length; i++) if (_voices[i].playing != null) n++;
            return n;
        }
    }

    public bool Play(string eventName) => Play(eventName, transform.position, 1f);

    public bool Play(string eventName, Vector3 position, float volumeScale = 1f)
    {
        Requested++;
        EnsurePool();
        if (!_indexed) Index();
        if (eventName == null || !_byName.TryGetValue(eventName, out SfxEvent e) || e.clips == null || e.clips.Length == 0)
        {
            Unknown++;
            return false;
        }

        // Unscaled: sound runs in real time, so a cooldown on scaled time never expires in a
        // hit stop and expires twenty times too slowly in slow motion.
        float now = Time.unscaledTime;
        Sweep(now);

        if (now - e.lastPlayed < e.cooldownSeconds || e.voices >= Mathf.Max(1, e.maxVoices))
        {
            Dropped++;
            return false;
        }

        int slot = FreeSlot(e.priority);
        if (slot < 0)
        {
            Dropped++;
            return false;
        }

        AudioClip clip = Pick(e);
        if (clip == null) { Unknown++; return false; }

        ref Voice v = ref _voices[slot];
        if (v.playing != null) { v.source.Stop(); v.playing.voices--; }     // stolen

        float pitch = Mathf.Max(0.1f, e.pitch + UnityEngine.Random.Range(-e.pitchVariance, e.pitchVariance));
        AudioSource s = v.source;
        s.transform.position = position;
        s.clip = clip;
        s.pitch = pitch;
        s.volume = Mathf.Clamp01(e.volume * volumeScale * (1f + UnityEngine.Random.Range(-e.volumeVariance, e.volumeVariance)));
        s.spatialBlend = e.spatialBlend;
        // The engine's own voice priority runs the other way: 0 is kept longest, 255 dropped first.
        s.priority = Mathf.Clamp(128 - e.priority * 32, 0, 255);
        s.Play();

        v.playing = e;
        v.priority = e.priority;
        v.end = now + clip.length / pitch;
        e.voices++;
        e.lastPlayed = now;
        Played++;
        return true;
    }

    /// <summary>Stop everything now — on a scene change, or when the run restarts.</summary>
    public void StopAll()
    {
        for (int i = 0; i < _voices.Length; i++)
        {
            if (_voices[i].playing == null) continue;
            if (_voices[i].source != null) _voices[i].source.Stop();
            _voices[i].playing.voices--;
            _voices[i].playing = null;
        }
    }

    /// <summary>Rebuild the name table after editing <see cref="events"/> from code.</summary>
    public void Index()
    {
        _byName.Clear();
        if (events != null)
            foreach (SfxEvent e in events)
            {
                if (e == null || string.IsNullOrEmpty(e.name)) continue;
                if (_byName.ContainsKey(e.name)) Debug.LogWarning("[SFX] two events are named '" + e.name + "'; the first is used", this);
                else _byName[e.name] = e;
            }
        _indexed = true;
    }

    void OnDisable() => StopAll();

    // Built on first use and rebuilt when voiceCap changes, so a cap assigned from code after
    // AddComponent is the cap that applies.
    void EnsurePool()
    {
        int want = Mathf.Max(1, voiceCap);
        if (_voices.Length == want) return;
        StopAll();
        var next = new Voice[want];
        for (int i = 0; i < want; i++)
        {
            if (i < _voices.Length) { next[i] = _voices[i]; continue; }
            var go = new GameObject("Voice " + i);
            go.transform.SetParent(transform, false);
            var s = go.AddComponent<AudioSource>();
            s.playOnAwake = false;
            s.loop = false;
            s.dopplerLevel = 0f;                         // a one-shot on a moving pool object must not bend
            s.rolloffMode = AudioRolloffMode.Linear;
            next[i].source = s;
        }
        for (int i = want; i < _voices.Length; i++)
            if (_voices[i].source != null) Destroy(_voices[i].source.gameObject);
        _voices = next;
        for (int i = 0; i < _voices.Length; i++)
        {
            AudioSource s = _voices[i].source;
            s.outputAudioMixerGroup = output;
            s.minDistance = minDistance;
            s.maxDistance = maxDistance;
            s.ignoreListenerPause = ignoreListenerPause;
        }
    }

    void Sweep(float now)
    {
        for (int i = 0; i < _voices.Length; i++)
        {
            if (_voices[i].playing == null || _voices[i].end > now) continue;
            _voices[i].playing.voices--;
            _voices[i].playing = null;
        }
    }

    // A free source, else the least important busy one that is strictly below this priority
    // (the one nearest its end among equals), else none.
    int FreeSlot(int priority)
    {
        int steal = -1;
        for (int i = 0; i < _voices.Length; i++)
        {
            if (_voices[i].playing == null) return i;
            if (_voices[i].priority >= priority) continue;
            if (steal < 0 || _voices[i].priority < _voices[steal].priority ||
                (_voices[i].priority == _voices[steal].priority && _voices[i].end < _voices[steal].end))
                steal = i;
        }
        return steal;
    }

    static AudioClip Pick(SfxEvent e)
    {
        int n = e.clips.Length;
        int i = n == 1 ? 0 : UnityEngine.Random.Range(0, n);
        if (n > 1 && i == e.lastClip) i = (i + 1) % n;
        e.lastClip = i;
        return e.clips[i];
    }
}
