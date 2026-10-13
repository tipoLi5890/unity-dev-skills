// SaveRoundTripTests.cs — EditMode tests over the save file: what is written reads back equal, a
// version 1 file arrives as version 2 with the documented field change, a file cut short is
// detected and the save before it is the one returned, and a file from a newer build is never
// written over.
//
// Copy into an EditMode test assembly: an asmdef with includePlatforms ["Editor"] that references
// UnityEngine.TestRunner, UnityEditor.TestRunner and the Runtime assembly holding SaveStore.cs
// (this skill → resources/).
//
// REQUIRES com.unity.test-framework.
//
// Every test works in its own directory under the system's temporary folder and removes it
// afterwards; nothing touches Application.persistentDataPath. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform EditMode \
//     -testFilter SaveRoundTrip -testResults /tmp/save.xml -logFile /tmp/save.log
//
// When the save gains a field: bump SaveData.CurrentVersion, freeze the old shape as a class,
// add one step to SaveMigrations, and add one fixture here — the JSON of the old version, typed
// out as a string, never produced by the current code.
using System;
using System.IO;
using NUnit.Framework;
using UnityEngine;

public class SaveRoundTrip
{
    // A file as version 1 wrote it. Typed by hand on purpose: produced by the current classes
    // it would stop describing what is on players' disks the day those classes change.
    const string V1Fixture =
        "{\"version\":1,\"savedAtUnix\":1700000000,\"scene\":\"Assets/Scenes/GateRoom.unity\"," +
        "\"lane\":2,\"distance\":42.5,\"collected\":[\"pickup-a\",\"pickup-b\"]}";

    string _dir;
    SaveStore _store;

    [SetUp]
    public void SetUp()
    {
        _dir = Path.Combine(Path.GetTempPath(), "save-roundtrip-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_dir);
        _store = new SaveStore(_dir);
    }

    [TearDown]
    public void TearDown()
    {
        if (Directory.Exists(_dir)) Directory.Delete(_dir, true);
    }

    static SaveData GateRoomSave(int lane, float z)
    {
        var save = new SaveData { scene = "Assets/Scenes/GateRoom.unity" };
        save.player.lane = lane;
        save.player.position = new Vector3((lane - 1) * SaveMigrations.LaneSpacing, 0f, z);
        save.player.checkpoint = "checkpoint-switch";
        save.SetFlag("gate-switch", 1);
        save.SetFlag("pickup-a", 1);
        save.SetFlag("sentry-alerts", 3);
        return save;
    }

    // ------------------------------------------------------------------------- round trip

    [Test]
    public void Write_ThenRead_ReturnsTheSameSave()
    {
        SaveData written = GateRoomSave(2, 12.5f);
        _store.Write(written, 1700000100);

        SaveReadResult read = _store.Read();

        Assert.IsTrue(read.Found, read.problem);
        Assert.AreEqual(SaveSource.Main, read.source);
        Assert.AreEqual(SaveData.CurrentVersion, read.fileVersion);
        Assert.AreEqual("", read.problem);
        Assert.AreEqual(JsonUtility.ToJson(written), JsonUtility.ToJson(read.data));
        Assert.AreEqual(1700000100L, read.data.savedAtUnix, "the timestamp is the one passed in");
        Assert.AreEqual(3, read.data.GetFlag("sentry-alerts"));
        Assert.IsFalse(read.data.HasFlag("pickup-b"), "a flag nobody set reads as 0");
        Assert.IsFalse(File.Exists(_store.TempPath), "the temporary file is gone after a write");
    }

    [Test]
    public void SameData_SameTimestamp_SameBytes()
    {
        _store.Write(GateRoomSave(1, 4f), 1700000100);
        byte[] first = File.ReadAllBytes(_store.MainPath);
        _store.Write(GateRoomSave(1, 4f), 1700000100);
        byte[] second = File.ReadAllBytes(_store.MainPath);

        // No clock, no instance id and no ordering accident inside the file: a diff of two
        // saves shows what the player did and nothing else.
        CollectionAssert.AreEqual(first, second);
    }

    // -------------------------------------------------------------------------- migration

    [Test]
    public void V1File_MigratesToV2()
    {
        File.WriteAllText(_store.MainPath, V1Fixture);

        SaveReadResult read = _store.Read();

        Assert.IsTrue(read.Found, read.problem);
        Assert.AreEqual(1, read.fileVersion, "the version found in the file, before migration");
        SaveData save = read.data;
        Assert.AreEqual(2, save.version);
        Assert.AreEqual(1700000000L, save.savedAtUnix);
        Assert.AreEqual("Assets/Scenes/GateRoom.unity", save.scene);

        // lane and distance moved into player; distance is position.z and the lane sets x.
        Assert.AreEqual(2, save.player.lane);
        Assert.AreEqual(1.3f, save.player.position.x, 0.0001f);
        Assert.AreEqual(0f, save.player.position.y, 0.0001f);
        Assert.AreEqual(42.5f, save.player.position.z, 0.0001f);
        Assert.AreEqual("", save.player.checkpoint, "version 1 had no checkpoint");

        // collected ids became flags with value 1.
        Assert.AreEqual(2, save.flags.Count);
        Assert.AreEqual(1, save.GetFlag("pickup-a"));
        Assert.AreEqual(1, save.GetFlag("pickup-b"));
    }

    [Test]
    public void MigratedSave_IsWrittenBackAtTheCurrentVersion()
    {
        File.WriteAllText(_store.MainPath, V1Fixture);
        SaveReadResult old = _store.Read();

        _store.Write(old.data, 1700000200);
        SaveReadResult now = _store.Read();

        Assert.AreEqual(SaveData.CurrentVersion, now.fileVersion);
        Assert.AreEqual(1, now.data.GetFlag("pickup-b"));
        // The version 1 file is the backup: one step back is still on disk, in its own format.
        SaveFileState backup = SaveStore.Parse(File.ReadAllText(_store.BackupPath),
                                               out _, out int backupVersion, out string problem);
        Assert.AreEqual(SaveFileState.Good, backup, problem);
        Assert.AreEqual(1, backupVersion);
    }

    // ---------------------------------------------------------------------- damaged files

    [Test]
    public void TruncatedFile_IsDetected_AndThePreviousSaveSurvives()
    {
        _store.Write(GateRoomSave(0, 5f), 100);      // A
        _store.Write(GateRoomSave(2, 30f), 200);     // B: A is now the backup

        // The write of B is cut short: half the bytes reach the disk.
        byte[] whole = File.ReadAllBytes(_store.MainPath);
        byte[] half = new byte[whole.Length / 2];
        Array.Copy(whole, half, half.Length);
        File.WriteAllBytes(_store.MainPath, half);

        SaveReadResult read = _store.Read();

        Assert.IsTrue(read.Found, "nothing usable was found: " + read.problem);
        Assert.AreEqual(SaveSource.Backup, read.source);
        StringAssert.Contains("cut off", read.problem);
        Assert.AreEqual(100L, read.data.savedAtUnix, "the save returned is A, the one before the damage");
        Assert.AreEqual(0, read.data.player.lane);

        // The next write must not push the damaged file over the only good copy.
        _store.Write(GateRoomSave(1, 8f), 300);      // C
        SaveReadResult after = _store.Read();
        Assert.AreEqual(SaveSource.Main, after.source);
        Assert.AreEqual(300L, after.data.savedAtUnix);
        SaveStore.Parse(File.ReadAllText(_store.BackupPath), out SaveData backup, out _, out string problem);
        Assert.IsNotNull(backup, "the backup no longer parses: " + problem);
        Assert.AreEqual(100L, backup.savedAtUnix, "the backup is still A");
    }

    [Test]
    public void ZeroFilledFile_IsDetected()
    {
        _store.Write(GateRoomSave(1, 5f), 100);
        _store.Write(GateRoomSave(1, 9f), 200);
        // The other shape a crash leaves: the right length, no content.
        File.WriteAllBytes(_store.MainPath, new byte[File.ReadAllBytes(_store.MainPath).Length]);

        SaveReadResult read = _store.Read();

        Assert.AreEqual(SaveSource.Backup, read.source, read.problem);
        Assert.AreEqual(100L, read.data.savedAtUnix);
    }

    [Test]
    public void NoFiles_IsNotAnError()
    {
        SaveReadResult read = _store.Read();

        Assert.IsFalse(read.Found);
        Assert.AreEqual(SaveSource.None, read.source);
        Assert.IsFalse(read.tooNew);
        Assert.AreEqual("no save file", read.problem);
    }

    [Test]
    public void FileWithNoVersion_IsRejected()
    {
        File.WriteAllText(_store.MainPath, "{\"scene\":\"Assets/Scenes/GateRoom.unity\"}");

        SaveReadResult read = _store.Read();

        Assert.IsFalse(read.Found);
        StringAssert.Contains("no version", read.problem);
    }

    // ----------------------------------------------------------------------- newer builds

    [Test]
    public void FileFromANewerBuild_IsNeverOverwritten()
    {
        string newer = "{\"version\":" + (SaveData.CurrentVersion + 1) + ",\"savedAtUnix\":900,\"scene\":\"x\"}";
        File.WriteAllText(_store.MainPath, newer);

        SaveReadResult read = _store.Read();
        Assert.IsFalse(read.Found);
        Assert.IsTrue(read.tooNew, read.problem);
        Assert.AreEqual(SaveData.CurrentVersion + 1, read.fileVersion);

        Assert.Throws<InvalidOperationException>(() => _store.Write(GateRoomSave(1, 1f), 950));
        Assert.AreEqual(newer, File.ReadAllText(_store.MainPath), "the newer save was changed");
        Assert.IsFalse(File.Exists(_store.TempPath));
    }
}
