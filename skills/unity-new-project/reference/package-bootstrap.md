# Installing packages headlessly — and the deadlock that makes it silently do nothing

> Part of the `unity-new-project` skill. This file is the one thing that turns a correct
> package-install script into a silent no-op.

## The `-quit` deadlock

`Client.Add`, `Client.AddAndRemove` and `Client.SearchAll` are **asynchronous**. The returned
`Request` only completes on a later `EditorApplication.update` tick, because the UPM child
process marshals its result back through the Editor's main-loop pump.

Two ways to break that, and both fail without an error:

> **Busy-waiting deadlocks.** `while (!req.IsCompleted) { }` blocks the main loop — which is the
> thing that would have completed the request. It hangs until the timeout kills it, and the
> stack trace points at your loop rather than at the cause.

> **`-quit` returns before the work happens.** The Editor exits the moment your
> `-executeMethod` target returns, which is *before* the first update tick. Exit code 0, empty
> log, no packages. This is the failure that reads as "the script ran fine but nothing
> installed".

**A/B it yourself** — same script, same project, one flag different. The method hooks
`EditorApplication.update` and logs from the completion callback:

```
Unity -batchmode -quit -projectPath . -executeMethod PackageProbe.RunAsync
    entered RunAsync()
    RunAsync() returning — update hooked, request NOT complete yet
    (nothing further)                                     exit 0

Unity -batchmode       -projectPath . -executeMethod PackageProbe.RunAsync
    entered RunAsync()
    RunAsync() returning — update hooked, request NOT complete yet
    COMPLETED  status=Success  packages=49                exit 0
```

> **Both runs exit 0.** That is the whole danger: the exit code is identical whether the work
> happened or not, so nothing downstream can tell. Assert on the manifest, never on the code.

So: **do not use `unity run` for package installs.** Invoke the Editor binary directly, without
`-quit`, and let the script own its own exit.

## The shape that works

`Assets/Editor/ProjectBootstrap/PackageInstaller.cs`:

```csharp
static AddAndRemoveRequest _request;
static double _deadline;

public static void Install() {                    // -executeMethod …Install   (NO -quit)
    _request  = Client.AddAndRemove(packagesToAdd: PackagesToAdd, packagesToRemove: PackagesToRemove);
    _deadline = EditorApplication.timeSinceStartup + 600;
    EditorApplication.update += Poll;             // returning here does NOT end the job
}

static void Poll() {
    if (_request == null) return;
    if (!_request.IsCompleted) {
        if (EditorApplication.timeSinceStartup > _deadline) {
            EditorApplication.update -= Poll;
            Debug.LogError("[PackageInstaller] timed out");
            EditorApplication.Exit(2);
        }
        return;
    }
    EditorApplication.update -= Poll;
    if (_request.Status == StatusCode.Success) {
        Debug.Log($"[PackageInstaller] resolved: {string.Join(", ", _request.Result.Select(p => $"{p.name}@{p.version}"))}");
        EditorApplication.Exit(0);
    } else {
        Debug.LogError($"[PackageInstaller] {_request.Error?.message}");
        EditorApplication.Exit(1);
    }
}
```

`EditorApplication.Exit(code)` both terminates the Editor and sets the exit code — that is why
no `-quit` is needed. Exit convention: `0` resolved, `1` UPM error, `2` timed out.

**One `AddAndRemove` beats a loop of `Add`.** It resolves the whole set in a single pass, which
is faster and cannot leave the manifest half-applied if one id is wrong.

## Running it

```bash
ED=$(unity editors path "$VERSION" --format json \
     | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['path'])")
# macOS: $ED may be a directory containing Unity.app, or the .app itself — handle both
UNITY_BIN="$ED/Unity.app/Contents/MacOS/Unity"
[ -x "$UNITY_BIN" ] || UNITY_BIN="$ED/Contents/MacOS/Unity"
# Linux: $ED/Editor/Unity     Windows: $ED/Editor/Unity.exe
"$UNITY_BIN" -batchmode -projectPath "$PROJECT" -executeMethod ProjectBootstrap.PackageInstaller.Install -logFile -
```

`-logFile -` streams the Editor log to stdout — without it you cannot see `[PackageInstaller]`
or the UPM error, and the run is a bare exit code. **`unity logs` will not help here**: it reads
the Hub log, not this Editor's.

## Verify — do not infer, and manifest.json is only half of it

```bash
echo "exit=$?"
cat "$PROJECT/Packages/manifest.json"          # the REQUEST: every id you asked for present?
grep -A6 '"<package id>"' "$PROJECT/Packages/packages-lock.json"   # the RESULT: resolved version/hash
ls "$PROJECT/Library/PackageCache" | grep <package id>             # what was actually unpacked
```

Exit 0 means the script reached `Exit(0)`. **`manifest.json` records what you asked for; it does
not tell you what compiled.** For a git dependency the difference is the whole point: the
manifest holds `com.<vendor>.<pkg>@https://…git?path=unity-package#v4.3.1`, while
`packages-lock.json` holds the resolved commit —

```json
"com.<vendor>.<pkg>": { "source": "git", "version": "https://…#v4.3.1",
                        "hash": "a28138a44d3637c4333e8728ec63b699b5b3bba5" }
```

— whose prefix must match the commit the tag points at. Check all three after any install or tag
bump.

Corollary for a **tag bump**: three places change together — the version string held as a C#
constant in the installer, `Packages/manifest.json`, and `Packages/packages-lock.json`. If the
constant and the manifest disagree, whichever ran last decides what resolves — which is why the
three move in one commit.

## Private git dependencies: credentials decide whether this works at all

A private UPM dependency is consumed as a URL, so package resolution is a `git` operation with
whatever credentials the machine has — nothing Unity can help with:

```
"com.<vendor>.<pkg>": "https://github.com/<org>/<repo>.git?path=unity-package#v4.3.1"
```

A machine can resolve it **non-interactively over https (an osxkeychain credential helper, say)
and not at all over SSH**, so check which transport resolves:

```bash
git ls-remote https://github.com/<org>/<repo>.git >/dev/null && echo "resolvable"
```

Prove that **before** running the installer on any new machine or CI runner, and give CI an
https read token rather than a deploy key.

> **The failure does not look like a package failure.** With the dependency unresolvable, the
> whole project fails to compile, and every downstream command reports its own symptom instead:
> test runs produce *no results file* (with exit 0 — see the exit-code trap above). If a fresh
> clone "cannot run its tests", check `git ls-remote` on the dependency URL before reading a
> single test log.

Pinning rule for the URL itself is in `SKILL.md` §3: an annotated tag, never a branch, and note
the `?path=` form for a package that lives in a subfolder of the repo.

## When a *fresh* template project does not compile, suspect the template

Creating a project from the **`universal-2d`** template on Unity 6000.4 produces project-wide
compile errors — the template's locked package versions (collab-proxy / inputsystem / timeline /
shadergraph) are stale for that editor and its `com.unity.modules.*` list is incomplete.

The fix is to replace `Packages/manifest.json` wholesale with a set known to compile on the
*same* editor version, and to delete the 2D packages the game does not use (`2d.animation`,
`psdimporter`, `aseprite`, `spriteshape`) rather than leave them to resolve. A package set known
to compile on Unity 6000.4:

| Package | Version |
|---|---|
| `com.unity.collab-proxy` | 2.12.4 |
| `com.unity.inputsystem` | 1.19.0 |
| `com.unity.timeline` | 1.8.12 |
| `com.unity.test-framework` | 1.6.0 |
| `com.unity.ugui` | 2.0.0 |
| `com.unity.render-pipelines.universal` | 17.4.0 |
| `com.unity.localization` | 1.5.13 |

Treat that table as *evidence that a working set exists for this editor*, not as a list to copy
into a different editor version — the point is the diagnosis: **a template's manifest is a
starting guess, not a working configuration.** This is the one situation where reading
`manifest.json` before anything else is right, and it is also the one situation where replacing
it wholesale beats `Client.AddAndRemove` — after which you re-open the Editor and let UPM
rewrite the lockfile.

## Two adjacent scripts, one of which may use `unity run`

- `Client.SearchAll()` / `Client.Search(id)` are **also async** — same poll-and-exit shape, same
  headless invocation. Use them to confirm an id exists rather than guessing at one.
- `AssetDatabase.Refresh(ForceUpdate)` + `SaveAssets()` is **synchronous**, so it is safe under
  `unity run` and the injected `-quit` does no harm. This is how you generate `.meta` files
  headlessly after a script has written `.cs` or asset files — and **every `.cs` and asset must
  be committed together with its `.meta`**.

## Never edit `manifest.json` by hand

Hand-editing skips resolution: the lockfile goes stale, transitive dependencies are not pulled,
and the first person to open the project gets a resolve error with no obvious cause. Let the
API write it.

Registry ids can be confirmed from a terminal without an Editor, but **only for an id you
already know** — there is no full-text search endpoint (`-/v1/search` returns 404):

```bash
curl -fsSL https://packages.unity.com/com.unity.cinemachine \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['dist-tags']['latest'])"
```

The `-f` matters: without it a 404 page is fed to the parser and you get a JSON error instead of
a clear "no such package".

> **A 404 does not always mean the id is wrong.** Built-in packages are resolved locally and are
> not on the registry at all — `com.unity.2d.sprite` returns 404 while installing perfectly well
> and reporting `"source": "BuiltIn"`. Use the registry to confirm a *registry*
> package's latest version, not to decide whether an id exists.
