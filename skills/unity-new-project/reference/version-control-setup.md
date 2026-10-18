# Version control for a Unity repo — the day-one file, and proving it worked

> Part of the `unity-new-project` skill. Everything here is cheap in the first commit and a
> history rewrite afterwards.

## 1. `.gitattributes` in the first commit

A day-one `.gitattributes`:

```gitattributes
# Unity YAML: keep text, merge with UnityYAMLMerge where configured
*.unity        text eol=lf merge=unityyamlmerge
*.prefab       text eol=lf merge=unityyamlmerge
*.asset        text eol=lf merge=unityyamlmerge
*.meta         text eol=lf
*.cs           text eol=lf diff=csharp
*.asmdef       text eol=lf
*.json         text eol=lf
*.md           text eol=lf
*.sh           text eol=lf

# Binaries via Git LFS (day one; retrofitting rewrites history)
*.png  filter=lfs diff=lfs merge=lfs -text
*.jpg  filter=lfs diff=lfs merge=lfs -text
*.psd  filter=lfs diff=lfs merge=lfs -text
*.aseprite filter=lfs diff=lfs merge=lfs -text
*.wav  filter=lfs diff=lfs merge=lfs -text
*.ogg  filter=lfs diff=lfs merge=lfs -text
*.mp3  filter=lfs diff=lfs merge=lfs -text
*.mp4  filter=lfs diff=lfs merge=lfs -text
*.ttf  filter=lfs diff=lfs merge=lfs -text
*.otf  filter=lfs diff=lfs merge=lfs -text
*.fbx  filter=lfs diff=lfs merge=lfs -text
```

`merge=unityyamlmerge` only does anything once each clone's `.git/config` points that merge
driver at the Editor's UnityYAMLMerge binary — the attribute alone is a declaration of intent,
not a working merge tool.

Two consequences people discover late:

- **`*.asset` is deliberately text, so it is deliberately *not* in LFS.** That is right for
  ScriptableObjects you want to diff, and it is a slow leak for the generated ones — see §3.
- **A clone without `git lfs install` gets pointer files.** Unity then reports the fonts and
  textures as corrupt, which reads as an asset bug rather than a checkout problem. (The
  pointer-vs-binary check in §2 confirms it in ten seconds.)

## 2. Verify the first binary-carrying commit actually used LFS

`git lfs ls-files --cached` **does not exist**:

```
$ git lfs ls-files --cached
Error: unknown flag: --cached
```

Inside a longer chained command that error is easy to miss, because the surrounding output still
looks plausible enough to move on — so run these two on their own:

```bash
git lfs ls-files | wc -l                                # working tree: how many files LFS owns
git show HEAD:Assets/Art/Shared/some_image.png | head -c 60   # what the COMMIT contains
```

An LFS-tracked blob prints `version https://git-lfs.github.com/spec/v1`; a file that slipped
past the filter prints binary noise (`\x89PNG…`). Do this once, on the first commit that adds
binaries. If it is wrong, fixing it before you push is `git rm --cached <path>`, re-add, and
`git commit --amend` (the raw blob stays in history otherwise); fixing it in a month is a history
rewrite plus everyone re-cloning.

## 3. The text-YAML exception grows: TMP SDF font assets

Font assets are `.asset` (Unity YAML), so the rule above keeps them out of LFS on purpose —
they need to stay mergeable. With **dynamic** TMP atlases the file is not static: every Editor
session that renders a new glyph bakes it into the atlas and dirties the asset.

With dynamic CJK faces (Noto Sans SC, TC and JP, say), each face can grow from ~202 KB to 1.3–1.6 MB
(about 7×) over a day of Editor sessions, as text YAML — in the diffable half of the repo.
Nothing breaks — but plan for it: decide whether those assets are committed after a deliberate
glyph bake or regenerated, and expect the diffs to be unreviewable either way. Switching a shipped
atlas from Dynamic to Static is the usual answer; that decision and the whole font pipeline belong
to `unity-localization`, not here.

## 4. Publishing an already-large offline repo to a remote

An offline Unity project with art and audio already in LFS publishes in three commands (a
private GitHub remote here):

```bash
gh repo create <owner>/<repo> --private --source=. --remote=origin --description "…"
git push -u origin main
git push origin --tags          # NOT covered by the previous line
```

The LFS objects go up with no extra LFS configuration, because LFS was already set up in
`.gitattributes` — which is the whole point of §1. Without `gh`, the same
thing is `git remote add origin <url>` after creating the empty repo in the host's UI.

Two things that bite:

- **Annotated tags created before the remote existed are not pushed by `git push`.** They need
  `git push origin --tags` (or `git push origin <tag>`), and their absence is silent.
- A release you already shipped can be tagged retroactively:
  `git tag -a v0.1.0 <sha> -m "…" && git push origin v0.1.0`.

## 5. An LFS budget, kept as a ledger

LFS storage on a hosted plan has a quota, and a day of asset imports can take most of it. A 3D
tennis game budgeted against a 1 GB free tier (check your plan's current figure in the host's
billing page; it is a number, not a feeling). What one day added:

| Import | LFS added |
|---|---|
| A purchased mocap pack (75 clips), as imported for the game | 105 MB |
| Each rigged character FBX with textures | about 9 MB |
| Two more LOD levels per character | 3.2 MB |
| Three venues | about 21 MB |
| Source files staged for the character pipeline (`.blend`, FBX, the vendor archive, image masters) | about 292 MB |

The rules that kept it inside the budget:

- **Every commit that adds binaries states its LFS cost** in the message or the hand-back
  (`git lfs ls-files -s` before and after), and the handoff keeps a running total.
- **Decimate before committing.** A racket from an image-to-3D tool arrived at 19,994 triangles;
  the pipeline cut it to 1,491 before export. The oversized source is regenerable and stays out of
  git (`unity-3d-models`).
- **Regenerable outputs are ignored, not stored.** Candidates, previews, raw generator output,
  pipeline `out/` folders and throwaway lab projects can all be rebuilt by a script; four
  converted clips (about 5 MB) were left out of git because the same inputs reproduce them byte
  for byte.
- **A push over a set size (300 MB here) waits for the person.** One agent declined to push
  about 318 MB because it included another agent's unpushed commits and a purchased pack whose
  licence was unconfirmed. That was the right call.

## 6. Pushing from a shared working tree

- **A push publishes every commit between `origin/main` and `HEAD`**, whoever made them. One
  agent's push published six commits by another. Look first:
  `git log origin/main..HEAD --format='%h %an %s'`.
- **A large first push can be declined by the host** (`! [remote rejected] main -> main
  (pre-receive hook declined)`). Here a plain retry went through with 318 MB of LFS; the cause was
  never confirmed. Retry once, then confirm the push landed with `git ls-remote origin main`
  matching `git rev-parse main`, rather than reading the absence of an error. If it keeps
  failing, push in smaller pieces (`git push origin <older-sha>:main` first).
- **A pre-commit hook usually checks the working tree, not the staged diff.** When several agents
  share one checkout, another agent's uncommitted changes fail the hook on your docs-only commit.
  Make the hook check what is staged: export the index with
  `git checkout-index -a --prefix="$tmp/"` and run the check there, or limit it to
  `git diff --cached --name-only`. Never `git stash` in a shared checkout: it takes the other
  agents' edits out from under them. Or give each agent its own worktree (`unity-cli` → `reference/version-control.md` §8). Do not `--no-verify` past it:
  once one agent bypasses, the hook no longer guarantees anything.

## 7. Purchased and borrowed material

- **Purchased assets go in a private repo only**, with a licence note beside them (what was
  bought, what the licence says about redistribution) and an open question in the handoff:
  "does the licence cover shipping this in the product?" until someone confirms it for release.
- **Never copy a paid tool's files or code into the repo**, even when its output is used; record
  which tool made an output instead.
- **A prior project used as reference is read-only.** Copy what you need in, with its origin noted;
  never write into it.

## 8. Related

- Settings that this file's rules assume — `Force Text` serialization and `Visible Meta Files` —
  belong inside the re-runnable setup method, not in a wiki page: `reference/generated-assets.md`.
- Hosting choice (GitHub/GitLab + LFS vs UVCS vs local git) is in `SKILL.md` §2.
