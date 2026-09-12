# Signing, versionCode, and the records that outlive the build

## The iron law

The keystore **is** the app's identity on the store. Lose the file or the password and you cannot
update that listing again, ever — the only route back is a new package name, which means a new
listing, zero installs and zero reviews. Backup is not housekeeping; it is the difference between
having an app and having had one.

- Keystore lives **outside the repository**, gitignored by pattern as well as by location.
- Backed up to at least two independent places, and the **password with it** — a keystore whose
  password is only in one machine's file is not backed up.
- On Play, the **upload key is not the app signing key** when Play App Signing is on. Read which
  one you are holding before deciding how catastrophic losing it is.

The full store-side discipline — keystore custody and store submission — is platform-shared: it is
the same for any engine that ships to Play. Unity adds nothing to it and exempts nothing from it.

```bash
keytool -genkeypair -v -keystore ~/keys/<app>.keystore \
        -alias <app> -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=<App>, O=<Org>, C=<CC>"
```

Generate the password rather than inventing one, and never type either onto a command line — it
lands in shell history and in the process table where anything on the machine can read it.

```bash
PASS="$(LC_ALL=C tr -dc 'A-Za-z0-9!@#%^_+=' < /dev/urandom | head -c 28)"
```

Run that in a plain shell, not inside the build script: `head` closes the pipe after 28 bytes, `tr`
dies of SIGPIPE, and under `set -o pipefail` the pipeline returns 141 — so the assignment fails and
`set -e` ends the script. That is trap 1 in `build-automation.md`.

## Credentials in a gitignored env file

```bash
# Tools/.build-env   (gitignored, chmod 600)
UNITY_KEYSTORE=/Users/you/keys/app.keystore
UNITY_KEYSTORE_PASS=...
UNITY_KEY_ALIAS=app
UNITY_KEY_ALIAS_PASS=...
```

```bash
[[ -f "$ENV_FILE" ]] && { set -a; . "$ENV_FILE"; set +a; }
```

Then **prove** it is ignored, rather than assuming the pattern matched:

```bash
git check-ignore -v Tools/.build-env
git status --short | grep -i build-env    # must print nothing
```

Add the artifact patterns too (`*.apk`, `*.aab`) — a stray 70 MB APK in the project root is easy to
commit by accident and impossible to remove from history afterwards without a rewrite. Ignore the
output directory and the native build's temp directory in the same commit: an Android IL2CPP build
can leave a `.utmp/` directory in the project root, and it reaches version control before anyone
notices.

## The version number lives in more than one place

Bumping a version is a grep, not an edit. A bump like `0.1.0 → 0.2.0` can mean three files
agreeing:

- `ProjectSettings/ProjectSettings.asset` → `bundleVersion:`
- the same file → `AndroidBundleVersionCode:`
- a **committed Editor setup script** that assigns `PlayerSettings.bundleVersion = "0.1.0";`

Editing only the asset appears to work — until the next `-executeMethod …ConfigureAndroid`, which
writes the old version straight back and ships it. The build driver reads the version out of the
asset, so it packages whatever the setup script last wrote, with no warning anywhere.

```bash
grep -rn "bundleVersion" ProjectSettings Assets/Scripts/Editor    # before believing a bump
```

Anything that both *stores* a value and *re-applies* it from code has this shape — application id,
`targetSdk`, icons. Either the code path owns the value and the asset is generated, or the asset
owns it and the code path does not touch it. Owning it in both places is the bug.

## A build script's `versionCode` may live only in memory

A build method that does `PlayerSettings.Android.bundleVersionCode = vc;` and then exits has
changed the value **for that build**; nothing guarantees it is serialised back into
`ProjectSettings.asset`, so treat the asset as the source of truth. An auto-bump that reads
`AndroidBundleVersionCode` from that same asset therefore computes the same number again on the
next release, and the two ends of the chain quietly disagree.

Consequences, in order of how bad: a store rejects the re-used code; a device treats it as not-newer
and refuses to install over what is there; a tester reports "your app is broken".

Three ways to be safe, in preference order: pass `--version-code N` explicitly; bump in the editor
and **commit** before building; or keep the committed build history below and refuse a code that
already appears in it — which is the backstop that turns the silent duplicate into a loud refusal.

## versionCode is monotonic per artifact handed out

`versionName` is a label for humans. `versionCode` is the ordering the platform enforces:

- Play rejects a re-used code outright;
- a device treats a lower one as a downgrade and refuses to install over what is already there.

Bump for **every artifact anyone else receives**, not just for store uploads — the tester who
cannot install your fix because it shares a code with the build they already have will report it as
"your app is broken".

Automate the bump, and refuse a re-use rather than warning about it:

```bash
if awk -F'\t' -v c="$VERSION_CODE" '$3==c{f=1} END{exit !f}' "$HISTORY"; then
  die "versionCode $VERSION_CODE has already been built — see $HISTORY"
fi
```

## Keep a build history, and commit it

"Which versionCode did I upload?" is a question people get wrong, and getting it wrong wastes a
store review cycle. One tab-separated line per artifact, written by the build script, committed:

```
date              mode     versionCode  versionName  package            artifact
2026-08-25T13:36  test     1            0.1.0        com.example.app    app-test-1-....apk
2026-08-25T15:02  release  2            0.1.0        com.example.app    app-release-2-....apk
```

Artifacts themselves stay out of the repository. The record of what was built does not.

**A build leaves the tree dirty, and that is normal — check it rather than committing it.** A
build path that runs the Android configure step and a PlayMode gate writes into
`ProjectSettings/ProjectSettings.asset` both times, so `git status` is never clean afterwards. The
routine that keeps history honest, run after every artifact:

```bash
git diff ProjectSettings/ProjectSettings.asset | grep '^[-+] ' | head -4   # what did the build change?
git checkout -- ProjectSettings/ProjectSettings.asset                      # revert it
git add Tools/build-history.tsv && git commit -m "build: <artifact>"       # commit only the ledger
```

Read the diff before reverting: if the build changed something you *meant* to change — a bumped
`versionCode`, a new icon — reverting it is how the next build re-uses the code.

## The package name is permanent

`applicationIdentifier` is store identity and is locked the moment the app is published. Unity's
template default (`com.DefaultCompany.<Project>`) shipping to a store is unrecoverable, so a build
script should refuse a release build that still carries it — a warning is not enough for something
that cannot be undone.

Set it on **every** platform in the file at once, or the iOS bundle ID quietly stays on the
template default until the day it matters.
