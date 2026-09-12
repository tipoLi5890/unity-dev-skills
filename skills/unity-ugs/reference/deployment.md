# Deployment — one window, one environment, whatever is under Assets

`com.unity.services.deployment` is Editor-only; no runtime code references it.

The Deployment Window (**Services > Deployment**) finds every UGS resource file under `Assets/`,
targets one environment, and pushes the ones you check.

## File types, and who registers them

A file type appears in the window only because its package is installed. A `.rc` file in a project
without `com.unity.remote-config` is an inert text asset — no error, just absent from the list,
which is the usual explanation for "my file does not show up".

| Service | Package | Extensions | Registered from |
|---|---|---|---|
| Cloud Code scripts | `com.unity.services.cloudcode` | `.js` | 2.1.0 |
| Cloud Code C# modules | `com.unity.services.cloudcode` | `.ccmr` | 2.5.0 |
| Remote Config | `com.unity.remote-config` | `.rc` | 3.2.0 |
| Economy | `com.unity.services.economy` | `.ecc`, `.eci`, `.ecv`, `.ecr` | 3.2.1 |
| Leaderboards | `com.unity.services.leaderboards` | `.lb` | 2.0.0 |
| Game Server Hosting | `com.unity.services.multiplayer` | `.gsh` | 1.1.0 |
| Matchmaker | `com.unity.services.multiplayer` | `.mmq` | 1.0 |
| Game Overrides | `com.unity.services.tooling` | `.ugo` | 1.3.0 |
| Access Control | `com.unity.services.tooling` | `.ac` | 1.0 |
| Deployment definitions | `com.unity.services.deployment` | `.ddef` | — |

Economy has four extensions because currencies, inventory items, virtual purchases and real-money
purchases are separate definition files.

## The loop

1. Add `com.unity.services.deployment` through the Package Manager.
2. Open **Services > Deployment**.
3. **Pick the environment in the dropdown, and read it back before anything else.** It is the one
   field in this window that decides whether you are editing a sandbox or production.
4. Check the files to push.
5. Deploy.

> **Report, then wait.** Say which environment is selected and list the files that would go, then
> get confirmation. A deploy is not reversible from this window, and the data behind the
> environment belongs to real players.

## `.ddef` — scoping the window

A deployment definition narrows the window to a subset of files, which is what stops a large
project from presenting every team's resources to everyone.

Create with **Create > Unity Gaming Services > Deployment Definition**.

```json
{
  "name": "GameplayServices",
  "excludePaths": [
    "Assets/CloudCode/Experimental/**",
    "Assets/Config/Archive/**"
  ]
}
```

| Field | Type | |
|---|---|---|
| `name` | `string` | Shown in the window's dropdown |
| `excludePaths` | `string[]` | Glob patterns to skip |

- With no `.ddef` selected, the window shows and deploys everything it discovers under `Assets/`.
- With one selected, it shows only that definition's scope minus the excluded paths.
- Several can coexist; the dropdown chooses.

The exclusion list is also the cheap way to keep an in-progress module out of a deploy without
moving it out of the repo.

## Programmatic access

The main package's types are all `internal` — **there is no public API on it**. Programmatic
deployment comes from the separate `com.unity.services.deployment.api` package, namespace
`Unity.Services.DeploymentApi.Editor`.

### `Deployments.Instance`

| Member | Type | |
|---|---|---|
| `Instance` | `Deployments` | Static singleton |
| `DeploymentProviders` | `ObservableCollection<DeploymentProvider>` | Every registered service provider |
| `DeploymentWindow` | `IDeploymentWindow` | The window, controllable |
| `EnvironmentProvider` | `IEnvironmentProvider` | Current environment |
| `ProjectIdProvider` | `IProjectIdentifierProvider` | Current project id |

### `IDeploymentWindow`

| Member | |
|---|---|
| `Deploy(items, token)` | `Task<DeploymentResult<IDeploymentItem>>` |
| `Deploy(filePaths, token)` | Extension: same, addressed by path |
| `GetAllDeploymentItems(includeDeploymentDefinitions)` | Extension: everything across every provider |
| `GetFromFiles(filePaths)` | Items matching those paths |
| `GetDeploymentDefinitions()` | The `.ddef` items |
| `OpenWindow()` | Opens the `EditorWindow` |
| `GetChecked()` / `GetSelected()` | **Only meaningful while the window is open** |
| `Check(items)` / `ClearChecked()` | Check programmatically |
| `Select(items)` / `ClearSelection()` | Select programmatically |
| `DeploymentStarting` | `event Action<IReadOnlyList<IDeploymentItem>>` |
| `DeploymentEnded` | `event Action<IReadOnlyList<IDeploymentItem>>` |
| `GetCurrentDeployment()` | The active `DeploymentScope`, or null |

The checked/selected pair depends on window state; a headless script should build its item list
with `GetAllDeploymentItems` or `GetFromFiles` and never touch them.

### Results and status

`DeploymentResult<T>` exposes `Deployed` (`List<T>`) — what actually went.

`DeploymentStatus` is built through static factories rather than a constructor:
`Empty`, `UpToDate`, `ModifiedLocally` and `FailedToDeploy` are static readonly instances;
`GetDeployed(details)`, `GetDeploying(details)`, `GetFailedToDeploy(details)`,
`GetFailedToFetch(details)`, `GetFailedToLoad(e, path)`, `GetFailedToRead(e, path)`,
`GetFetched(details)`, `GetFetching(details)`, `GetPartialDeploy(details)` and
`GetPartialFetch(details)` build the rest.

`SeverityLevel`: `None` 0, `Info` 1, `Warning` 2, `Error` 3, `Success` 4.

A partial deploy is its own status, not a failure — a script that treats anything other than
`Deployed` as an error will report a half-applied environment as a total one.

### `DeploymentProvider`

Subclass it to put your own assets in the window.

| Member | |
|---|---|
| `Service` | Display name (abstract) |
| `DeployCommand` | The deploy command (abstract) |
| `DeploymentItems` | `ObservableCollection<IDeploymentItem>` — populate this |
| `Commands` | Extra context-menu commands |
| `OpenCommand` | Double-click handler (optional) |
| `ValidateCommand` | Validation (optional) |
| `SyncItemsWithRemoteCommand` | Sync with remote (optional) |

`IDeploymentItem` carries `Name`, `Path`, `Progress` (0–100), `Status` and
`States` (`ObservableCollection<AssetState>` — local validation).

```csharp
using UnityEditor;
using Unity.Services.DeploymentApi.Editor;

class MyServiceDeploymentProvider : DeploymentProvider
{
    public override string Service => "MyService";
    public override Command DeployCommand { get; } = new MyDeployCommand();
}

[InitializeOnLoadMethod]
static void RegisterProvider()
{
    Deployments.Instance.DeploymentProviders.Add(new MyServiceDeploymentProvider());
}
```

> **A custom deploy command that writes to a UGS service goes through `IAdminClient`** from
> `com.unity.services.apis` — authenticate with `SetServiceAccount(keyId, keySecret)`, then call
> the admin API for the service. There is no other supported path from the Editor.
> [`apis.md`](apis.md) has the interface and the templates; `unity-live-services` §2 decides where
> that key may live, and the answer is never the project.

### Deploying from code

```csharp
using Unity.Services.DeploymentApi.Editor;

var allItems = Deployments.Instance.DeploymentWindow.GetAllDeploymentItems();
var result   = await Deployments.Instance.DeploymentWindow.Deploy(allItems);

await Deployments.Instance.DeploymentWindow.Deploy(new[] { "Assets/MyConfig.rc" });

Deployments.Instance.DeploymentWindow.DeploymentStarting += items =>
    Debug.Log($"Deploying {items.Count} items…");
Deployments.Instance.DeploymentWindow.DeploymentEnded += items =>
    Debug.Log($"Deployment finished: {items.Count} items");
```

## Outside the Editor

The [UGS CLI](https://github.com/Unity-Technologies/unity-gaming-services-cli/) is the standalone
tool for the same resources, and the one a pipeline should use. It deploys and fetches `.rc`,
`.ac`, `.ccmr`, `.lb`, `.ec*` and `.ugo`; `fetch` pulls remote state back into the local files,
which is how an environment edited in the dashboard gets reconciled with the repo. It also
handles triggers and schedules — generating default configs for both — and reaches admin
functionality the window does not surface.

It is a different tool from the `unity` CLI that `unity-cli` covers. Both being called "the CLI"
in a conversation is a reliable source of confusion.

## Where to go next

- The file the Cloud Code entry needs beside it: [`cloud-code.md`](cloud-code.md)
- Policies and overrides: [`tooling.md`](tooling.md)
- Admin writes from a deploy command: [`apis.md`](apis.md)
- Which environment a build talks to, and how that is made visible: `unity-live-services` §1
- [Deployment manual](https://docs.unity.com/ugs/en-us/manual/deployment/manual)
