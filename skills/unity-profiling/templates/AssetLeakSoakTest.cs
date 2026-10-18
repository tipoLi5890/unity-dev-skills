// AssetLeakSoakTest.cs — play the same situations several times and fail when the number of
// Materials or Meshes in memory keeps growing. Catches the leaks a frame-time window never shows:
// runtime-made assets that outlive the objects that made them.
//
// Copy into a PlayMode test assembly that references UnityEngine.TestRunner and the game's
// Runtime assembly. Fill in the three hooks marked HOOK with the game's own way of starting a
// situation, letting it run, and leaving it (unity-play-harness → resources/ has a situation API).
//
// The measure: Resources.FindObjectsOfTypeAll<Material>() and <Mesh>() count every loaded
// instance, assets and runtime copies alike. Round 1 loads what the game keeps for its lifetime
// (shared materials, font atlases, pools), so it is the baseline; rounds 2 and 3 must not add
// more than a small slack. On failure the log names what grew, by object name, so name every
// runtime asset you create.
//
// Do NOT call Resources.UnloadUnusedAssets in the test: it frees unreferenced runtime assets and
// hides exactly the leak this looks for. If the game calls it on every scene load, the leak is
// still real on the frames before that call; test the screen that is rebuilt without a scene load.
//
// Worked case: a tennis game rebuilt its match screen every match. Nine matches (three situations,
// three rounds) found runtime materials and meshes that were never destroyed (fixed with
// resources/OwnedAssets.cs) and sixteen TextMeshPro outline materials copied per match by
// per-label outlineWidth / outlineColor edits (fixed by sharing one material). After the fix both counts were flat
// within the slack of 4. It runs in the smoke category, on every change.
//
//   [LEAK] after round 1: materials 412, meshes 233
//   [LEAK] after round 3: materials 412, meshes 233
//   [LEAK] grew: ScoreLabel Outline +32, HitRing +18          (only printed when something grew)
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public sealed class AssetLeakSoakTest
{
    const int Rounds = 3;
    const int Slack = 4;

    // HOOK: the situations to cycle. Cover each screen variant (solo, split screen, each venue).
    static readonly string[] Situations = { "match/solo-a", "match/duel-b", "match/solo-c" };

    [UnityTest, Category("Smoke")]
    public IEnumerator RepeatedSituations_DoNotAccumulateMaterialsOrMeshes()
    {
        int mats0 = 0, meshes0 = 0;
        Dictionary<string, int> names0 = null;
        for (int round = 0; round < Rounds; round++)
        {
            foreach (var s in Situations)
            {
                yield return Enter(s);       // HOOK
                yield return Run(s);         // HOOK
                yield return Leave(s);       // HOOK
            }
            yield return null;               // let Destroy() calls from the last Leave complete
            yield return null;
            int mats = Resources.FindObjectsOfTypeAll<Material>().Length;
            int meshes = Resources.FindObjectsOfTypeAll<Mesh>().Length;
            Debug.Log($"[LEAK] after round {round + 1}: materials {mats}, meshes {meshes}");
            if (round == 0) { mats0 = mats; meshes0 = meshes; names0 = Names(); }
            if (round == Rounds - 1)
            {
                var grew = Names().Where(kv => kv.Value > (names0.TryGetValue(kv.Key, out var c) ? c : 0))
                                  .Select(kv => kv.Key + " +" + (kv.Value - (names0.TryGetValue(kv.Key, out var c0) ? c0 : 0)))
                                  .ToArray();
                if (grew.Length > 0) Debug.Log("[LEAK] grew: " + string.Join(", ", grew));
                Assert.LessOrEqual(mats - mats0, Slack, "materials pile up across rounds: " + string.Join(", ", grew));
                Assert.LessOrEqual(meshes - meshes0, Slack, "meshes pile up across rounds");
            }
        }
    }

    static Dictionary<string, int> Names() =>
        Resources.FindObjectsOfTypeAll<Material>().Concat<Object>(Resources.FindObjectsOfTypeAll<Mesh>())
            .GroupBy(o => o.GetType().Name + ":" + (string.IsNullOrEmpty(o.name) ? "(unnamed)" : o.name))
            .ToDictionary(g => g.Key, g => g.Count());

    // ---- HOOKS: replace with the game's own calls -------------------------------------------

    static IEnumerator Enter(string situation)
    {
        // e.g. yield return Situations.Enter(situation);   or load the match scene with a config
        Assert.Inconclusive("AssetLeakSoakTest: fill in Enter() for " + situation);
        yield break;
    }

    static IEnumerator Run(string situation)
    {
        // Long enough for every effect, popup and label to have appeared at least once:
        // a hit, a bounce, a score, a banner. Autoplay or scripted input.
        yield return new WaitForSeconds(6f);
    }

    static IEnumerator Leave(string situation)
    {
        // e.g. back to the menu: the screen that is rebuilt per match is destroyed here.
        yield break;
    }
}
