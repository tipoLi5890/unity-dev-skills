# Versions

The version facts the skills depend on, each checked against an official source. This is the one
file in the repository that carries source links and check dates. A skill names the fact, not the
number, and points here; where a skill must show a number (a pin in a code sample, a version fork
in an API), the number must match this table.

When a fact changes, change it here first, then grep `skills/` for the old value.

The **Token** column is what `tools/check-contracts.py` reads: every value a skill may carry for a
key. `pkg@1.2.3` is a pin (`"pkg": "1.2.3"` in a manifest, or `pkg@1.2.3`); `17.x` takes any 17
release. `pkg>=1.2.3` is a floor (a package-table row, or `pkg` 1.2.3+). `targetSdkVersion=36` is a
value a script or code sample may assign. A key with several tokens accepts any of them. A key not
in the column is not checked, and `—` marks a fact that names no package or key.

## Store and platform policy

| Fact | Value | Token | Source | Checked |
|---|---|---|---|---|
| Google Play: target API for new apps and app updates | Android 16, API 36, from 2026-08-31 (extension available to 2026-11-01). Wear OS and Automotive: 35. TV and XR: 34 | `targetSdkVersion=36` | [developer.android.com](https://developer.android.com/google/play/requirements/target-sdk) | 2026-10-30 |
| Google Play: target API for existing apps to stay visible to new users | API 35 from 2026-08-31; below that, the app is offered only to devices on its target version or lower | `targetSdkVersion=35` | [developer.android.com](https://developer.android.com/google/play/requirements/target-sdk) | 2026-10-30 |
| Google Play: 16 KB memory page support | Required on 64-bit devices for every app that targets API 35 or higher. From 2027-02-01 an update without it cannot be released | `targetSdkVersion=35` | [developer.android.com](https://developer.android.com/guide/practices/page-sizes) | 2026-10-30 |
| Consequence for this plugin | A store build can no longer pin `targetSdk` 34 to dodge a 4 KB-aligned native library. The library must be rebuilt or replaced. A pin at 34 is for sideloaded or internal builds only | `targetSdkVersion=34` | derived from the three rows above | 2026-10-30 |

## Unity Editor

| Fact | Value | Token | Source | Checked |
|---|---|---|---|---|
| LTS streams | 6000.0 LTS (support ends October 2026), 6000.3 LTS (support ends December 2027) | — | [unity.com](https://unity.com/releases/unity-6/support) | 2026-10-30 |
| Newest releases after 6000.4 | 6000.5.0f1 released 2026-06-15; 6000.6.0f1 released 2026-08-31 (the docs label 6000.6 "Current") | — | [6000.5](https://unity.com/releases/editor/whats-new/6000.5.0), [6000.6](https://unity.com/releases/editor/whats-new/6000.6.0) | 2026-10-30 |
| Pre-release | 6000.7 in beta; Unity 7.0 in public alpha (announced 2026-10-06) | — | [unity.com beta](https://unity.com/releases/editor/beta), [discussions.unity.com](https://discussions.unity.com/t/unity-7-is-here/1738415) | 2026-10-30 |
| Android `minSdk` floor | API 25 on 6000.3 and 6000.4; API 26 on 6000.5 and 6000.6 | `minSdkVersion=25` `minSdkVersion=26` | [6000.4](https://docs.unity3d.com/6000.4/Documentation/Manual/android-requirements-and-compatibility.html), [6000.5](https://docs.unity.com/en-us/engine/6000.5/manual/platform-specific/android/introducing/requirements-and-compatibility), [6000.6](https://docs.unity.com/en-us/engine/6000.6/manual/platform-specific/android/introducing/requirements-and-compatibility) | 2026-10-30 |
| Android target API levels the Editor offers | 35 and 36 (6000.3 to 6000.6) | `targetSdkVersion=35` `targetSdkVersion=36` | same pages | 2026-10-30 |

## Packages

Registry facts come from the package's own entry in the Unity registry (`https://packages.unity.com/<id>`):
the `latest` dist-tag, its `unity` minimum and its `dependencies`.

| Fact | Value | Token | Source | Checked |
|---|---|---|---|---|
| URP (`com.unity.render-pipelines.universal`) | A core package fixed to the Editor: 17.N on 6000.N (17.4 on 6000.4). Never pin it from the registry, whose `latest` tag is an old 10.x line | `com.unity.render-pipelines.universal@17.x` | [URP requirements](https://docs.unity3d.com/6000.4/Documentation/Manual/urp/requirements.html) | 2026-10-30 |
| Input System (`com.unity.inputsystem`) | latest 1.20.1 | `com.unity.inputsystem@1.20.1` | [com.unity.inputsystem](https://packages.unity.com/com.unity.inputsystem) | 2026-10-30 |
| Cinemachine 3 (`com.unity.cinemachine`) | latest 3.1.7 | `com.unity.cinemachine@3.1.7` | [com.unity.cinemachine](https://packages.unity.com/com.unity.cinemachine) | 2026-10-30 |
| 2D Animation (`com.unity.2d.animation`) | major tracks the Editor: 13.x needs 6000.3, 14.x 6000.4, 15.x 6000.5, 16.x 6000.6, 17.x 6000.7 | `com.unity.2d.animation@13.x` `com.unity.2d.animation@14.x` `com.unity.2d.animation@15.x` `com.unity.2d.animation@16.x` `com.unity.2d.animation@17.x` | [com.unity.2d.animation](https://packages.unity.com/com.unity.2d.animation) | 2026-10-30 |
| UGS Core (`com.unity.services.core`) | latest 1.18.0. General floor, as `unity-ugs` states it: 1.16.0 (Cloud Code 3.0.0 depends on the same); 1.18.0 with IAP 5.4 in the project (what `com.unity.purchasing` 5.4.4 depends on) | `com.unity.services.core@1.18.0` `com.unity.services.core>=1.16.0` `com.unity.services.core>=1.18.0` | [com.unity.services.core](https://packages.unity.com/com.unity.services.core) | 2026-10-30 |
| UGS Authentication (`com.unity.services.authentication`) | latest 3.8.1. General floor, as `unity-ugs` states it: 3.6.1 (Cloud Code 3.0.0 depends on the same); 3.8.1 for IAP direct-to-consumer payments | `com.unity.services.authentication@3.8.1` `com.unity.services.authentication>=3.6.1` `com.unity.services.authentication>=3.8.1` | [com.unity.services.authentication](https://packages.unity.com/com.unity.services.authentication), [IAP D2C workflow](https://docs.unity.com/en-us/iap/payment-providers/workflow) | 2026-10-30 |
| UGS Cloud Code (`com.unity.services.cloudcode`) | `latest` is 3.0.0, which needs Unity 6000.7; on 6000.3 to 6000.6 stay on 2.x (floor 2.10.3, latest 2.10.4) | `com.unity.services.cloudcode@3.0.0` `com.unity.services.cloudcode@2.10.4` `com.unity.services.cloudcode>=2.10.3` | [com.unity.services.cloudcode](https://packages.unity.com/com.unity.services.cloudcode) | 2026-10-30 |
| UGS Cloud Save, Remote Config, Deployment, Tooling, APIs | latest 3.4.2, 4.2.5, 1.7.2, 1.4.1, 1.1.1 | `com.unity.services.cloudsave@3.4.2` `com.unity.remote-config@4.2.5` `com.unity.services.deployment@1.7.2` `com.unity.services.tooling@1.4.1` `com.unity.services.apis@1.1.1` | [com.unity.services.cloudsave](https://packages.unity.com/com.unity.services.cloudsave), [com.unity.remote-config](https://packages.unity.com/com.unity.remote-config), [com.unity.services.deployment](https://packages.unity.com/com.unity.services.deployment), [com.unity.services.tooling](https://packages.unity.com/com.unity.services.tooling), [com.unity.services.apis](https://packages.unity.com/com.unity.services.apis) | 2026-10-30 |
| Unity IAP (`com.unity.purchasing`) | latest 5.4.4. Direct-to-consumer payments need IAP 5.4; from 5.4.4 IAP installs the Deployment package itself. The vendor floor is Unity 2022.3, Unity 6 recommended | `com.unity.purchasing@5.4.4` `com.unity.purchasing>=5.4` | [com.unity.purchasing](https://packages.unity.com/com.unity.purchasing), [IAP D2C workflow](https://docs.unity.com/en-us/iap/payment-providers/workflow) | 2026-10-30 |
| LevelPlay | Unity package 9.6.0 (2026-10-28), wrapping native LevelPlay SDK 9.7.0 for Android and iOS. The two lines are numbered separately and matched up to 9.5.0; since then the native SDK runs ahead. `unity-ads-levelplay`'s 9.4 / 9.5 API forks were written against that shared numbering | `com.unity.services.levelplay@9.6.0` | [LevelPlay Unity changelog](https://docs.unity.com/en-us/grow/levelplay/sdk/unity/changelog) | 2026-10-30 |
| Multiplayer Services (`com.unity.services.multiplayer`) | latest 2.4.1 | `com.unity.services.multiplayer@2.4.1` | [com.unity.services.multiplayer](https://packages.unity.com/com.unity.services.multiplayer) | 2026-10-30 |
| Netcode for GameObjects (`com.unity.netcode.gameobjects`) | latest 3.1.0 | `com.unity.netcode.gameobjects@3.1.0` | [com.unity.netcode.gameobjects](https://packages.unity.com/com.unity.netcode.gameobjects) | 2026-10-30 |
| AI Navigation (`com.unity.ai.navigation`) | latest 2.0.16 | `com.unity.ai.navigation@2.0.16` | [com.unity.ai.navigation](https://packages.unity.com/com.unity.ai.navigation) | 2026-10-30 |
