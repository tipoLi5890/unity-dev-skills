# Custom Shader Graph nodes from reflected HLSL functions

> Part of the `unity-render-urp` skill. This is the one piece of shader authoring the skill
> covers, because it is not shader authoring: a reflected node is a plain HLSL function plus
> metadata, and getting the metadata wrong is a silent failure — the file compiles and no node
> appears in the search.

## The version gate comes first

> **Reflected function nodes need `com.unity.shadergraph` 17.5 or newer.** On 17.4 the grep below
> comes back empty and the package ships no `ShaderApiReflectionSupport.hlsl` to include, so a
> file written against the feature does not compile at all. Treat an empty grep as *absent*
> whatever the version string says.

Check the installed version before writing anything:

```bash
unity command eval 'var p = UnityEditor.PackageManager.PackageInfo.FindForAssetPath(
  "Packages/com.unity.shadergraph/package.json");
  return p == null ? "not installed" : p.version;'
```

Then confirm the package really carries the feature — no output means it does not, whatever the
version string says. The glob assumes the package sits in `Library/PackageCache`; if it does not,
grep the folder its `PackageInfo.resolvedPath` names instead:

```bash
grep -rl 'UNITY_EXPORT_REFLECTION' Library/PackageCache/com.unity.shadergraph@*/ --include='*.hlsl' | head -3
```

Below the floor, say so and stop. The fallback is a hand-written `CustomFunctionNode` in the
graph, which is a different mechanism with a different authoring path and is outside this file.

## The four required function hints

A reflected node is a function preceded by `UNITY_EXPORT_REFLECTION` and documented with a
`funchints` block. **Four tags are required.** Omit one and the node is not findable, which
looks the same as a compile failure that did not happen:

| Tag | What it decides |
|---|---|
| `sg:ProviderKey` | The stable identity of the node. A graph that already uses the node finds it by this, so **changing it orphans every existing use** |
| `sg:DisplayName` | The node's title in the graph |
| `sg:SearchCategory` | Where it sits in the node search tree, as a `Path/Sub-path` |
| `sg:SearchTerms` | The comma-separated words that match it in the search box |

Optional and worth knowing: `sg:ReturnDisplayName` labels the output port, `sg:SearchName` gives
the search a longer name than the title, and `<Precision/>` lets the node inherit the graph's
precision instead of pinning what the signature says.

C#-style documentation tags are allowed **outside** a `funchints` or `paramhints` block, so
ordinary `/// <summary>` prose above the function is fine and does not interfere.

## Parameter hints

Each input gets a `paramhints name="<parameter name>"` block. The name must match the parameter
in the signature exactly — a typo is not an error, it is a hint that applies to nothing.

| Tag | Effect |
|---|---|
| `sg:DisplayName` | The port's label |
| `sg:Default` | The value the port carries unconnected. `1,1,0` for a float3, `1,1,0,1` for a float4, a bare number for a scalar, an index for a dropdown |
| `sg:Color` | Draws a float3/float4 as a colour swatch rather than as numeric fields |
| `sg:Static` | The value is a compile-time constant on the node, not an input port. Use it for anything that changes the generated code rather than the value it operates on |
| `sg:Range` | `min, max` — draws a slider and clamps |
| `sg:Dropdown` | A comma-separated option list; `sg:Default` then takes the zero-based index |
| `sg:Referable` | Binds the port to a graph-supplied value — UV, position, normal, tangent, bitangent, view direction, vertex colour, screen position. `<Default>` picks the variant, e.g. `UV2`, `AbsoluteWorld`, `World` |
| `sg:External` | Names the namespace a struct parameter's type comes from |
| `Dynamic` | The parameter's width follows what is connected instead of the declared type |
| `Linkage` | Names another parameter whose presentation depends on this one |

`sg:Static` and `sg:Range` combine; so do `sg:Static`, `sg:Color` and `sg:Default`. Every
combination that is legal, in one compilable file:
[`../resources/ShaderGraphHints.hlsl`](../resources/ShaderGraphHints.hlsl).

The referable shorthand is worth calling out: `<UV/>` and `<sg:Referable>UV</sg:Referable>` do
the same thing, and the short form is what most existing files use.

## Where the file goes

> **The file must open with `#include "ShaderApiReflectionSupport.hlsl"`.** That is what defines
> `UNITY_EXPORT_REFLECTION`. Without it the macro is an undefined identifier and the whole file
> fails to compile — which is at least loud, unlike a missing hint.

The asset is a `ShaderInclude` — a `.hlsl` under `Assets/`. Before creating a new one, **look for
an existing one that already holds reflected nodes**, because a project that has any usually
wants them together:

```bash
grep -rl 'UNITY_EXPORT_REFLECTION' Assets --include='*.hlsl'
```

If one turns up: show the user its current contents and get agreement before appending. That file
is likely to be referenced from several graphs, so an append is a change to shipped material, not
a new file — and a `ProviderKey` collision inside one file is the kind of breakage that shows up
as a node the graph can no longer resolve.

If none turns up, create one. Put it somewhere the project's own conventions point at rather than
inventing a folder.

## What to report

- Which file was written or appended to, and whether it existed.
- Every `sg:ProviderKey` added — these are the identities graphs will store.
- The `SearchCategory` and `SearchTerms`, so the user can find the node without guessing.
- The installed `com.unity.shadergraph` version, and whether it clears the floor.

Then have the user open a graph and search the terms. A node that compiles and is not findable is
the normal failure here, and nothing in the console says so.
