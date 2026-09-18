# Signing with what this Mac actually has

Xcode's GUI hides a three-way join. From a terminal you do the join yourself, once, and then the
build is one line.

```
certificate + private key  (login keychain)
        ∩ embedded in
provisioning profile       (~/Library/MobileDevice/Provisioning Profiles, or
        ∩ lists             ~/Library/Developer/Xcode/UserData/Provisioning Profiles)
the device's UDID
```

A build signs when one profile satisfies all three. `templates/ios-run.sh doctor` prints the join;
the steps below are what it runs.

## 1. Which identities can sign

```bash
security find-identity -v -p codesigning
#  1) <40-hex SHA-1> "Apple Development: Some Name (XXXXXXXXXX)"
```

> **The id in parentheses is the person, not the team.** It is the developer's member id.
> `DEVELOPMENT_TEAM=XXXXXXXXXX` with that value fails with **"No Account for Team"** — which reads
> like a login problem and is not one.

The 40-hex string on the left is the certificate's SHA-1. Keep it; step 2 matches on it.

## 2. What each profile covers

A `.mobileprovision` is a signed plist. Decode, then read four things:

```bash
for p in ~/Library/MobileDevice/Provisioning\ Profiles/*.mobileprovision \
         ~/Library/Developer/Xcode/UserData/Provisioning\ Profiles/*.mobileprovision; do
  [ -f "$p" ] || continue
  security cms -D -i "$p" > /tmp/pp.plist 2>/dev/null || continue
  PB=/usr/libexec/PlistBuddy
  echo "== $($PB -c 'Print :Name' /tmp/pp.plist)"
  echo "   team    $($PB -c 'Print :TeamIdentifier:0' /tmp/pp.plist)"          # ← the real team id
  echo "   app id  $($PB -c 'Print :Entitlements:application-identifier' /tmp/pp.plist)"
  echo "   expires $($PB -c 'Print :ExpirationDate' /tmp/pp.plist)"
  echo "   devices $($PB -c 'Print :ProvisionedDevices' /tmp/pp.plist 2>/dev/null | grep -vc '[{}]')"
  i=0; while $PB -c "Print :DeveloperCertificates:$i" /tmp/pp.plist > /tmp/c.der 2>/dev/null; do
    echo "   cert    $(openssl x509 -inform DER -in /tmp/c.der -noout -fingerprint -sha1 | tr -d ':' | sed 's/.*=//')"
    i=$((i+1)); done
done
```

| Field | What it decides |
|---|---|
| `TeamIdentifier` | **The value for `DEVELOPMENT_TEAM`.** Also the certificate subject's `OU` |
| `application-identifier` | `TEAM.*` is a wildcard — any bundle id, but **no capabilities** (push, iCloud, App Groups). `TEAM.com.you.app` covers exactly that id |
| `ProvisionedDevices` | Must contain the device's UDID (step 3). Absent key = a distribution profile; it will not install on a device |
| `DeveloperCertificates` | One of these SHA-1s must equal an identity from step 1 — a certificate without its private key on this Mac signs nothing |
| `Name` starting `iOS Team Provisioning Profile` | **Xcode-managed.** Decides which signing style works — step 4 |

## 3. The device's UDID

`devicectl`'s `Identifier` column is a CoreDevice id, **not** the UDID profiles list.

```bash
xcrun devicectl list devices
xcrun devicectl device info details --device <identifier> | grep -iE ' udid|osVersionNumber|developerModeStatus'
```

`developerModeStatus: disabled` blocks install and launch whatever the signing says — it is
enabled on the device, in Settings → Privacy & Security → Developer Mode, and needs a restart.

## 4. The build line

**When a managed profile covers the device and the certificate** (the common case on a Mac that
has ever run this team's projects from Xcode):

```bash
xcodebuild -project <out>/Unity-iPhone.xcodeproj -scheme Unity-iPhone -sdk iphoneos \
  -configuration Debug -destination "id=<identifier>" -derivedDataPath <dd> \
  CODE_SIGN_STYLE=Automatic DEVELOPMENT_TEAM=<TeamIdentifier> build
grep -E "Signing Identity|Provisioning Profile" <log> | sort -u        # read back what it chose
```

No Xcode account has to be logged in for this. Automatic signing **uses cached managed profiles
offline**; it only needs Apple when it must create or renew one.

| Error | Cause | Do |
|---|---|---|
| `No Account for Team "X"` | `X` is the member id from the certificate name, or a team with no cached profile; or `-allowProvisioningUpdates` was passed with no account logged in | Use `TeamIdentifier` from step 2; drop `-allowProvisioningUpdates` |
| `No profiles for 'com.x.y' were found` | No cached profile matches that bundle id for that team | Use a bundle id the wildcard covers, or have the profile created once (Xcode with the account, any project) |
| `Provisioning profile "…" is Xcode managed, but signing settings require a manually managed profile` | `CODE_SIGN_STYLE=Manual` + `PROVISIONING_PROFILE_SPECIFIER` pointing at a managed profile | Managed profiles only work with `Automatic`. Do not fight it |
| `UnityFramework does not support provisioning profiles` | A profile specifier passed on the command line applies to **every** target, and frameworks take none | Another reason to stay on `Automatic`; if you must go manual, set the specifier on the app target only (xcconfig), never globally |
| `errSecInternalComponent` during codesign over SSH / in CI | The keychain is locked | `security unlock-keychain` in the same session |
| Builds, installs, then `The application could not be verified` on launch | Profile expired, or device not in it | Re-run step 2 and read `ExpirationDate` / devices |

**`-allowProvisioningUpdates` is for a Mac with the account logged in** — then it may register
the device and mint a profile. Without an account it turns a build that would have worked into
*"No Account for Team"*.

## 5. The gate that needs none of this

```bash
xcodebuild -project <out>/Unity-iPhone.xcodeproj -scheme Unity-iPhone -sdk iphoneos \
  -configuration Debug CODE_SIGNING_ALLOWED=NO build | tail -3      # ** BUILD SUCCEEDED **
```

No device, no team, no profile, runs in CI. It proves the generated C++ and every native plugin
compile and link for `arm64`. Do this after every change to a `.mm` and before anyone reaches
for a phone.

## Always pass `-derivedDataPath`

Without it the `.app` lands under `~/Library/Developer/Xcode/DerivedData/<Project>-<hash>/`, and
a `find … | head -1` across that directory returns **whichever build is oldest**. With it, the
path is `<dd>/Build/Products/Debug-iphoneos/<Product>.app` — known, and yours to delete first.
