#!/usr/bin/env python3
"""Static C# rules the Unity compiler only reports inside a project, or only in a player build.

Every *.cs under skills/ is copied into someone's Assets/ folder as shipped, so three mistakes
cost that person a broken project without any error here:

  a  A top-level, non-abstract, non-generic class that derives (directly, or through another
     class in these skills) from MonoBehaviour, ScriptableObject or one of their Unity
     subclasses lives in a file of the same name. Otherwise Unity cannot add it as a
     component or create it as an asset ("No MonoBehaviour scripts in the file"). Exempt:
     test sources (NUnit), whose helper components are only created by AddComponent, and
     types declared after a `// check-csharp: placeholders below` line — stand-ins for the
     game's own components that a template tells you to delete.
  b  A file that names the Editor API — a `using UnityEditor…` directive, a qualified
     `UnityEditor.`, or one of the common editor-only types (AssetDatabase, EditorUtility,
     MenuItem, …) — sits under an Editor/ folder, or every such line is inside an
     `#if UNITY_EDITOR` region. The Editor compiles it either way; the player build fails.
     A runtime file with a guarded editor-only section (a menu helper, an OnValidate) is fine:
     the rule is per line, not "the whole file wrapped".
  c  No new types in the global namespace. Two skills' (or a skill's and a library's)
     global types of the same name do not compile in one project. The types that are global
     today are listed in tools/csharp-global-allowlist.txt as `<skill> <Type>`; a global
     type not in that list fails. `--write-allowlist` rewrites the list from the tree.

Stdlib only. Exit 0 when every rule holds, 2 when one fails, 1 on a usage error.

  python3 tools/check-csharp.py
  python3 tools/check-csharp.py --list-global      # every global type, with its file
  python3 tools/check-csharp.py --write-allowlist  # after removing (never adding) a global type
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / 'skills'
ALLOWLIST = ROOT / 'tools' / 'csharp-global-allowlist.txt'

# Unity bases whose subclasses need the file name to match the class name.
UNITY_BASES = {
    'MonoBehaviour', 'ScriptableObject', 'StateMachineBehaviour', 'EditorWindow', 'Editor',
    'ScriptableWizard', 'ScriptedImporter', 'AssetImporter', 'ScriptableSingleton',
    'TileBase', 'Tile', 'RuleTile', 'AnimatedTile', 'GridBrushBase', 'GridBrush',
    'ScriptableRendererFeature', 'ScriptableRendererData', 'VolumeComponent',
    'UIBehaviour', 'Graphic', 'MaskableGraphic', 'Selectable', 'BaseMeshEffect',
    'PlayableAsset', 'TrackAsset', 'ScriptablePacker', 'LocalizedAsset',
    'NetworkBehaviour',
}

TYPE_DECL = re.compile(
    r'(?P<mods>(?:\b(?:public|internal|private|protected|sealed|abstract|static|partial|'
    r'readonly|ref|unsafe|new|file)\s+)*)'
    r'\b(?P<kind>class|struct|interface|enum|record(?:\s+(?:class|struct))?)\s+'
    r'(?P<name>[A-Za-z_]\w*)\s*(?P<generic><[^>{;]*>)?\s*(?:\((?:[^(){};]|\([^()]*\))*\)\s*)?'
    r'(?::\s*(?P<bases>[^{;]*?))?\s*(?:\bwhere\b[^{;]*)?[{;]')
NAMESPACE_BLOCK = re.compile(r'\bnamespace\s+([A-Za-z_][\w.]*)\s*\{')
NAMESPACE_FILE = re.compile(r'(?m)^\s*namespace\s+([A-Za-z_][\w.]*)\s*;')
USING_EDITOR = re.compile(r'^\s*using\s+(?:static\s+)?(?:\w+\s*=\s*)?UnityEditor\b')
QUALIFIED_EDITOR = re.compile(r'(?<![\w.])UnityEditor\s*\.')
EDITOR_TYPES = re.compile(
    r'(?<![\w.])(?:AssetDatabase|EditorUtility|EditorApplication|EditorGUILayout|EditorGUI|'
    r'EditorPrefs|EditorSceneManager|PrefabUtility|BuildPipeline|Handles|Undo|'
    r'SerializedObject|SerializedProperty)\s*\.|\[\s*(?:MenuItem|InitializeOnLoad(?:Method)?|'
    r'CustomEditor|PostProcessBuild)\b')
PLACEHOLDERS = re.compile(r'//\s*check-csharp:\s*placeholders below')
DIRECTIVE = re.compile(r'^\s*#\s*(if|elif|else|endif)\b(.*)$')


def strip_code(text: str) -> str:
    """Comments, strings and chars blanked out (newlines kept), so offsets and lines survive."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if c == '/' and nxt == '/':
            j = text.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
        elif c == '/' and nxt == '*':
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r'[^\n]', ' ', text[i:j]))
            i = j
        elif c == '"' or (c in '@$' and nxt == '"') or (c in '@$' and nxt in '@$' and text[i + 2:i + 3] == '"'):
            start = i
            prefix = ''
            while text[i] in '@$':
                prefix += text[i]
                i += 1
            if text.startswith('"""', i):          # raw string literal
                j = text.find('"""', i + 3)
                j = n if j < 0 else j + 3
            else:
                verbatim = '@' in prefix
                j = i + 1
                while j < n:
                    if verbatim and text[j] == '"' and text[j + 1:j + 2] == '"':
                        j += 2
                        continue
                    if not verbatim and text[j] == '\\':
                        j += 2
                        continue
                    if text[j] == '"' or (not verbatim and text[j] == '\n'):
                        j += 1
                        break
                    j += 1
            out.append(re.sub(r'[^\n]', ' ', text[start:j]))
            i = j
        elif c == "'":
            m = re.match(r"'(?:\\.|[^'\\\n])+'", text[i:])
            if m:
                out.append(' ' * len(m.group(0)))
                i += len(m.group(0))
            else:
                out.append(c)
                i += 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def blank_directives(code: str) -> str:
    """Preprocessor lines blanked, so `#region Foo {` or `#if X` never reads as code."""
    return re.sub(r'(?m)^[ \t]*#.*$', lambda m: ' ' * len(m.group(0)), code)


def editor_guarded_lines(text: str) -> set:
    """Line numbers (1-based) that only compile when UNITY_EDITOR is defined: inside an
    `#if UNITY_EDITOR` (or `UNITY_EDITOR && …`) branch, or the `#else` of `#if !UNITY_EDITOR`."""
    requires = re.compile(r'\(?\s*UNITY_EDITOR\s*\)?(?:\s*&&.*)?|.*&&\s*\(?\s*UNITY_EDITOR\s*\)?')
    negated = re.compile(r'!\s*UNITY_EDITOR')
    guarded = set()
    stack = []          # per open #if: [condition of the #if, this branch needs UNITY_EDITOR]
    for no, line in enumerate(text.splitlines(), 1):
        m = DIRECTIVE.match(line)
        if m:
            kind, cond = m.group(1), m.group(2).split('//')[0].strip()
            if kind == 'if':
                stack.append([cond, bool(requires.fullmatch(cond))])
            elif kind == 'elif' and stack:
                stack[-1][1] = bool(requires.fullmatch(cond))
            elif kind == 'else' and stack:
                stack[-1][1] = bool(negated.fullmatch(stack[-1][0]))
            elif kind == 'endif' and stack:
                stack.pop()
            continue
        if any(branch for _, branch in stack):
            guarded.add(no)
    return guarded


def matching_brace(code: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(code)):
        if code[i] == '{':
            depth += 1
        elif code[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return len(code)


def parse(path: pathlib.Path) -> dict:
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    code = blank_directives(strip_code(text))
    depth_at = []
    d = 0
    for ch in code:
        depth_at.append(d)
        if ch == '{':
            d += 1
        elif ch == '}':
            d -= 1
    ns_spans = []       # (open, close, name)
    for m in NAMESPACE_BLOCK.finditer(code):
        o = m.end() - 1
        ns_spans.append((o, matching_brace(code, o), m.group(1)))
    file_ns = NAMESPACE_FILE.search(code)
    types = []
    for m in TYPE_DECL.finditer(code):
        pos = m.start('kind')
        enclosing = [s for s in ns_spans if s[0] < pos < s[1]]
        if depth_at[pos] != len(enclosing):
            continue    # nested type, or a declaration inside a method
        if file_ns and file_ns.start() < pos:
            ns = file_ns.group(1)
        else:
            ns = '.'.join(s[2] for s in sorted(enclosing)) or None
        bases = [b.strip() for b in re.split(r',(?![^<]*>)', m.group('bases') or '') if b.strip()]
        types.append({
            'name': m.group('name'), 'kind': m.group('kind').split()[0], 'ns': ns,
            'abstract': 'abstract' in m.group('mods') or 'static' in m.group('mods'),
            'generic': bool(m.group('generic')), 'bases': bases,
            'line': code.count('\n', 0, pos) + 1,
        })
    return {'text': text, 'code': code, 'types': types}


def base_name(b: str) -> str:
    b = re.sub(r'<.*', '', b).strip()
    return b.split('.')[-1]


def skill_of(path: pathlib.Path) -> str:
    return path.relative_to(SKILLS).parts[0]


def in_editor_folder(path: pathlib.Path) -> bool:
    return 'Editor' in path.relative_to(SKILLS).parts[:-1]


def is_test(parsed: dict) -> bool:
    return bool(re.search(r'^\s*using\s+NUnit\.Framework\s*;', parsed['text'], re.M))


def collect() -> dict:
    return {p: parse(p) for p in sorted(SKILLS.rglob('*.cs'))}


def global_types(files: dict) -> list:
    rows = []
    for p, f in files.items():
        for t in f['types']:
            if t['ns'] is None:
                rows.append((skill_of(p), t['name'], p))
    return rows


def read_allowlist() -> set:
    if not ALLOWLIST.is_file():
        return set()
    out = set()
    for line in ALLOWLIST.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            parts = line.split()
            if len(parts) == 2:
                out.add((parts[0], parts[1]))
    return out


def write_allowlist(rows: list) -> None:
    keys = sorted({(s, n) for s, n, _ in rows})
    head = ('# Global-namespace C# types that exist today, as `<skill> <Type>`.\n'
            '# tools/check-csharp.py fails on a global type not listed here. Put new types in a\n'
            '# namespace instead of adding a line; remove a line when its type moves into one\n'
            '# (`python3 tools/check-csharp.py --write-allowlist` rewrites this file from the tree).\n')
    ALLOWLIST.write_text(head + ''.join(f'{s} {n}\n' for s, n in keys), encoding='utf-8')


def rule_a(files: dict) -> list:
    # class name -> first base, across the skills, to follow MonoBehaviour through our own bases
    parent = {}
    for f in files.values():
        for t in f['types']:
            if t['kind'] in ('class', 'record') and t['bases']:
                parent.setdefault(t['name'], base_name(t['bases'][0]))

    def is_unity_object(name: str, seen=()) -> bool:
        if name in UNITY_BASES:
            return True
        if name in parent and name not in seen:
            return is_unity_object(parent[name], seen + (name,))
        return False

    errs = []
    for p, f in files.items():
        if is_test(f):
            continue
        m = PLACEHOLDERS.search(f['text'])
        stub_from = f['text'].count('\n', 0, m.start()) + 1 if m else None
        for t in f['types']:
            if stub_from is not None and t['line'] > stub_from:
                continue
            if t['kind'] != 'class' or t['abstract'] or t['generic'] or not t['bases']:
                continue
            if is_unity_object(base_name(t['bases'][0])) and t['name'] != p.stem:
                errs.append(f'{p.relative_to(ROOT)}:{t["line"]}: {t["name"]} derives from a Unity '
                            f'object ({base_name(t["bases"][0])}) but the file is {p.name}; move it '
                            f'to {t["name"]}.cs or Unity cannot add or create it')
    return errs


def rule_b(files: dict) -> list:
    errs = []
    for p, f in files.items():
        if in_editor_folder(p):
            continue
        guarded = editor_guarded_lines(f['text'])
        # The type names alone are only editor API when the file imports UnityEditor; a game
        # type called Handles or Undo is not.
        uses_editor = bool(re.search(r'^\s*using\s+UnityEditor\b', f['code'], re.M))
        code_lines = f['code'].splitlines()
        raw_lines = f['text'].splitlines()
        for no, raw in enumerate(raw_lines, 1):
            if no in guarded:
                continue
            code_line = code_lines[no - 1] if no - 1 < len(code_lines) else ''
            if USING_EDITOR.match(code_line) or QUALIFIED_EDITOR.search(code_line) or \
                    (uses_editor and EDITOR_TYPES.search(code_line)):
                errs.append(f'{p.relative_to(ROOT)}:{no}: names UnityEditor outside an Editor/ '
                            f'folder and outside #if UNITY_EDITOR; a player build fails. Move the '
                            f'file under an Editor/ folder or guard it')
                break
    return errs


def rule_c(files: dict, allow: set) -> list:
    errs = []
    for s, n, p in global_types(files):
        if (s, n) not in allow:
            errs.append(f'{p.relative_to(ROOT)}: {n} is a new type in the global namespace; '
                        f'put it in a namespace (tools/csharp-global-allowlist.txt lists only '
                        f'the global types that already exist)')
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--list-global', action='store_true', help='print every global type and its file')
    ap.add_argument('--write-allowlist', action='store_true',
                    help='rewrite tools/csharp-global-allowlist.txt from the tree')
    ap.error = lambda msg: (print(f'check-csharp: {msg}', file=sys.stderr), sys.exit(1))
    a = ap.parse_args()
    files = collect()
    rows = global_types(files)
    if a.list_global:
        for s, n, p in sorted(rows):
            print(f'{s} {n}\t{p.relative_to(ROOT)}')
        return 0
    if a.write_allowlist:
        write_allowlist(rows)
        print(f'wrote {ALLOWLIST.relative_to(ROOT)}: {len({(s, n) for s, n, _ in rows})} global types')
        return 0
    allow = read_allowlist()
    stale = sorted(allow - {(s, n) for s, n, _ in rows})
    results = [('a  Unity object class name equals file name', rule_a(files)),
               ('b  UnityEditor only under Editor/ or #if UNITY_EDITOR', rule_b(files)),
               ('c  no new global-namespace types', rule_c(files, allow))]
    if not ALLOWLIST.is_file():
        results[2][1].insert(0, f'{ALLOWLIST.relative_to(ROOT)} is missing; run --write-allowlist')
    if stale:
        results.append(('c  allowlist has no stale rows',
                        [f'{ALLOWLIST.relative_to(ROOT)}: `{s} {n}` no longer exists as a global '
                         f'type; remove the line (or run --write-allowlist)' for s, n in stale]))
    bad = 0
    for title, errs in results:
        print(f'{"FAIL" if errs else "ok  "} {title}' + (f' ({len(errs)})' if errs else ''))
        for e in errs:
            print(f'     {e}')
        bad += len(errs)
    ntypes = sum(len(f['types']) for f in files.values())
    print(f'{len(files)} C# files, {ntypes} top-level types, {len(rows)} global; '
          f'{"all rules hold" if not bad else f"{bad} problem(s)"}')
    return 2 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
