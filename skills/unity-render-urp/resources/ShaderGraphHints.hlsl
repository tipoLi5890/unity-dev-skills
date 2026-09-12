// Every hint tag a reflected Shader Graph node can carry, in one compilable file.
// Copy the shape, not the file: each function here exists to show one group of tags.
//
// This include must be first. Without it UNITY_EXPORT_REFLECTION is undefined and the file
// fails to compile rather than quietly producing no nodes.
#include "ShaderApiReflectionSupport.hlsl"

namespace GameEffects
{
    struct Sample
    {
        float Value;
    };

// Function-level tags. The first four are required for the node to be findable at all;
// the rest are optional labelling.
/// <funchints>
///     <sg:ProviderKey>GameEffectsEveryHint</sg:ProviderKey>
///     <sg:DisplayName>Every Hint</sg:DisplayName>
///     <sg:SearchCategory>Game Effects/Reference</sg:SearchCategory>
///     <sg:SearchTerms>hint, reflected, reference, example</sg:SearchTerms>
///     <sg:ReturnDisplayName>Result</sg:ReturnDisplayName>
///     <sg:SearchName>Every Hint Reference Node</sg:SearchName>
/// </funchints>
/// <paramhints name="carrier">
///     <sg:DisplayName>Carrier Value</sg:DisplayName>
///     <sg:Default>0.5</sg:Default>
///     <sg:External>GameEffects</sg:External>
/// </paramhints>
/// <paramhints name="tint3">
///     <sg:DisplayName>Tint RGB</sg:DisplayName>
///     <sg:Color />
///     <sg:Default>1,1,0</sg:Default>
/// </paramhints>
/// <paramhints name="tint4">
///     <sg:DisplayName>Tint RGBA</sg:DisplayName>
///     <sg:Color />
///     <sg:Default>1,1,0,1</sg:Default>
/// </paramhints>
/// <paramhints name="constTint3">
///     <sg:DisplayName>Constant Tint RGB</sg:DisplayName>
///     <sg:Color />
///     <sg:Static />
///     <sg:Default>1,1,0</sg:Default>
/// </paramhints>
/// <paramhints name="constTint4">
///     <sg:DisplayName>Constant Tint RGBA</sg:DisplayName>
///     <sg:Color />
///     <sg:Static />
///     <sg:Default>1,1,0,1</sg:Default>
/// </paramhints>
/// <paramhints name="blendMode">
///     <sg:DisplayName>Blend Mode</sg:DisplayName>
///     <sg:Dropdown>Add, Multiply, Screen</sg:Dropdown>
///     <sg:Default>1</sg:Default>
/// </paramhints>
/// <paramhints name="constBlendMode">
///     <sg:DisplayName>Constant Blend Mode</sg:DisplayName>
///     <sg:Dropdown>Add, Multiply, Screen</sg:Dropdown>
///     <sg:Static />
///     <sg:Default>2</sg:Default>
/// </paramhints>
/// <paramhints name="strength">
///     <sg:DisplayName>Strength</sg:DisplayName>
///     <sg:Range>0, 1</sg:Range>
///     <sg:Default>0.75</sg:Default>
/// </paramhints>
/// <paramhints name="constStrength">
///     <sg:DisplayName>Constant Strength</sg:DisplayName>
///     <sg:Static />
///     <sg:Range>0, 1</sg:Range>
///     <sg:Default>0.25</sg:Default>
/// </paramhints>
/// <paramhints name="enabled">
///     <sg:DisplayName>Enabled</sg:DisplayName>
///     <sg:Static />
///     <sg:Default>1</sg:Default>
/// </paramhints>
/// <paramhints name="steps">
///     <sg:DisplayName>Steps</sg:DisplayName>
///     <sg:Static />
///     <sg:Default>5</sg:Default>
/// </paramhints>
UNITY_EXPORT_REFLECTION float3 EveryHint(
    inout Sample carrier,
    float3 tint3,
    inout float4 tint4,
    float3 constTint3,
    float4 constTint4,
    inout uint blendMode,
    uint constBlendMode,
    float strength,
    float constStrength,
    bool enabled,
    int steps
)
{
    return float3(carrier.Value, constStrength, constTint4.r);
}

} // namespace GameEffects

// Referable parameters bind straight to a graph-supplied value, so the node shows up already
// wired instead of with a dangling input. The tag names the source; <Default> picks the variant.
/// <funchints>
///     <sg:ProviderKey>GameEffectsReferables</sg:ProviderKey>
///     <sg:DisplayName>Referable Inputs</sg:DisplayName>
///     <sg:SearchCategory>Game Effects/Reference</sg:SearchCategory>
///     <sg:SearchTerms>referable, uv, position, normal</sg:SearchTerms>
/// </funchints>
/// <paramhints name="UV">
///     <UV/>
///     <Default>UV2</Default>
/// </paramhints>
/// <paramhints name="secondUV">
///     <sg:Referable>UV</sg:Referable>
///     <Default>UV1</Default>
/// </paramhints>
/// <paramhints name="Position">
///     <Position/>
///     <Default>AbsoluteWorld</Default>
/// </paramhints>
/// <paramhints name="Normal">
///     <Normal/>
///     <Default>World</Default>
/// </paramhints>
/// <paramhints name="Tangent">
///     <Tangent/>
///     <Default>Object</Default>
/// </paramhints>
/// <paramhints name="Bitangent">
///     <Bitangent/>
///     <Default>Tangent</Default>
/// </paramhints>
/// <paramhints name="ViewDirection">
///     <ViewDirection/>
///     <Default>Screen</Default>
/// </paramhints>
/// <paramhints name="VertColor">
///     <VertexColor/>
/// </paramhints>
/// <paramhints name="ScreenPosition">
///     <ScreenPosition/>
///     <Default>Pixel</Default>
/// </paramhints>
/// <paramhints name="fallback">
///     <sg:Default>1,0,0</sg:Default>
/// </paramhints>
UNITY_EXPORT_REFLECTION float3 ReferableInputs(float2 UV,
                                               float2 secondUV,
                                               float3 Position,
                                               float3 Normal,
                                               float3 Tangent,
                                               float3 Bitangent,
                                               float3 ViewDirection,
                                               float4 VertColor,
                                               float4 ScreenPosition,
                                               float3 fallback)
{
    return fallback;
}

// <Precision/> lets the node follow the graph's precision instead of pinning float or half.
// <Dynamic/> on a parameter lets its width follow whatever is connected.
/// <funchints>
///     <sg:ProviderKey>GameEffectsPrecision</sg:ProviderKey>
///     <sg:DisplayName>Precision Follow</sg:DisplayName>
///     <sg:SearchCategory>Game Effects/Reference</sg:SearchCategory>
///     <sg:SearchTerms>precision, dynamic, half</sg:SearchTerms>
///     <Precision/>
/// </funchints>
/// <paramhints name="a"><Dynamic/></paramhints>
/// <paramhints name="b"><Dynamic/></paramhints>
/// <paramhints name="sum"><Dynamic/></paramhints>
UNITY_EXPORT_REFLECTION float2 PrecisionFollow(float a, half b, out float sum)
{
    sum = a + b;
    return float2(a, b);
}

// <Linkage> ties one parameter's presentation to another — here the bool decides which branch
// consumes `amount`, so the graph can grey the unused input rather than leaving it live.
/// <funchints>
///     <sg:ProviderKey>GameEffectsLinkage</sg:ProviderKey>
///     <sg:DisplayName>Linked Inputs</sg:DisplayName>
///     <sg:SearchCategory>Game Effects/Reference</sg:SearchCategory>
///     <sg:SearchTerms>linkage, linked, branch</sg:SearchTerms>
/// </funchints>
/// <paramhints name="useRed">
///     <Linkage>amount</Linkage>
/// </paramhints>
UNITY_EXPORT_REFLECTION float3 LinkedInputs(bool useRed, float amount)
{
    return useRed ? float3(amount, 0, 0) : float3(0, amount, 0);
}
