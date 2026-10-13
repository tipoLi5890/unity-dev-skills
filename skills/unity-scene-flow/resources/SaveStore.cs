// SaveStore.cs — the save as one versioned plain-data document, the migration chain that brings
// an old file up to the current version, and a write that cannot leave the player with no save.
//
// Drop into a Runtime assembly. No package needed (JsonUtility is a built-in module). Plain C#:
// the directory is passed in, so an EditMode test runs it against a temporary folder, and the
// timestamp is passed in, so the same data always produces the same file.
//
// Three files in one directory:
//   save.json       the save
//   save.json.bak   the save before it — what Read falls back to when save.json is damaged
//   save.json.tmp   the write in progress; never read
// A write goes to the temporary file, is flushed to the disk, is read back and parsed, and only
// then replaces save.json — with the previous file kept as the backup. A crash at any point
// leaves either the old save or the new one readable; the backup is never overwritten with a
// file that did not parse.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

/// <summary>Version 2, the current shape. Facts only: ids, numbers and strings.</summary>
[Serializable]
public sealed class SaveData
{
    public const int CurrentVersion = 2;

    public int version = CurrentVersion;
    /// <summary>Seconds since 1970-01-01 UTC, handed to Write by the caller.</summary>
    public long savedAtUnix;
    /// <summary>Build path of the content scene: Assets/Scenes/GateRoom.unity.</summary>
    public string scene = "";
    public SavePlayer player = new SavePlayer();
    /// <summary>World facts by persistent id: a pickup taken, a gate opened, a switch thrown.</summary>
    public List<SaveFlag> flags = new List<SaveFlag>();

    public int GetFlag(string id, int fallback = 0)
    {
        for (int i = 0; i < flags.Count; i++)
            if (flags[i].id == id) return flags[i].value;
        return fallback;
    }

    public bool HasFlag(string id) => GetFlag(id) != 0;

    public void SetFlag(string id, int value = 1)
    {
        if (string.IsNullOrEmpty(id)) throw new ArgumentException("a flag needs an id", nameof(id));
        for (int i = 0; i < flags.Count; i++)
        {
            if (flags[i].id != id) continue;
            flags[i] = new SaveFlag { id = id, value = value };
            return;
        }
        flags.Add(new SaveFlag { id = id, value = value });
    }

    /// <summary>A deep copy through the same serialiser the file uses — what a checkpoint keeps.</summary>
    public SaveData Clone() => JsonUtility.FromJson<SaveData>(JsonUtility.ToJson(this));
}

[Serializable]
public sealed class SavePlayer
{
    /// <summary>0, 1 or 2; the middle lane is 1.</summary>
    public int lane = 1;
    public Vector3 position;
    /// <summary>Persistent id of the last checkpoint reached, or "".</summary>
    public string checkpoint = "";
}

[Serializable]
public struct SaveFlag
{
    public string id;
    public int value;
}

/// <summary>
/// Version 1, frozen. Never edited again: it exists so a file written by the first release can
/// still be read. v1 → v2: lane and distance move into player (distance becomes position.z, the
/// lane also sets position.x), and each id in collected becomes a flag with value 1.
/// </summary>
[Serializable]
public sealed class SaveDataV1
{
    public int version = 1;
    public long savedAtUnix;
    public string scene = "";
    public int lane = 1;
    public float distance;
    public string[] collected = new string[0];
}

public static class SaveMigrations
{
    /// <summary>Lanes are 1.3 units apart and the middle lane, 1, is at x = 0.</summary>
    public const float LaneSpacing = 1.3f;

    /// <summary>
    /// Steps[n] turns the JSON of version n into the JSON of version n + 1. Index 0 is unused:
    /// there is no version 0. A new version adds one entry and one frozen class, and changes
    /// nothing that is already here.
    /// </summary>
    static readonly Func<string, string>[] Steps = { null, V1ToV2 };

    /// <summary>Run every step from <paramref name="fromVersion"/> up to the current version.</summary>
    public static string ToCurrent(string json, int fromVersion)
    {
        for (int v = fromVersion; v < SaveData.CurrentVersion; v++)
        {
            if (v < 1 || v >= Steps.Length || Steps[v] == null)
                throw new InvalidOperationException("no migration from save version " + v);
            json = Steps[v](json);
        }
        return json;
    }

    static string V1ToV2(string json)
    {
        SaveDataV1 old = JsonUtility.FromJson<SaveDataV1>(json);
        var now = new SaveData
        {
            version = 2,
            savedAtUnix = old.savedAtUnix,
            scene = old.scene ?? "",
        };
        now.player.lane = old.lane;
        now.player.position = new Vector3((old.lane - 1) * LaneSpacing, 0f, old.distance);
        if (old.collected != null)
            foreach (string id in old.collected)
                if (!string.IsNullOrEmpty(id)) now.SetFlag(id, 1);
        return JsonUtility.ToJson(now);
    }
}

public enum SaveSource { None, Main, Backup }

public enum SaveFileState { Missing, Corrupt, TooNew, Good }

public struct SaveReadResult
{
    /// <summary>The save at the current version, or null when there is nothing usable.</summary>
    public SaveData data;
    public SaveSource source;
    /// <summary>The version found in the file, before migration.</summary>
    public int fileVersion;
    /// <summary>The main file was written by a newer build. Do not write over it.</summary>
    public bool tooNew;
    /// <summary>Why the main file was not used, or "" when it was.</summary>
    public string problem;

    public bool Found => data != null;
}

public sealed class SaveStore
{
    [Serializable]
    sealed class Header
    {
        public int version = 0;      // 0 is what a file with no version field reads as
    }

    public string MainPath { get; private set; }
    public string TempPath { get; private set; }
    public string BackupPath { get; private set; }

    public SaveStore(string directory, string fileName = "save.json")
    {
        if (string.IsNullOrEmpty(directory)) throw new ArgumentException("directory");
        MainPath = Path.Combine(directory, fileName);
        TempPath = MainPath + ".tmp";
        BackupPath = MainPath + ".bak";
    }

    /// <summary>
    /// The current save, migrated. Falls back to the backup when the main file is missing or
    /// damaged, and says so in <see cref="SaveReadResult.problem"/>.
    /// </summary>
    public SaveReadResult Read()
    {
        var result = new SaveReadResult { problem = "" };

        SaveFileState main = Inspect(MainPath, out SaveData data, out int version, out string problem);
        if (main == SaveFileState.Good)
        {
            result.data = data;
            result.source = SaveSource.Main;
            result.fileVersion = version;
            return result;
        }
        if (main == SaveFileState.TooNew)
        {
            // Not a damaged file: a good one this build cannot read. Falling back to the backup
            // here would be followed by a write that destroys the newer progress.
            result.tooNew = true;
            result.fileVersion = version;
            result.problem = problem;
            return result;
        }

        result.problem = main == SaveFileState.Missing ? "no save file" : problem;
        if (Inspect(BackupPath, out data, out version, out string backupProblem) == SaveFileState.Good)
        {
            result.data = data;
            result.source = SaveSource.Backup;
            result.fileVersion = version;
        }
        else if (main == SaveFileState.Corrupt && backupProblem.Length > 0)
        {
            result.problem += "; backup: " + backupProblem;
        }
        return result;
    }

    /// <summary>
    /// Write the save. <paramref name="unixSeconds"/> is the caller's clock —
    /// DateTimeOffset.UtcNow.ToUnixTimeSeconds() in the game, a constant in a test. Throws when
    /// the file could not be written or verified; the previous save is untouched in that case.
    /// </summary>
    public void Write(SaveData data, long unixSeconds)
    {
        if (data == null) throw new ArgumentNullException(nameof(data));
        Directory.CreateDirectory(Path.GetDirectoryName(MainPath));

        byte[] bytes = new UTF8Encoding(false).GetBytes(ToJson(data, unixSeconds));
        using (var stream = new FileStream(TempPath, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            stream.Write(bytes, 0, bytes.Length);
            stream.Flush(true);          // to the disk, not to the OS cache: a rename of an unflushed file can survive a power cut as an empty one
        }

        // Read it back before it is allowed near the real save.
        if (Inspect(TempPath, out _, out _, out string problem) != SaveFileState.Good)
        {
            File.Delete(TempPath);
            throw new IOException("the save did not read back: " + problem);
        }

        SaveFileState main = Inspect(MainPath, out _, out int mainVersion, out _);
        if (main == SaveFileState.TooNew)
        {
            File.Delete(TempPath);
            throw new InvalidOperationException("refusing to overwrite a save of version " + mainVersion +
                                                " with version " + SaveData.CurrentVersion);
        }
        if (main == SaveFileState.Missing)
        {
            File.Move(TempPath, MainPath);
            return;
        }
        if (main == SaveFileState.Corrupt)
        {
            // The damaged file must not become the backup: the backup is the only good copy.
            File.Delete(MainPath);
            File.Move(TempPath, MainPath);
            return;
        }

        try
        {
            // One call: new → main, old main → backup.
            File.Replace(TempPath, MainPath, BackupPath);
        }
        catch (Exception e) when (e is PlatformNotSupportedException || e is IOException ||
                                  e is UnauthorizedAccessException)
        {
            // The same result in three steps. After each one, main or backup is a whole file.
            File.Copy(MainPath, BackupPath, true);
            File.Delete(MainPath);
            File.Move(TempPath, MainPath);
        }
    }

    /// <summary>Remove the save, its backup and any write in progress — "new game".</summary>
    public void Delete()
    {
        if (File.Exists(MainPath)) File.Delete(MainPath);
        if (File.Exists(BackupPath)) File.Delete(BackupPath);
        if (File.Exists(TempPath)) File.Delete(TempPath);
    }

    /// <summary>The text Write puts in the file. Stamps the version and the time onto the data.</summary>
    public static string ToJson(SaveData data, long unixSeconds)
    {
        data.version = SaveData.CurrentVersion;
        data.savedAtUnix = unixSeconds;
        return JsonUtility.ToJson(data, true);
    }

    /// <summary>
    /// Text → the current version's data. Detects an empty, cut-off or zero-filled file, a file
    /// with no version, and one from a newer build; migrates an older one.
    /// </summary>
    public static SaveFileState Parse(string json, out SaveData data, out int fileVersion, out string problem)
    {
        data = null;
        fileVersion = 0;
        problem = "";

        string text = json == null ? "" : json.Trim().Trim('\0').Trim();
        if (text.Length == 0)
        {
            problem = "the file is empty";
            return SaveFileState.Corrupt;
        }
        // A write cut short loses the end of the file, and the end of the file is the brace.
        if (text[0] != '{' || text[text.Length - 1] != '}' || !Balanced(text))
        {
            problem = "the file is cut off: it does not start and end as one object";
            return SaveFileState.Corrupt;
        }

        try
        {
            Header header = JsonUtility.FromJson<Header>(text);
            fileVersion = header != null ? header.version : 0;
            if (fileVersion < 1)
            {
                problem = "no version field";
                return SaveFileState.Corrupt;
            }
            if (fileVersion > SaveData.CurrentVersion)
            {
                problem = "written by a newer build: version " + fileVersion + ", this build reads up to " +
                          SaveData.CurrentVersion;
                return SaveFileState.TooNew;
            }

            data = JsonUtility.FromJson<SaveData>(SaveMigrations.ToCurrent(text, fileVersion));
        }
        catch (Exception e)
        {
            data = null;
            problem = "not readable as a save: " + e.Message;
            return SaveFileState.Corrupt;
        }

        if (data == null)
        {
            problem = "parsed to nothing";
            return SaveFileState.Corrupt;
        }
        // JsonUtility leaves a field the file did not have at its default, and a string that
        // was null in the file as null.
        data.version = SaveData.CurrentVersion;
        if (data.scene == null) data.scene = "";
        if (data.player == null) data.player = new SavePlayer();
        if (data.player.checkpoint == null) data.player.checkpoint = "";
        if (data.flags == null) data.flags = new List<SaveFlag>();
        return SaveFileState.Good;
    }

    // Every brace and bracket outside a string closes, and the last one closes the document.
    // Counted here so that "cut off" never depends on how the parser words its complaint.
    static bool Balanced(string text)
    {
        int depth = 0;
        bool inString = false;
        for (int i = 0; i < text.Length; i++)
        {
            char c = text[i];
            if (inString)
            {
                if (c == '\\') i++;
                else if (c == '"') inString = false;
                continue;
            }
            if (c == '"') inString = true;
            else if (c == '{' || c == '[') depth++;
            else if (c == '}' || c == ']')
            {
                depth--;
                if (depth < 0 || (depth == 0 && i != text.Length - 1)) return false;
            }
        }
        return depth == 0 && !inString;
    }

    static SaveFileState Inspect(string path, out SaveData data, out int fileVersion, out string problem)
    {
        data = null;
        fileVersion = 0;
        problem = "";
        if (!File.Exists(path)) return SaveFileState.Missing;
        string text;
        try { text = File.ReadAllText(path, Encoding.UTF8); }
        catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
        {
            problem = "could not be read: " + e.Message;
            return SaveFileState.Corrupt;
        }
        return Parse(text, out data, out fileVersion, out problem);
    }
}
