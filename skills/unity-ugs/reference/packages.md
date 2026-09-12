# Packages — ids, floors, and what actually resolved

Floors are the vendor's stated minimum. Each floor is on its package's registry version list, so a
pin at that version resolves; if a call is missing at the floor, pin higher rather than assuming
the table is wrong about the API. Read what resolved off `Packages/packages-lock.json`.

| Package | API floor | What it gives you |
|---|---|---|
| `com.unity.services.core` | 1.16.0 | `UnityServices.InitializeAsync()`, the dependency graph |
| `com.unity.services.authentication` | 3.6.1 | Player identity and every sign-in method |
| `com.unity.services.cloudcode` | 2.10.3 | Server-authoritative C# modules |
| `com.unity.services.cloudsave` | 3.4.0 | Per-player and game-wide key-value storage, player files |
| `com.unity.remote-config` | 4.2.5 | Server-side config and definitions. Note the id has no `services.` segment |
| `com.unity.services.deployment` | 1.7.2 | The Deployment Window (Editor only) |
| `com.unity.services.tooling` | 1.4.1 | Registers `.ac` and `.ugo` with that window (Editor only) |
| `com.unity.services.apis` | 1.1.1 | Generated REST clients, including the admin client |
| `com.unity.services.leaderboards` | — | Score submission and ranking |
| `com.unity.services.economy` | — | Currencies, inventory, virtual purchases |
| `com.unity.services.analytics` | — | Events and consent |

Two things that table is worth reading for:

- **A `latest` dist-tag can be a pre-release — pin deliberately.** Adding
  `com.unity.services.cloudcode` without a version pin resolves it through the Editor's own rules,
  not through that tag — but if you are reading the registry to decide a pin, check whether
  `latest` is an `-exp` build and take the newest stable instead.
- **`com.unity.services.wire` is a separate add** and Cloud Code subscriptions do not work
  without it.

Adding packages is a project change, not an API call — `unity-new-project` →
`reference/package-bootstrap.md` has the manifest-versus-lockfile check that tells you what
actually resolved.
