# Cloud Code — the only writer you can trust

`CloudCodeService.Instance` (`ICloudCodeService`), namespace `Unity.Services.CloudCode`,
assembly `Unity.Services.CloudCode`. Needs `UnityServices.InitializeAsync()` and a signed-in
player first.

## Scripts or modules

| | Scripts | Modules |
|---|---|---|
| Language | JavaScript | C# on .NET 9 |
| Client call | `CallEndpointAsync` | `CallModuleEndpointAsync` |
| Deployed as | `.js` | `.ccmr`, pointing at a solution |
| Type-safe client bindings | no | yes, generated |
| NuGet | no | yes |
| Can push messages to a client | no | yes |

**Write production logic as C# modules.** Scripts stay useful for a throwaway experiment, where
the one file and no build step is the point; anything that survives to a release wants the type
safety and the generated bindings.

## Wrong → Correct

| Wrong | Correct |
|---|---|
| `CallEndpointAsync("MyModule", "Fn", args)` | `CallEndpointAsync` is for **scripts**: one name, then args |
| `CallModuleEndpointAsync("Fn", args)` | Module name **first**, function name second |
| `await CallEndpointAsync(...)` treated as void | The non-generic overloads return `Task<string>`, both of them |
| `SubscribeToPlayerMessagesAsync(callbacks)` | Takes **no parameters**. Wire handlers on the returned object afterwards |
| `SubscribeToGeneralMessagesAsync()` | `SubscribeToProjectMessagesAsync()`, also parameterless |
| `SubscriptionEventConnectionState` | `EventConnectionState` |
| `Callbacks.Error += (EventConnectionState s) => …` | `Error` is `Action<string>` |

## `ICloudCodeService`

```csharp
// Scripts.
Task<string>  CallEndpointAsync(string function, Dictionary<string, object> args = default)
Task<TResult> CallEndpointAsync<TResult>(string function, Dictionary<string, object> args = default)

// Modules. module = the .ccmr filename without its extension; function = the method name.
Task<string>  CallModuleEndpointAsync(string module, string function,
    Dictionary<string, object> args = default, CloudCodeModuleScope scope = default)
Task<TResult> CallModuleEndpointAsync<TResult>(string module, string function,
    Dictionary<string, object> args = default, CloudCodeModuleScope scope = default)

// Real-time server push. Both take no arguments; both need com.unity.services.wire.
Task<ISubscriptionEvents> SubscribeToPlayerMessagesAsync()
Task<ISubscriptionEvents> SubscribeToProjectMessagesAsync()
```

Two `string` parameters in a row is exactly the shape an argument swap hides in, and a swapped
pair surfaces as `NotFound` rather than as anything naming the mistake.

## What a module can and cannot do

- **There is no `UnityEngine`.** A module is a plain .NET library. Anything sharing types with the
  client shares plain C# — no `MonoBehaviour`, no `Vector3`, no `JsonUtility`.
- **There is no Remote Config client either.** A module that needs config values gets them as a
  parameter from the caller, or reads them through the admin API. The battle pass blueprint takes
  the first route, and [`battlepass.md`](battlepass.md) explains why that is safe.
- **A cold module is slow.** The first call after an idle stretch waits for a new worker. Budget
  for it in the UI rather than in a timeout, and time that first call on your own environment
  before promising a figure to anyone.
- **Only modules can push.** Server-to-client messages have no script equivalent.

## Subscriptions

Requires `com.unity.services.wire`. Subscribe first, then attach handlers to the object you got
back — passing handlers into the subscribe call is the mistake the
table above lists.

```csharp
public interface ISubscriptionEvents
{
    SubscriptionEventCallbacks Callbacks { get; }
    Task SubscribeAsync();      // re-subscribe after an unsubscribe
    Task UnsubscribeAsync();
}
```

```csharp
var subscription = await CloudCodeService.Instance.SubscribeToPlayerMessagesAsync();
subscription.Callbacks.MessageReceived      += OnMessageReceived;   // Action<IMessageReceivedEvent>
subscription.Callbacks.MessageBytesReceived += OnBytesReceived;     // Action<byte[]>
subscription.Callbacks.ConnectionStateChanged += OnStateChanged;    // Action<EventConnectionState>
subscription.Callbacks.Kicked += OnKicked;                          // Action
subscription.Callbacks.Error  += OnError;                           // Action<string>
```

`IMessageReceivedEvent` carries `MessageType` and `Message` (the payload, usually JSON) plus the
CloudEvents envelope: `Id`, `CorrelationId`, `Source`, `Type`, `SpecVersion`, `Time`, `ProjectId`
and `EnvironmentId`.

`EventConnectionState` (`Unity.Services.CloudCode.Subscriptions`):

| State | Value | Means |
|---|---|---|
| `Unknown` | 0 | initial |
| `Unsubscribed` | 1 | not connected |
| `Subscribing` | 2 | connecting |
| `Subscribed` | 3 | connected, messages flowing |
| `Unsynced` | 4 | dropped, will reconnect on its own |
| `Error` | 5 | connection error |

`Unsynced` is transient — treat it as a status indicator, not as a reason to tear the
subscription down and rebuild it.

## Triggers

A trigger runs a Cloud Code endpoint in response to an event from another service, with no client
involved. Configured in the dashboard or through the UGS CLI, never in client code.

| Emitter | Examples |
|---|---|
| Authentication | player signed in, account deleted |
| Scheduler | cron or one-shot |
| Leaderboards | score submitted, leaderboard reset |
| Cloud Save | data saved, data deleted |

Cleanup work belongs here rather than in a client call: an account deletion that must also clear
Cloud Save cannot rely on the client still being there to ask.

## Module scope

`CallModuleEndpointAsync` takes an optional `CloudCodeModuleScope`
(`Unity.Services.CloudCode.Models`).

```csharp
var scope = new CloudCodeModuleScope(ScopeType.MultiplayerSession, sessionId);
var result = await CloudCodeService.Instance.CallModuleEndpointAsync<MyResult>(
    "MyModule", "MyFunction", args, scope);
```

| `ScopeType` | Value | |
|---|---|---|
| `MultiplayerSession` | 1 | scoped to a session id |
| `Player` | 2 | the calling player — the default |

## Building a module

A module is a .NET 9 class library that the Deployment Window builds and publishes. **It is a
file set, and a missing file fails the deploy** — often while naming something other than the
file you actually forgot.

| File | Why it has to exist |
|---|---|
| `<Module>.sln` | What the `.ccmr` points at |
| `<Module>/<Module>.csproj` | The library itself, with the two Cloud Code NuGet references |
| `<Module>/<Module>.cs` | At least one `[CloudCodeFunction]` method |
| `<Module>/ModuleSetup.cs` | Registers `GameApiClient` for injection |
| `<Module>/Properties/PublishProfiles/FolderProfile.pubxml` | The `linux-x64` publish. Its absence is reported as a failure to retrieve the main project |
| `Assets/.../<Module>.ccmr` | The Unity asset the Deployment Window lists |

### Where it goes

Put the module folder at the **project root**, beside `Assets/`. Unity does not scan the project
root, so nothing needs hiding from the compiler there.

> **The `~` suffix is only for a module that lives inside `Assets/`.** That suffix is what tells
> Unity to skip a folder during compilation. At the project root it is noise, and it makes the
> path harder to type.

```
<ProjectRoot>/
  Assets/
    CloudCode/
      MyModule.ccmr                       <- the Unity asset, points at the .sln
  MyModuleCCM/
    MyModule.sln
    MyModule/
      MyModule.csproj
      MyModule.cs                         <- [CloudCodeFunction] entry points
      ModuleSetup.cs                      <- registers IGameApiClient
      Properties/
        PublishProfiles/
          FolderProfile.pubxml            <- linux-x64
    MyModule.Tests/
      MyModule.Tests.csproj               <- IsPublishable=false, never deployed
      MyModuleTests.cs
```

### The `.gitignore` override you will forget

Unity's stock `.gitignore` excludes `*.sln` and `*.csproj` across the whole repo — reasonable for
generated Unity solutions, wrong for a module whose solution is source. Without an override the
module's project files are quietly untracked, and the failure lands on a teammate or on CI rather
than on you. Add a `.gitignore` **inside the module directory**:

```
# <Module>CCM/.gitignore
!*.sln
!*.csproj
!Properties/PublishProfiles/*.pubxml
```

Then confirm with `git status` that those files are listed as untracked or modified. An
un-listed file is the whole bug, and it looks like nothing.

### `.sln`

Generate fresh GUIDs for `{MAIN-GUID}`, `{TEST-GUID}` and `{SLN-GUID}`. The test project has no
`Release|Any CPU.Build.0` line on purpose — that is half of what keeps it out of the published
output.

```
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 16
VisualStudioVersion = 16.0.30114.105
MinimumVisualStudioVersion = 10.0.40219.1
Project("{9A19103F-16F7-4668-BE54-9A1E7A4F7556}") = "MyModule", "MyModule\MyModule.csproj", "{MAIN-GUID}"
EndProject
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "MyModule.Tests", "MyModule.Tests\MyModule.Tests.csproj", "{TEST-GUID}"
EndProject
Global
	GlobalSection(SolutionConfigurationPlatforms) = preSolution
		Debug|Any CPU = Debug|Any CPU
		Release|Any CPU = Release|Any CPU
	EndGlobalSection
	GlobalSection(ProjectConfigurationPlatforms) = postSolution
		{MAIN-GUID}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{MAIN-GUID}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{MAIN-GUID}.Release|Any CPU.ActiveCfg = Release|Any CPU
		{MAIN-GUID}.Release|Any CPU.Build.0 = Release|Any CPU
		{TEST-GUID}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{TEST-GUID}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{TEST-GUID}.Release|Any CPU.ActiveCfg = Release|Any CPU
	EndGlobalSection
	GlobalSection(SolutionProperties) = preSolution
		HideSolutionNode = FALSE
	EndGlobalSection
	GlobalSection(ExtensibilityGlobals) = postSolution
		SolutionGuid = {SLN-GUID}
	EndGlobalSection
EndGlobal
```

### `.csproj`

```xml
<Project Sdk="Microsoft.NET.Sdk">

    <PropertyGroup>
        <TargetFramework>net9.0</TargetFramework>
        <Nullable>enable</Nullable>
        <Configurations>Debug;Release</Configurations>
    </PropertyGroup>

    <ItemGroup>
        <PackageReference Include="Com.Unity.Services.CloudCode.Apis" Version="0.0.21" />
        <PackageReference Include="Com.Unity.Services.CloudCode.Core" Version="0.0.1" />
        <PackageReference Include="Microsoft.Extensions.Logging.Abstractions" Version="7.0.1" />
    </ItemGroup>

    <PropertyGroup>
        <PublishReadyToRunComposite>true</PublishReadyToRunComposite>
    </PropertyGroup>

</Project>
```

The `Com.Unity.Services.CloudCode.*` pins, the logging-abstractions one beside them and the
test-project pins further down are NuGet packages, not Unity registry packages, so the Package
Manager never resolves them. Treat every version in these two files as a template value and check
it against the vendor's module template before you commit a pin.

### `FolderProfile.pubxml`

Cloud Code runs on Linux and supplies the runtime, so the publish targets `linux-x64` and is not
self-contained.

```xml
<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Configuration>Release</Configuration>
    <Platform>Any CPU</Platform>
    <PublishDir>bin\Release\net9.0\publish\</PublishDir>
    <PublishProtocol>FileSystem</PublishProtocol>
    <TargetFramework>net9.0</TargetFramework>
    <RuntimeIdentifier>linux-x64</RuntimeIdentifier>
    <SelfContained>false</SelfContained>
    <PublishSingleFile>False</PublishSingleFile>
  </PropertyGroup>
</Project>
```

### `ModuleSetup.cs`

One per module. Without it `IGameApiClient` cannot be injected, and every endpoint that touches
another service fails at construction.

```csharp
using Microsoft.Extensions.DependencyInjection;
using Unity.Services.CloudCode.Apis;
using Unity.Services.CloudCode.Core;

public class ModuleSetup : ICloudCodeSetup
{
    public void Setup(ICloudCodeConfig config)
    {
        config.Dependencies.AddSingleton(GameApiClient.Create());
    }
}
```

### The module class

```csharp
using System;
using System.Globalization;
using Microsoft.Extensions.Logging;
using Unity.Services.CloudCode.Apis;
using Unity.Services.CloudCode.Core;

public class MyModule
{
    readonly IGameApiClient m_GameApiClient;
    readonly ILogger<MyModule> m_Logger;

    public MyModule(IGameApiClient gameApiClient, ILogger<MyModule> logger)
    {
        m_GameApiClient = gameApiClient;
        m_Logger = logger;
    }

    // Pure computation: no context parameter.
    [CloudCodeFunction("SayHello")]
    public string SayHello(string name) => $"Hello, {name}!";

    // IExecutionContext is a method parameter, added only where player or project identity
    // is actually needed.
    [CloudCodeFunction("GetServerTime")]
    public string GetServerTime(IExecutionContext context)
        => DateTime.UtcNow.ToString(CultureInfo.InvariantCulture);
}
```

Two injection routes, and mixing them up is a compile error rather than a runtime one:
`IGameApiClient` and `ILogger<T>` arrive through the **constructor**; `IExecutionContext` arrives
as a **method parameter**. The context carries `PlayerId`, `ProjectId` and `ServiceToken` — the
token being what lets a module write a bucket the client may not.

### Test project

```xml
<Project Sdk="Microsoft.NET.Sdk">

    <PropertyGroup>
        <TargetFramework>net9.0</TargetFramework>
        <LangVersion>latest</LangVersion>
        <ImplicitUsings>enable</ImplicitUsings>
        <Nullable>enable</Nullable>
        <IsPackable>false</IsPackable>
        <IsPublishable>false</IsPublishable>
    </PropertyGroup>

    <ItemGroup>
        <PackageReference Include="coverlet.collector" Version="6.0.2" />
        <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.12.0" />
        <PackageReference Include="NUnit" Version="4.2.2" />
        <PackageReference Include="NUnit.Analyzers" Version="4.4.0" />
        <PackageReference Include="NUnit3TestAdapter" Version="4.6.0" />
    </ItemGroup>

    <ItemGroup>
        <Using Include="NUnit.Framework" />
    </ItemGroup>

    <ItemGroup>
        <ProjectReference Include="..\MyModule\MyModule.csproj" />
    </ItemGroup>

</Project>
```

`IsPublishable=false` here plus the missing Release build entry in the `.sln` are two independent
guards on the same thing: test code never reaching the deployed module.

### `.ccmr`

```json
{
  "modulePath": "../../MyModuleCCM/MyModule.sln"
}
```

The path is relative to the `.ccmr` itself — two levels up from `Assets/CloudCode/` reaches the
project root. **The filename without the extension is the module name** that
`CallModuleEndpointAsync` takes, so renaming this file renames the endpoint.

## Generated bindings

After a module is deployed, generate a typed wrapper instead of hand-writing dictionaries at
every call site. The generator reads the deployed module's metadata and emits one file per class
under `Assets/CloudCode/GeneratedModuleBindings/`. Those files are output — regeneration
overwrites whatever you edited into them.

Select the `.ccmr` in the Project window and use **Generate Bindings** in the Inspector, or
regenerate everything from **Services > Cloud Code > Generate Cloud Code Bindings**.

```csharp
// Assets/CloudCode/GeneratedModuleBindings/MyModuleBindings.cs — emitted output, do not edit.
public class MyModuleBindings
{
    readonly ICloudCodeService k_Service;
    public MyModuleBindings(ICloudCodeService service) { k_Service = service; }

    public async Task<string> SayHello(string name)
        => await k_Service.CallModuleEndpointAsync<string>("MyModule", "SayHello",
            new Dictionary<string, object> { { "name", name } });
}
```

```csharp
var bindings = new MyModuleBindings(CloudCodeService.Instance);
var greeting = await bindings.SayHello("World");
```

Two gaps to know about: the generator does not distinguish required from optional parameters, and
it does not handle tuples. Return a named type rather than a tuple and the second stops mattering.

## Calling from the client

```csharp
using Unity.Services.CloudCode;
using System.Collections.Generic;

// Script.
int reward = await CloudCodeService.Instance.CallEndpointAsync<int>(
    "CalculateReward", new Dictionary<string, object> { { "level", 5 }, { "difficulty", "hard" } });

// Module, typed result.
var result = await CloudCodeService.Instance.CallModuleEndpointAsync<GrantResult>(
    "EconomyModule", "GrantDailyReward",
    new Dictionary<string, object> { { "playerId", playerId } });
```

Subscription lifecycle, in full:

```csharp
ISubscriptionEvents subscription;

async Task SubscribeToMessages()
{
    subscription = await CloudCodeService.Instance.SubscribeToPlayerMessagesAsync();

    subscription.Callbacks.MessageReceived += OnMessageReceived;
    subscription.Callbacks.ConnectionStateChanged += state => Debug.Log($"State: {state}");
    subscription.Callbacks.Error  += error => Debug.LogError($"Subscription error: {error}");
    subscription.Callbacks.Kicked += () => Debug.LogWarning("Kicked from subscription");
}

void OnMessageReceived(IMessageReceivedEvent evt)
{
    Debug.Log($"[{evt.MessageType}] {evt.Message}");
}

async Task Unsubscribe()
{
    await subscription.UnsubscribeAsync();
    subscription = null;
}
```

Unsubscribe when the object owning the handlers goes away. A subscription outliving its
`MonoBehaviour` delivers messages into a destroyed target, which surfaces later and elsewhere.

## Deploying

Open **Services > Deployment**, confirm the environment in the dropdown, and deploy the `.js` and
`.ccmr` files it lists. Regenerate bindings after any module deploy that changed a signature —
stale bindings compile fine and fail at the call.

Ordering, when a client change and a module change ship together: deploy the module that tolerates
both the old and the new client **first**. `unity-live-services` §5 has the reasoning; players
update on their own schedule.

## Errors

```csharp
try
{
    var result = await CloudCodeService.Instance.CallModuleEndpointAsync<MyResult>(
        "MyModule", "MyFunction", args);
}
catch (CloudCodeRateLimitedException ex)
{
    Debug.LogError($"Rate limited; retry after {ex.RetryAfter}s");
}
catch (CloudCodeException ex)
{
    Debug.LogError($"Cloud Code: {ex.Message} (reason: {ex.Reason})");
}
```

| `CloudCodeExceptionReason` | Value | |
|---|---|---|
| `Unknown` | 0 | |
| `NoInternetConnection` | 1 | |
| `ProjectIdMissing` | 2 | |
| `PlayerIdMissing` | 3 | not signed in |
| `AccessTokenMissing` | 4 | |
| `InvalidArgument` | 5 | |
| `Unauthorized` | 6 | an `.ac` policy denies this endpoint |
| `NotFound` | 7 | wrong module or function name — including a swapped pair |
| `TooManyRequests` | 8 | |
| `ServiceUnavailable` | 9 | |
| `ScriptError` | 10 | the module threw; the message is yours |
| `SubscriptionError` | 11 | |

`ScriptError` is the useful one: a validation failure you threw inside the module arrives here,
so throw with a message a player-facing string can be derived from.

## Where to go next

- Which bucket a module should write, and why: [`cloud-save.md`](cloud-save.md)
- Making the direct path actually unavailable: [`tooling.md`](tooling.md)
- Two complete modules with their client halves: [`achievements.md`](achievements.md),
  [`battlepass.md`](battlepass.md)
- [Cloud Code manual](https://docs.unity.com/ugs/en-us/manual/cloud-code/manual)
