---
name: unity-search
description: >-
  Turn "find", "where is", "which prefabs use", "what references X" into a
  Unity Search query — asset type filters, folders, labels, ref=
  relationships, scene component queries — show it, and optionally open the
  Search window in a live Editor. Load for "find all materials in Assets/UI",
  "what references this texture", "which scene objects have a Rigidbody",
  "show every Light in the scene", "what Unity Search query do I use", "open
  the Search window with that". Read-only: it never selects, moves or edits a
  result. Scripted asset audits and driving the Editor are unity-debug; a
  project-wide dependency graph is out of scope.
---

# unity-search — one query, shown before it runs

A request shaped like *find*, *locate*, *list*, *where is*, *which ones use*, *what references* has
one good answer: a single Unity Search query, written out, with a word about what it searches.

Two things happen every time, whether or not an Editor is reachable:

1. **The query is shown.** It is the part the reader keeps, pastes and edits.
2. **You say what it searches** — project assets, the loaded scenes, or both. The same `t:` prefix
   means a different thing on each side, so this is not decoration.

If a live Editor is there, opening the Search window with the query is a bonus, not the deliverable.

> **"This", "the selected one", "the current material" — with no name or path in the conversation,
> ask.** A guessed asset name produces a query that returns nothing, and an empty result reads as
> "there are none" rather than "you searched for the wrong thing".

## Load what the request needs

| The situation | Read |
|---|---|
| Anything past a bare `t:<type>` — folders, labels, references, expressions | `reference/query-patterns.md` §1–§3 |
| Mapping the user's wording onto a query shape | `reference/query-patterns.md` §4 |
| Opening the window, or an open attempt that failed | §Open it in a live Editor |
| The question is one Search cannot settle — shader properties, missing scripts, a full audit | §When Search cannot answer, then `unity-debug` → `reference/editor-control.md` |
| "Which assets does this change affect" — a diff question, not a find question | `unity vcs affected` in `unity-cli` → `reference/version-control.md` |
| The CLI is not installed, or no Editor answers | skill `unity-cli` |

## Building the query

Six rules cover almost everything; the tables are in `reference/query-patterns.md`.

- **Asset types are lowercase; scene component types are Unity type names.** `t:material`,
  `t:prefab`, `t:audioclip` for assets; `t:Light`, `t:Rigidbody`, `t:AudioSource` for what is in
  the loaded scenes.
- **Two types at once is a list:** `t:[material, texture]`.
- **Scope with `dir:`, label with `l:`, name with a bare keyword.** `t:prefab dir:Assets/Courier`,
  `l:Hazard`, `sentry`. Quote any path with a space.
- **Relationship words mean `ref=`.** "uses", "references", "depends on", "what would break":
  `ref=Lane_Asphalt`, `ref="Assets/Courier/Materials/Lane Asphalt.mat"`, or the expression form
  `t:prefab ref={t:texture}` when the other side is a whole type rather than one asset.
- **A name and a type combine:** `Sentry t:Rigidbody`.
- **One good query beats a long speculative one.** An unknown filter is treated as an ordinary
  word rather than rejected, so a malformed query comes back empty and looks like an answer.

> **An empty result is not proof of absence.** Widen once — drop the filter, keep the keyword —
> before reporting that nothing exists.

## The answer, always two lines

```text
Query: `t:material dir:Assets/Courier/UI`
Opened the Search window with it.
```

…or, when nothing was opened:

```text
Query: `t:prefab ref={t:texture}`
Paste it into the Search window.
```

An assumption gets a third line and nothing more: *"Read as the material's name; a path would be
exact."* Keep the rest out.

## Open it in a live Editor

Two preconditions: `unity status --format json` reports `state: "ready"`, and the Editor's command
catalogue carries `eval` (`unity command --detail compact`). Both come from the project having the
`com.unity.pipeline` package — that whole surface is `unity-cli`.

```bash
unity command eval 'const string q = @"t:material dir:Assets/Courier/UI";
var picked = new System.Collections.Generic.List<UnityEditor.Search.SearchProvider>();
foreach (var id in new[] { "asset", "scene" })
{
    var p = UnityEditor.Search.SearchService.GetProvider(id);
    if (p != null) picked.Add(p);
}
var ctx = picked.Count > 0
    ? new UnityEditor.Search.SearchContext(picked, q)
    : new UnityEditor.Search.SearchContext(UnityEditor.Search.SearchService.GetActiveProviders(), q);
UnityEditor.Search.SearchService.ShowWindow(ctx);
return "opened: " + q;' --format json
```

Four things that snippet is shaped by:

- **What `eval` compiles is a block of statements, not a source file.** No `using` directives (one is read
  as a resource-disposal statement), and every type fully qualified — a bare `SearchService` does
  not resolve. Confirm the flag spelling with `unity command eval --help` on your CLI version.
- **The query is a verbatim string**, so a double quote inside it is written twice:
  `@"ref=""Assets/Courier Run/Gate.prefab"""`.
- **Providers are filtered, not assumed.** `GetProvider` returns null for one that is not
  registered, and handing a null into the context throws; falling back to
  `GetActiveProviders()` keeps the window opening at all.
- **It opens a window and stops there.** No selecting, no pinging, no saving.

**Judge the result from `data.result.result` only.** An outer `success: false` or a
`COMMAND_FAILED` code means it did not open, whatever the exit line suggests — never report
"Opened the Search window" from an exit code. Three failures worth naming rather than retrying:

| What you see | Say |
|---|---|
| `UnityEditor.Search` does not resolve | This Editor may not expose the modern Search API — here is the query to paste |
| The Editor is running headless, with no windows | Hand over the query instead; whether a window can open at all in that mode is worth confirming on your version |
| More than one Editor is running | Re-run with `--project-path`, naming the project |

## When Search cannot answer

- **Material and shader properties.** `t:material Standard` narrows; it does not prove. A scripted
  audit is the honest answer.
- **Missing scripts**, and anything needing a per-component walk: a short `eval` script that
  enumerates and reports, not a query.
- **A full inventory** through `UnityEditor.AssetDatabase.FindAssets("t:Material", new[]{"Assets"})`
  — and **always pass the search-in folders**, because an unscoped call walks the whole project
  including packages. What that costs on a large project: `unity-audio` →
  `reference/mixer-routing.md`.
- **A project-wide dependency graph.** Out of scope; `ref=` answers one hop.

## Discipline

- **Show the query before claiming anything about results.** It is the reviewable artefact.
- **Never report a window as opened without the Editor's own return value.**
- **Ask rather than invent a name.** "This prefab" with no prefab in the conversation is a
  question, not a query.
- **Find and fix is two requests.** Run the find, show what it found, then stop and ask before
  anything touches a result.
- **State the limit in the same breath as the query** when Search can only narrow — an
  authoritative-looking query for a question it cannot settle is worse than no query.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Acting on results: select, rename, move, delete, re-import | Stop and ask; the Editor-side work is `unity-debug` |
| A scripted audit that has to be exhaustive or property-aware | `unity-debug` → `reference/editor-control.md` |
| Installing the CLI, connecting an Editor, the command catalogue | `unity-cli` |
| "Which assets does this change affect" across a diff | `unity-cli` → `reference/version-control.md` |
| Repository text search, build logs, package registries, menu or settings search | Not Unity Search's index — name the right tool and stop |
