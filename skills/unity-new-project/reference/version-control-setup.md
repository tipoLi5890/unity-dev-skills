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

## 5. Related

- Settings that this file's rules assume — `Force Text` serialization and `Visible Meta Files` —
  belong inside the re-runnable setup method, not in a wiki page: `reference/generated-assets.md`.
- Hosting choice (GitHub/GitLab + LFS vs UVCS vs local git) is in `SKILL.md` §2.
