// Before-and-after pictures for a pipeline migration. Writes a PNG to the OS temp
// directory and returns the path, so the agent reads the image itself rather than asking
// anyone to describe it. Temp rather than Assets/: a PNG written into the project becomes
// an imported asset somebody then has to clean up.
//
// Put this under Assets/Editor/, let Unity compile, then call it with one line:
//   unity command eval --code 'return UnityDev.UrpMigration.SceneCapture.SceneView(1280, 720, "urp-mig-before");'
//
// Check before trusting a capture: under a scriptable pipeline, cam.Render() does not
// always drive the render loop, and the symptom is a PNG that is entirely black rather
// than an error. If that happens, submit a render request
// (RenderPipeline.SubmitRenderRequest with a StandardRequest carrying the target texture)
// on your version, or take the picture through the Editor's own screenshot command --
// see the unity-debug skill.
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace UnityDev.UrpMigration
{
    public static class SceneCapture
    {
        [MenuItem("Tools/Unity Dev/URP Migration/Capture Scene View")]
        public static void RunFromMenu()
        {
            SceneView();
        }

        /// <summary>Capture the last active Scene view camera.</summary>
        public static string SceneView(int width = 1280, int height = 720, string name = "urp-mig-sceneview")
        {
            var sceneView = UnityEditor.SceneView.lastActiveSceneView;
            if (sceneView == null)
                throw new Exception("No active Scene view to capture -- open one, or use GameCamera().");

            return Capture(sceneView.camera, width, height, name, "SceneView");
        }

        /// <summary>Capture what the main camera renders.</summary>
        public static string GameCamera(int width = 1280, int height = 720, string name = "urp-mig-gameview")
        {
            var camera = Camera.main;
            if (camera == null)
                throw new Exception("No camera tagged MainCamera in the open scene.");

            return Capture(camera, width, height, name, "Camera.main");
        }

        /// <summary>
        /// Point the Scene view somewhere specific, then capture. One angle per call, each
        /// with its own filename -- two captures under one name is how a before picture gets
        /// compared against itself.
        /// </summary>
        public static string Angle(Vector3 pivot, Vector3 euler, float size,
                                   string name = "urp-mig-angle", int width = 1280, int height = 720)
        {
            var sceneView = UnityEditor.SceneView.lastActiveSceneView;
            if (sceneView == null)
                throw new Exception("No active Scene view to aim.");

            sceneView.pivot = pivot;
            sceneView.rotation = Quaternion.Euler(euler);
            sceneView.size = size;
            sceneView.Repaint();

            return Capture(sceneView.camera, width, height, name, "SceneView");
        }

        static string Capture(Camera camera, int width, int height, string name, string source)
        {
            var target = new RenderTexture(width, height, 24);
            var texture = new Texture2D(width, height, TextureFormat.RGB24, false);
            var previousTarget = camera.targetTexture;
            var previousActive = RenderTexture.active;

            string path;
            try
            {
                camera.targetTexture = target;
                camera.Render();
                camera.targetTexture = previousTarget;

                RenderTexture.active = target;
                texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                texture.Apply();

                path = Path.Combine(Path.GetTempPath(), name + ".png");
                File.WriteAllBytes(path, ImageConversion.EncodeToPNG(texture));
            }
            finally
            {
                camera.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                UnityEngine.Object.DestroyImmediate(texture);
                target.Release();
                UnityEngine.Object.DestroyImmediate(target);
            }

            var line = "[URP-MIG] capture path=" + path + " source=" + source +
                       " size=" + width + "x" + height;
            Debug.Log(line);
            return line;
        }
    }
}
