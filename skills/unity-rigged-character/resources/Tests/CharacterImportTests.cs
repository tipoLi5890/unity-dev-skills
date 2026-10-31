// CharacterImportTests — EditMode tests for how CharacterImportSettings names and finds a body FBX's
// embedded maps: which FBX material slots count as base colour and normal (Blender's and Auto-Rig
// Pro's DiffuseColor / NormalMap, Maya's and 3ds Max's names, Bump), that metallic and roughness
// slots are left alone, and the <Body>_<Role> and <Body>_<Material>_<Role> names the importer binds.
//
// Drop it into an EditMode test assembly that references the Editor assembly holding
// CharacterImportSettings.cs (nunit, no scene). The import itself is checked on a real FBX with
// CharacterImportSettings.Maps(folder) (reference/textures.md).
using NUnit.Framework;

namespace UnityDev.RiggedCharacter.Tests
{
    public class CharacterImportTests
    {
        [TestCase("DiffuseColor")]
        [TestCase("Maya|baseColor")]
        [TestCase("Maya|TEX_color_map")]
        [TestCase("3dsMax|Parameters|base_color_map")]
        public void BaseColourSlots(string prop)
        {
            Assert.AreEqual(CharacterImportSettings.BaseColorRole, CharacterImportSettings.MapRole(prop));
        }

        [TestCase("NormalMap")]
        [TestCase("Bump")]
        [TestCase("Maya|normalCamera")]
        [TestCase("Maya|TEX_normal_map")]
        public void NormalSlots(string prop)
        {
            Assert.AreEqual(CharacterImportSettings.NormalRole, CharacterImportSettings.MapRole(prop));
        }

        [TestCase("ReflectionFactor")]       // Blender's metallic: needs the hand-built mask
        [TestCase("ShininessExponent")]      // Blender's roughness
        [TestCase("EmissiveColor")]
        [TestCase("TransparentColor")]
        [TestCase("")]
        [TestCase(null)]
        public void OtherSlotsAreLeftAlone(string prop)
        {
            Assert.IsNull(CharacterImportSettings.MapRole(prop));
        }

        [Test]
        public void MapNamesCarryTheBody()
        {
            Assert.AreEqual("Runner_BaseColor", CharacterImportSettings.MapName("Runner", null, "BaseColor"));
            Assert.AreEqual("Runner_Normal", CharacterImportSettings.MapName("Runner", "", "Normal"));
            // more than one map in a slot: the material keeps them apart, unsafe characters replaced
            Assert.AreEqual("Runner_Bag_Strap_BaseColor", CharacterImportSettings.MapName("Runner", "Bag Strap", "BaseColor"));
            Assert.AreEqual("Runner_Mat_001_Normal", CharacterImportSettings.MapName("Runner", "Mat.001", "Normal"));
        }

        [Test]
        public void ColourMapNamesMatchTheTextureRules()
        {
            // OnPreprocessTexture imports a file as a normal map when its name contains "normal", and
            // MixamoTextures finds the colour map by "basecolor": the extracted names must hit both.
            Assert.IsTrue(CharacterImportSettings.MapName("Runner", null, CharacterImportSettings.NormalRole)
                .ToLowerInvariant().Contains("normal"));
            Assert.IsTrue(CharacterImportSettings.MapName("Runner", null, CharacterImportSettings.BaseColorRole)
                .ToLowerInvariant().Contains("basecolor"));
        }
    }
}
