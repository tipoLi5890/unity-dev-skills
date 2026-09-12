// Swap a TMP_Text's font from an Asset Table when the locale changes.
//
// REQUIRES com.unity.localization and TextMeshPro. Runtime component: put it on any
// GameObject whose label needs a per-locale face, and point its Asset Table reference at
// that locale's font entry.
//
// Use LocalizedTmpFont — the package's own LocalizedAsset<TMP_FontAsset> specialisation,
// and the type the Asset Table picker expects. If you substitute the raw generic, check
// that the Inspector still offers a font entry before going further.
//
// This is the per-locale-swap half of the decision in SKILL.md section 1. It composes
// with a TMP fallback chain as long as this component is what decides the language and
// the chain only catches a glyph the chosen face genuinely lacks.
using TMPro;
using UnityEngine.Localization;
using UnityEngine.Localization.Components;

[UnityEngine.AddComponentMenu("Localization/Asset/Localized Font Asset")]
public class LocalizedFontAsset : LocalizedAssetBehaviour<TMP_FontAsset, LocalizedTmpFont>
{
    protected override void UpdateAsset(TMP_FontAsset font)
    {
        // A null font here is not harmless: TMP falls back to its built-in Latin face,
        // which is solid tofu for CJK. Leave the current face alone instead.
        if (font == null) return;

        var label = GetComponent<TMP_Text>();
        if (label != null) label.font = font;
    }
}
