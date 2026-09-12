# String tables, key parity, and which locale the game actually picks

> Part of the `unity-localization` skill. Fonts are `reference/font-pipeline.md`; layout that
> breaks on a longer translation is `reference/per-locale-layout.md`.

Locale set throughout: zh-Hans (the source of truth), zh-Hant, ja, en.

## 1. A key that exists in one table only is the default failure

It does not crash and it does not tofu: the UI renders the **raw key**, which reads as deliberate
English rather than as a bug. It survives review because the person reviewing reads the source
locale.

The guard is one EditMode test, and the thing that makes it hold is that it iterates the **locale
list the app itself iterates**, not a hardcoded pair. A test that starts as
`foreach (var loc in new[] { "zh-Hans", "zh-Hant" })` has to be rewritten the moment a third
locale arrives. Write it against the list from the start and a new locale is covered by tests that
already exist.

```csharp
// Read each locale's raw table, compare key SETS against the source locale.
var source = KeysOf(SourceLocale);
foreach (var loc in AllLocales) {
    if (loc == SourceLocale) continue;
    var keys = KeysOf(loc);                       // regex "key":\s*"([^"]+)" over the raw file
    Assert.IsTrue(keys.SetEquals(source),
        $"{loc}: missing {First(5, source.Except(keys))}; extra {First(5, keys.Except(source))}");
}
```

Print the first handful of keys on **each** side, not just a count — "missing 3" sends someone
diffing 200-line files, `missing: {'common.back_glyph'}` is fixed in seconds. The same output
catches a key referenced in code before it exists in any table — the usual slip in a UI rewording.

Two companion tests that earn their place:

- a hardcoded list of the UI keys the shell cannot run without (back, confirm, pause, …) asserted
  present in **every** table, so a screen added with strings in one language fails fast;
- one `<contentId>.title` per locale for each item in whatever content catalog the game has, so
  adding content with a name in one language only is also red.

**Pre-flight, before Unity is started at all** — a one-liner that costs nothing and catches the
common case:

```bash
for f in Assets/Resources/Localization/*.json; do
  printf '%s %s\n' "$(basename "$f" .json)" "$(grep -c '"key"' "$f")"
done
```

Equal counts are not proof of equal key sets, but unequal counts are proof of a problem, and you
get the answer in a second instead of a minute.

## 2. If the Localization package is not usable yet: a JSON table that can migrate later

A project that cannot yet verify the package in its environment can ship its own tables and keep
the migration cheap — provided two shapes are right.

**The file shape is forced by `JsonUtility`, which cannot deserialize a top-level dictionary.**
An array of entries is the only thing that round-trips:

```json
{ "entries": [ { "key": "common.back", "value": "返回" } ] }
```

```csharp
[Serializable] class Entry { public string key, value; }
[Serializable] class Table { public List<Entry> entries; }
// Resources.Load<TextAsset>("Localization/" + Locale) → JsonUtility.FromJson<Table>(...) → cache
```

Behaviour worth pinning deliberately rather than discovering: duplicate keys last-wins silently,
empty keys are skipped, and a missing key returns `fallback ?? key` rather than throwing — a
throw here turns a translation gap into a crash on a device.

**The migration seam is one delegate, and its contract is "null means not found":**

```csharp
public static Func<string, string> Resolver;   // consulted first; null result falls through
```

Point it at a String Table later and no call site changes.

> **The obvious Localization API breaks that contract.**
> `LocalizationSettings.StringDatabase.GetLocalizedString(table, key)` returns a **non-null**
> string on a miss — `"No translation found for '<key>' ..."` — which would be passed straight
> through to the UI as if it were a translation. Use
> `GetTable(name)?.GetEntry(key)?.GetLocalizedString()` so a miss is genuinely null and the JSON
> table stays a working safety net. The miss string is the package's documented behaviour — check
> it on your package version before relying on the fallback.

## 3. Locale detection: three Chinese values, and a preference that looks like a bug

```csharp
Locale = Application.systemLanguage switch {
    SystemLanguage.ChineseTraditional => "zh-Hant",
    SystemLanguage.ChineseSimplified  => "zh-Hans",
    SystemLanguage.Chinese            => "zh-Hans",   // ← the one everybody forgets
    SystemLanguage.Japanese           => "ja",
    _                                 => "en",        // not the source locale
};
```

- **`SystemLanguage.Chinese` is a real value** distinct from the two specific ones. Miss it and
  some Chinese devices fall through to the default.
- **Unmatched falls back to `en`, not to the project's source locale.** English is more useful to a
  non-CJK player than Simplified Chinese is.
- **Store "follow system" as the empty string**, with any non-empty stored value meaning an
  explicit choice. That is what makes "never chosen" distinguishable from "chose the language that
  happens to match the system".
- **A stale stored preference makes the whole feature look dead.** A machine that saved a
  preference earlier (say `zh-Hant`) never follows the system language again, so follow-system
  looks unimplemented. Clear or re-select the preference before testing detection, on every
  machine that has ever run the game.
- **Make the language source injectable** (`static Func<SystemLanguage> SystemLanguageSource`) so
  EditMode tests can pin a device language instead of asserting against the machine they run on.

## 4. zh-Hans and zh-Hant are different vocabularies, not a character conversion

Never machine-convert one Chinese table into the other. The entry a converter can never catch is
Traditional-Chinese *wording* merely written in simplified characters: every character is already
correct. Audit the zh-Hans table key by key for pairs like these:

| Written as (Traditional wording) | Mainland register |
|---|---|
| 纪录格式 | 记录格式 |
| 目前 | 当前 |
| 维持 | 保持 |
| 传送 | 发送 |
| 触控输入 | 触摸输入 |

Pairs that are correctly regional (zh-Hans/zh-Hant), for contrast with what the audit looks for:
设置/設定, 保存/儲存, 粘贴/貼上, 数据/資料, 设备/裝置, 内置/內建, 连接/連線, 算法/演算法, 密钥/金鑰.

Write each table in its own regional register (zh-Hans = mainland, zh-Hant = Taiwan). The same
rule applies to any per-locale text the game sends to a service — a system prompt or a report
template shipped per language is a string table with the same failure mode.

## 5. Moving to the Localization package

Three rules that are cheap to encode up front and expensive to discover:

- **Nothing an Asset Table references may live under `Assets/Resources/`.** Tables load through
  Addressables; a `Resources/` asset raises `OperationException: Failed to load sub-asset` **at
  runtime, with no build-time error.** This is why font assets stay in `Assets/Fonts/` even when
  putting them in `Resources/` would be convenient.
- **Add the `Unity.Localization` assembly reference to whichever asmdef your UI lives in**, or the
  code simply will not see the API.
- **Any table or font-reference change needs `AddressableAssetSettings.BuildPlayerContent()`** or
  the build keeps serving the previous content.

Budget for the dependency weight before promising the migration: `com.unity.localization` pulls in
`com.unity.addressables` and `com.unity.nuget.newtonsoft-json`. The Addressables version it
requests is a floor (e.g. 1.25.0), and what resolves can be a major version above it — read the
resolved versions off `Packages/packages-lock.json`.

## 6. When the Localization package is in

Sections 1–4 assume the package is not usable yet. This one is the other side: `com.unity.localization`
resolved, its Editor API reachable, and the handful of places that API is quietly hostile.

### 6.1 Two presence checks, answering two different questions

`Packages/manifest.json` records what was **requested**. `Packages/packages-lock.json` records what
Unity actually **resolved** — plain JSON, no Editor, no async call, so it is the cheap check and the
correct one.

The lock file can be current before the assemblies are loadable, so the second check is the one that
gates code:

```csharp
return System.Type.GetType(
    "UnityEngine.Localization.Settings.LocalizationSettings, Unity.Localization") != null;
```

Until it returns true, every call in this section fails as an unresolved type — which reads as a
compile mistake, not as a missing package. Adding the package itself is a project change:
`unity-new-project` → `reference/package-bootstrap.md`.

### 6.2 Find or create the settings asset — and scope every `FindAssets`

```csharp
var hits = AssetDatabase.FindAssets("t:LocalizationSettings", new[] { "Assets" });
```

`AssetDatabase.FindAssets` has exactly **two** overloads: the
filter alone, and the filter plus search folders. The one-argument form searches the whole project
**including read-only packages**, so it can return an asset under `Packages/` — which you then point
the project at, dirty, and cannot save.

With only the second argument different, an unscoped `t:Scene` also returns scenes under
`Packages/` — on a project with Addressables installed, its test fixtures among them — which you
then try to open and save. Nothing warns; the unscoped call simply hands back other people's
assets. So:

1. Scoped `FindAssets`. If there is a hit, load it.
2. Otherwise `ScriptableObject.CreateInstance<LocalizationSettings>()` and
   `AssetDatabase.CreateAsset(settings, "Assets/Localization/LocalizationSettings.asset")`.
3. `LocalizationEditorSettings.ActiveLocalizationSettings = settings` — readable **and** writable.
4. Add the locales the project ships with through
   `LocalizationEditorSettings.AddLocale(locale, createUndo)`.

### 6.3 Populate by locale code, never by array order

The order of the locale list is not a contract. Match on `locale.Identifier.Code` against your own
data's key instead — `Locale.Identifier` is a `LocaleIdentifier` carrying a `Code` property.

Zipping a locale list against an input array by index is the failure this prevents, and it is the
worst kind: every table fills, nothing throws, and each language holds a plausible string from the
wrong locale. For an Asset Table, address the entry by the asset's GUID —
`table.GetEntry(sharedId) ?? table.AddEntry(sharedId, guid)`.

### 6.4 A write nobody saved reads back correctly for the rest of the session

After changing a collection, in this order:

1. `EditorUtility.SetDirty(collection)` **and** `EditorUtility.SetDirty(collection.SharedData)` — the
   shared key list is its own asset, and dirtying only the table loses the keys.
2. `LocalizationEditorSettings.EditorEvents.RaiseCollectionModified(sender, collection)` — the
   signature is `(object sender, LocalizationTableCollection collection)`, on the static
   `EditorEvents` property of type `LocalizationEditorEvents`. Skip it and the Localization windows
   keep showing pre-edit state until something forces a reimport, which reads as "my script did
   nothing".
3. `AssetDatabase.SaveAssets()`, once, at the end.

Skip step 3 and the entry reads back correctly all session and is gone when the Editor closes —
the same trap `SetDirty` sets everywhere else in the Editor API.

> `CreateStringTableCollection` takes a **directory**, not an asset path.

The overloads:
`CreateStringTableCollection(string tableName, string assetDirectory)` and
`(string tableName, string assetDirectory, IList<Locale> selectedLocales)`, with
`CreateAssetTableCollection` the same pair. Handing it `Assets/Localization/UIStrings.asset` where
`Assets/Localization` was wanted is the usual first error.

### 6.5 Three ways to change locale, for three different moments

| Moment | Use | API detail |
|---|---|---|
| Previewing a language while authoring | `Window > Asset Management > Localization Scene Controls` | the `MenuItem` on `UnityEditor.Localization.UI.SceneControlsWindow.ShowWindow`; the type is an `EditorWindow` in `Unity.Localization.Editor` |
| Runtime, including the game's own language menu | assign `LocalizationSettings.SelectedLocale` | static property, readable and writable |
| Which locale a fresh launch picks | a startup locale selector on the settings asset; `SpecificLocaleSelector` pins one | public, implements `IStartupLocaleSelector` |

Preview is Editor-only. It answers "does this screen look right in ja", never "what does the player
get on first launch" — those are different questions and the second one is the selector's.

> **A hand-rolled current-language variable is the thing to refuse.** An in-game language menu is
> expected and fine, as long as it sets `SelectedLocale` and lets the package propagate the change.
> A debug dropdown that tracks its own field and swaps strings itself leaves every
> package-bound label on the old locale, and the disagreement looks like a caching bug.

### 6.6 Binding a label, and the listener that is wired but asleep

Use the public `UnityEngine.Localization.Components.LocalizeStringEvent`, with `StringReference` and
`OnUpdateString` as properties and `RefreshString()` as a method. Its Editor-side convenience
counterpart is **internal**, so reaching it means routing around access control for an API Unity
makes no compatibility promise about.

Set `StringReference` to the table entry, then wire `OnUpdateString` to the label's `text` property.
A property setter has no method group to take a delegate from in C#, so name it instead:

```csharp
// set_text is public on both families:
// TMPro.TMP_Text.set_text(string) and UnityEngine.UI.Text.set_text(string).
var setText = (UnityAction<string>)System.Delegate.CreateDelegate(
    typeof(UnityAction<string>), label, "set_text");

// Clear first, or a second run stacks a duplicate call on the same event.
for (int i = lse.OnUpdateString.GetPersistentEventCount() - 1; i >= 0; i--)
    UnityEventTools.RemovePersistentListener(lse.OnUpdateString, i);

UnityEventTools.AddPersistentListener(lse.OnUpdateString, setText);

var index = lse.OnUpdateString.GetPersistentEventCount() - 1;
lse.OnUpdateString.SetPersistentListenerState(
    index, UnityEngine.Events.UnityEventCallState.EditorAndRuntime);
```

Naming a public member is ordinary reflection. What is not ordinary is the alternative some scripts
reach for — poking `m_MethodName`, `m_Mode` and `m_PersistentCalls` through `SerializedObject`.
Those are private serialized names carrying no compatibility promise, and they buy nothing:
`AddPersistentListener` writes the identical call.

> **`AddPersistentListener` leaves the call at `RuntimeOnly`.** The binding is correct and dormant:
> right in a build, invisible while authoring.

`UnityEngine.Events.UnityEventCallState` has exactly three values — `Off`, `EditorAndRuntime`,
`RuntimeOnly` — and the fix is public API,
`UnityEventBase.SetPersistentListenerState(int index, UnityEventCallState state)` returning `void`.
`UnityEditor.Events.UnityEventTools.AddPersistentListener` has **six** overloads:
one taking a bare `UnityEventBase`, one taking `UnityEvent` + `UnityAction`, and generic forms for
one through four arguments — the `UnityAction<string>` above binds the arity-1 form.

**Check it:** change the locale in Edit mode; a label that does not move is still `RuntimeOnly` —
set `EditorAndRuntime` and re-read `GetPersistentListenerState(i)`, then read it again after saving
and reopening the scene or prefab.

### 6.7 Four read-backs, because a wired binding and a live one look identical

Everything here is public API on the event (all five persistent-listener methods are public on
`UnityEventBase`), so none of it touches serialized fields.

| What it proves | Read | Expect |
|---|---|---|
| Anything at all got added | `GetPersistentEventCount()` | above zero |
| The call names this label's setter | `GetPersistentTarget(i)` / `GetPersistentMethodName(i)` | this component; `set_text` |
| Authoring-time locale changes reach it | `GetPersistentListenerState(i)` | `EditorAndRuntime`, not `RuntimeOnly` |
| The label moves when told to | `RefreshString()` | rendered text changes |

Four checks, not one. The first three can each pass on a binding that never runs: a count is only
evidence that *something* was added, and a `RuntimeOnly` call is a perfectly correct build-time
binding that simply does nothing while you are looking at it. The state read is what distinguishes
dormant from broken, and `RefreshString()` is what proves the pipe is connected end to end. The worst outcome here is not an unlocalised label: it is a
label carrying a complete, correct-looking binding that never runs, because that one passes
inspection.

### 6.8 Table completeness — and what counts as a pass

A key that exists with an empty value is the usual gap, and to this check it is indistinguishable
from a key that is absent — both render as untranslated, and both belong in the same report. What
the package itself puts on screen for a miss is §2's note; the check below does not depend on it.
Enumerate instead of eyeballing.

```csharp
var gaps = new System.Collections.Generic.List<string>();
var examined = 0;

foreach (var col in UnityEditor.Localization.LocalizationEditorSettings.GetStringTableCollections())
foreach (var key in col.SharedData.Entries)
foreach (var table in col.StringTables)
{
    examined++;
    var entry = table.GetEntry(key.Id);
    // Missing and present-but-empty both render as untranslated in game.
    if (entry == null || string.IsNullOrWhiteSpace(entry.Value))
        gaps.Add($"{col.TableCollectionName} / {table.LocaleIdentifier.Code} / {key.Key}");
}

// Zero examined is not a pass — it means no collection, or a collection with no locale tables,
// so the check looked at nothing. Say that distinctly instead of letting it read as success.
if (examined == 0)
    return "INCONCLUSIVE: no table entries examined. Either no String Table Collection exists, "
         + "or the collection has no locale tables. Fix that before trusting this check.";

return gaps.Count == 0
    ? $"COMPLETE: {examined} entries examined, no gaps"
    : $"GAPS ({gaps.Count} of {examined} examined):\n  " + string.Join("\n  ", gaps);
```

On a project with the package and no collections it returns `INCONCLUSIVE` — the case the third
state exists for. Before trusting a `COMPLETE`, blank one entry on purpose and confirm it comes back
under `GAPS`.

**Report the gaps; do not close them with the source language.** Some are decisions rather than
mistakes — a locale nobody asked to translate, a key deliberately identical across languages.
Filling those with English hides the decision and makes the table look done. List them and let the
person who owns the strings say which are intentional.

### 6.9 The strings no scene walk can see

Authored text sits on components. Text composed in code — `scoreLabel.text = $"EXP {value}"` — exists
nowhere at edit time, so no component scan reaches it, and it is the string that survives a
"localisation finished" pass and shows up in a screenshot from another locale.

```bash
# Assignments and SetText calls carrying a string literal.
grep -rnE '\.text\s*(=|\+=)\s*\$?"|SetText\(\s*\$?"' --include='*.cs' Assets/
```

Four literal forms are in scope — plain, interpolated, concatenated, `+=` — plus `SetText`. Two
shapes are out on purpose: `label.text = someVariable` has no literal to extract, and
`label.text = Localize("KEY")` is already routed. Knowing exactly what it declines to count is what
makes the calibration below readable.

**Its blind spot is a literal held in a variable or `const` declared elsewhere.** Calibrate before
trusting the count: run a loose `\.text\s*(=|\+=)\s*[A-Za-z_]` beside it — e.g. this pattern finding
**10** sites where the loose one finds **91**. Most of that 91 is correctly
ignored — variables and already-routed calls — but a low literal count next to a large assignment
count is the signal to grep that file's string literals too rather than declare the sweep complete.

Report it as a table, not a total: one row per site the scan found, what happened to it, and a
reason on every row that stayed. "Localised 24 strings" with nine found sites left untouched is the
exact shape of a pass that looks finished and is not.
