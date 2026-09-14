# Building CJK font assets from a script — order, sub-assets, and the file that never stays clean

> Part of the `unity-localization` skill. Sizing numbers (padding ratio, sampling point size per
> script, atlas cap) belong to `unity-game-ui` → `reference/text-and-cjk.md` and are not repeated
> here. This file is the pipeline around them: what has to exist before the builder runs, what the
> builder has to write, and which of its outputs will fight your repo.

Locale set throughout: zh-Hans / zh-Hant / ja / en.

## 1. The order is fixed, and the failure at step zero has no message

```
TMP Essential Resources  →  font assets  →  anything that references them
```

> **`TMP_FontAsset.CreateFontAsset` throws a `NullReferenceException` raised inside `TMP_Settings`
> when TMP Essential Resources have never been imported.** There is no message naming TMP, no
> "settings not found" — TMP simply has no settings object to read. The symptom reads as a broken
> font file or a broken build script, and the actual cause is a folder that does not exist.

Diagnose it in one line before touching anything else: does `Assets/TextMesh Pro/` exist? Then
guard the builder so the next person gets a sentence instead of an NRE:

```csharp
const string TmpSettings = "Assets/TextMesh Pro/Resources/TMP Settings.asset";
if (AssetDatabase.LoadAssetAtPath<TMP_Settings>(TmpSettings) == null) {
    Debug.LogError("TMP Essential Resources not imported — run the import step first.");
    return;                                   // exit before the NRE, with the cause named
}
```

Importing them headlessly is its own `-executeMethod`, because `AssetDatabase.ImportPackage` is
**asynchronous**: finish from `AssetDatabase.importPackageCompleted`, and let the Editor reach an
update tick.

> **The `.unitypackage` has no path you can write down — find it.** TextMesh Pro ships inside
> `com.unity.ugui`, and a registry package unpacks into
> `Library/PackageCache/<id>@<version-or-hash>/`, so the folder name changes with every resolve.
> A literal `Packages/com.unity.ugui/Package Resources/…` holds only while that package is
> embedded or local. `ImportPackage` against a path that is not there **imports nothing and fails
> no step**: no exception, no log line, and the next builder call dies on the NRE above.

Scan for it, and say what you scanned when it is missing:

```csharp
const string Tail = "Package Resources/TMP Essential Resources.unitypackage";

static string FindTmpEssentials() {
    var roots = new List<string> { "Packages/com.unity.ugui" };          // embedded or local
    if (Directory.Exists("Library/PackageCache"))
        roots.AddRange(Directory.GetDirectories("Library/PackageCache"));  // registry, versioned name
    foreach (var root in roots) {
        var candidate = Path.Combine(root, Tail).Replace('\\', '/');
        if (File.Exists(candidate)) return candidate;
    }
    Debug.LogError($"TMP Essential Resources not found under any of {roots.Count} roots: " +
                   string.Join(", ", roots));                             // name what was searched
    return null;
}

var pkg = FindTmpEssentials();
if (pkg == null) { EditorApplication.Exit(1); return; }                   // fail loudly, not silently
AssetDatabase.importPackageCompleted += _ => { /* done — now the settings asset exists */ };
AssetDatabase.ImportPackage(pkg, false);
```

Printing the scanned roots is the whole value of the guard: a run that found nothing then says
whether the package is absent, embedded somewhere unexpected, or not resolved yet.

> **Never reach for the menu item.**
> `EditorApplication.ExecuteMenuItem("Window/TextMeshPro/Import TMP Essential Resources")` returns
> `true` and then opens a **modal dialog** waiting for a human to click it. Nothing after it runs,
> the Editor never reaches an update tick, and a headless run hangs there until some timeout kills
> it — reported as "the import step timed out" rather than as a dialog nobody could see. The
> return value says the menu path existed, not that anything imported.

`TMP_PackageResourceImporter.ImportResources()` needs no path and opens no dialog —
`unity-ui-ugui` → `reference/code-built-ui.md`. Use the scan above when the import has to be an
auditable step with a named file and a completion callback.

> **Neither invocation may carry `-quit`.** The Editor exits the moment your method returns, which
> is before the import callback ever fires — exit code 0, no resources, no error. Same mechanism as
> the asynchronous package request in `unity-new-project` → `reference/package-bootstrap.md`.

```bash
"$UNITY" -batchmode -projectPath . -logFile - -executeMethod <Ns>.FontAssetBuilder.ImportTmpEssentials
"$UNITY" -batchmode -projectPath . -logFile - -executeMethod <Ns>.FontAssetBuilder.Build
```

Verify each step by the artifact it should have produced — `Assets/TextMesh Pro/` after the
first, `Assets/Fonts/*SDF.asset` after the second — not by the exit code, which in batchmode
without `-quit` tells you about the Editor session rather than about your method.

**Third ordering rule:** the builder is usually also the thing that writes the finished font
references back into whatever asset holds them (a theme, a settings object, an Asset Table). So
fonts must be built *before* the scaffolder that generates those assets runs, or the scaffolder
writes null font fields — and a null TMP font reference falls back to the built-in Liberation
Sans, which is solid tofu for CJK.

## 2. What the builder writes

A working configuration, one asset per locale:

```csharp
var fa = TMP_FontAsset.CreateFontAsset(font, 40, 4, GlyphRenderMode.SDFAA,
                                       1024, 1024, AtlasPopulationMode.Dynamic, true);
AssetDatabase.CreateAsset(fa, dst);

// Loop the array. That trailing `true` is multi-atlas: a CJK face grows a second and third
// atlas texture as glyphs arrive, and only the objects added here survive a reimport.
// `atlasTextures` is a public `Texture2D[]`; `atlasTexture` is just its first element, so
// adding that alone drops every atlas past the first.
foreach (var tex in fa.atlasTextures)
    AssetDatabase.AddObjectToAsset(tex, fa);
AssetDatabase.AddObjectToAsset(fa.material, fa);
fa.material.mainTexture = fa.atlasTexture;             // re-link explicitly
EditorUtility.SetDirty(fa);
AssetDatabase.SaveAssets();
```

The reason this one is worth looping rather than trusting: the first atlas is always there, so
`atlasTexture` alone looks correct on the day it is written and stays correct until the character
set outgrows 1024². Then the font goes partly blank and the builder is weeks behind you.

> **The in-memory instance is not the evidence.** `fa.material != null` and `fa.atlasTextures.Length`
> answer from the object you are still holding and stay true whether or not a single one of those
> objects reached the asset. Only `AssetDatabase.LoadAllAssetsAtPath(dst)` reads the file.

```csharp
// Returns UnityEngine.Object[].
var onDisk = AssetDatabase.LoadAllAssetsAtPath(dst);
// Expect the TMP_FontAsset, one Material, and one Texture2D per entry in fa.atlasTextures.
```

A font asset whose atlas has not overflowed reads back as **3 objects — 1 font asset, 1 material,
1 texture** — with `isMultiAtlasTexturesEnabled` true on a Dynamic asset and
`atlasTextures.Length == 1`, and `atlasTexture` alone passes that check too.
The loop matters once `atlasTextures.Length > 1`: the count on disk must then rise with it. The
bug is dormant until it is not.

Sampling 40 / padding 4 (10%) / 1024 atlas / Dynamic / multi-atlas `true` is the same set of
numbers `unity-game-ui` derives for CJK. Two values the call does **not** set and nobody checks
until they bite:

- **`m_Scale` must be exactly 1.** Anything else silently rescales every size derived from a
  viewing-distance calculation. It reads as "the design is a bit off", not as a bug.
- **`Clear Dynamic Data On Build` on.** Otherwise every glyph baked into the atlas while you were
  testing in the Editor ships inside the player. Note this is about what ships, not about the
  working tree — see §5.

## 3. Fallbacks are a safety net, not the language plan

Register every face on every other face's fallback table — TMP's lookup is cycle-safe, so the
mutual arrangement is fine:

```csharp
// Fallback(a, b, c) => a.fallbackFontAssetTable = new List<TMP_FontAsset> { b, c };
Fallback(sc, tc, jp);  Fallback(tc, sc, jp);  Fallback(jp, sc, tc);
```

…and then never let that chain answer the question "which language is this text". Worked example,
from one game's UI string tables:

| | Distinct characters used | Absent from Noto Sans SC | Absent from Noto Sans TC |
|---|---|---|---|
| zh-Hant table | 335 | **0** | — |
| zh-Hans table | 334 | — | **47** |

So an SC-primary build with a TC fallback shows **no tofu at all** for Traditional Chinese and
renders every Traditional string in Simplified glyph shapes — a bug reviewers see immediately,
screenshots hide, and assertions cannot reach. Note the asymmetry: the 47 Simplified characters
absent from TC are the only place a wrong primary can announce itself, and the mutual chain below
resolves even those. **"No tofu" is not evidence the chain is right.**

The fix is a per-locale primary chosen at label-construction time (`FontFor(locale)`: zh-Hant → TC,
ja → JP, else SC), with the mutual chain kept only for genuinely missing glyphs. All faces in the
chain must share the same padding : sampling ratio, or one line renders at two stroke weights.

This is a different question from the mixed Latin + CJK structure in `unity-game-ui` →
`reference/text-and-cjk.md` (a static Latin primary with a dynamic CJK fallback, chosen to bound
atlas memory). That structure answers *which script*; it does not answer *which region*, and only
the primary can.

A related trap, same shape: **a CJK font that advertises a language is not a font for that
language.** `NotoSansSC-Regular.otf` declares `en ja zh-cn zh-sg zh-tw`; `NotoSansJP-Regular.otf`
declares only `en ja`. Read those declarations off the files with fontconfig
(`fc-query --format='%{lang}\n' <font>`) rather than assuming — but the declaration only tells you
coverage, and coverage was never the problem.

## 4. Tofu triage, in the order that costs least

1. **Check the font file's size on disk.** `.otf` / `.ttf` in Git LFS come out of a clone made
   without LFS as short pointer text files rather than fonts. The builder then produces empty font
   assets and the built app is tofu everywhere — **with no error anywhere in the pipeline.**
2. **Is the theme/table font reference null?** Null → built-in Liberation Sans → tofu for every
   CJK glyph. See the ordering rule in §1.
3. **One tofu box, everything else fine?** That is a call site that built its text outside the
   factory that assigns the per-locale font (a bare `AddComponent<TextMeshProUGUI>()` gets TMP's
   default font). It is not a broken font asset. Route every label through one construction point.
4. **Was it fine and then went blank after a reimport?** The atlas and material were not added as
   sub-assets — SKILL.md §3.
5. **One character at a visibly different stroke weight inside a line** is the fallback chain doing
   its job. Correct behaviour, not a render bug — unless the ratio rule in §3 was broken.

## 5. The font asset will be modified after every Editor run. Decide what you do about it

A dynamic atlas rasterises whatever glyphs got displayed, so `Assets/Fonts/<Face> SDF.asset` shows
up in `git status --short` after **every** `-batchmode -executeMethod` call and **every** PlayMode
run that rendered CJK text. Each face grows from ~202 KB to 1.3–1.6 MB (about 7×) over a day of
Editor sessions, as text YAML (LFS policy lives in `unity-new-project` →
`reference/version-control-setup.md`; the decision lives here).

These `.asset` files are not LFS — `git check-attr filter` returns `unspecified` for them,
because only `*.otf` / `*.ttf` are LFS-filtered. So the churn lands in the *diffable* half of the
repo as an unreviewable multi-megabyte diff, and what gets committed depends on which screens the
last test run happened to visit.

Two honest answers:

- **Revert before every commit**, as a fixed pre-commit step:
  ```bash
  git checkout -- "Assets/Fonts/NotoSansSC-Regular SDF.asset" \
                  "Assets/Fonts/NotoSansTC-Regular SDF.asset" \
                  "Assets/Fonts/NotoSansJP-Regular SDF.asset"
  git add -A
  ```
  Cheap, and it keeps the committed atlas at whatever deliberate bake you last made.
- **Bake a static atlas for the shipped build** — trades repo churn for a fixed glyph set, which
  means every string that can ever appear must be known at bake time. Before relying on it, test
  every string that can appear against the baked glyph set.

What does **not** solve it: `Clear Dynamic Data On Build`. It acts at build time, and the churn
comes from ordinary Editor and PlayMode runs, which is where the dirty working tree appears.

## 6. Where the font files themselves come from

System fonts are the tempting answer and the wrong one to ship: macOS PingFang and Hiragino, and
the Windows CJK faces, are **not redistributable**, so they are not a legitimate stopgap for a
missing font — and a build that silently substitutes one has swapped a clear failure for a licence
problem. Ship an open-licensed family instead — for example the Noto Sans CJK subset OTFs from the
`notofonts/noto-cjk` repository (`Sans/SubsetOTF/{SC,TC,JP}/NotoSans{SC,TC,JP}-Regular.otf`) plus
the SIL OFL 1.1 text, fetched into `Assets/Fonts/`:

| File | Bytes |
|---|---|
| `NotoSansSC-Regular.otf` | 8,331,336 |
| `NotoSansTC-Regular.otf` | 5,683,368 |
| `NotoSansJP-Regular.otf` | 4,533,028 |
| OFL licence text | 4,301 |

Two consequences that are cheap on day one and expensive later: `*.otf` belongs in LFS from the
**first** commit, and the licence needs an entry on whatever About / credits screen the game ships.

For development only, named system fonts work as a stopgap: `zh-Hans` → Microsoft YaHei
(`msyh.ttc`); `ja` → MS Gothic (`msgothic.ttc`); `ko` → Malgun Gothic (`malgun.ttf`). Shipping one
is the licensing problem above, not a technical one. On device, `Dynamic OS` mode resolves against
the platform's own fonts instead — Android `NotoSans`, iOS `PingFang` — and iOS uses a **different
family per CJK language**, so one setting covering zh/ja/ko needs checking on hardware.
