#!/usr/bin/env python3
"""Check the data contracts: what one skill writes and another reads, and what the docs promise.

Four checks, each over the whole repository:

  outputs    every selftest that hands off a sample (prints `selftest-output: PATH`) runs, and
             each sample validates against schemas/<name>-<major>.json, picked by its `schema`
             stamp (`frames/1` -> frames-1.json). A `.jsonl` timeline is validated line by line,
             plus the file rules: the meta line first, at most one end line and only last, and
             end.samples equal to the number of samples. Fenced JSON examples in skills/**/*.md
             that carry a known stamp are validated the same way. Rows whose dependencies are
             missing print SKIP, as in tools/run-selftests.py, whose table this reuses.
  flags      each long flag in a documented command line (`scripts/....py --flag` inside a code
             block in skills/**/*.md) is a string the script's source defines; each documented
             `-executeMethod Ns.Class.Method` names a `static void|int|Task Method(` in a class
             of that name, in shipped C# under skills/ or in a C# block of the docs.
  deps       a skill script that reaches into another skill (a path built from the other skill's
             name, `skills/B/...` or `../B/...`) is declared in tools/cross-skill-deps.txt, and
             every path declared there exists.
  versions   every token in VERSIONS.md's Token column names a value a skill may carry for that
             key; every occurrence of a tracked key in skills/ (a package pin, a package version
             in a table row or next to the name, a targetSdkVersion/minSdkVersion assignment)
             carries one of those values.

  python3 tools/check-contracts.py                 # all four
  python3 tools/check-contracts.py --only flags    # one check (repeatable)
  python3 tools/check-contracts.py --blender PATH  # also the selftests that run inside Blender

Needs jsonschema for `outputs` (pip install jsonschema); the other checks are standard library.
Skills never import a validator: this file is the only place schemas are enforced.

Exit codes: 0 every check held; 2 a contract was violated; 3 harness error (a selftest that
should hand off a sample failed or wrote nothing, an unreadable schema, jsonschema missing);
1 usage error.
"""
import argparse
import ast
import importlib.util
import json
import os
import pathlib
import re
import shlex
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / 'skills'
SCHEMAS = ROOT / 'schemas'
DEPS_FILE = ROOT / 'tools' / 'cross-skill-deps.txt'
VERSIONS = ROOT / 'VERSIONS.md'
CHECKS = ('outputs', 'flags', 'deps', 'versions')

# A selftest that hands off a sample says so in its source.
HANDS_OFF = re.compile(r'selftest-output|contract_sample\(|contract_out\(')
OUTPUT_LINE = re.compile(r'^selftest-output:\s*(.+?)\s*$', re.M)
SUFFIX_STAMP = {'.frames.json': 'frames/1', '.gate.json': 'gate/1', '.timeline.jsonl': 'timeline/1'}


class Report:
    def __init__(self):
        self.violations, self.harness = [], []

    def bad(self, msg):
        self.violations.append(msg)
        print(f'FAIL {msg}')

    def broken(self, msg):
        self.harness.append(msg)
        print(f'ERROR {msg}')


def rel(p: pathlib.Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def skill_names() -> set:
    return {d.name for d in SKILLS.iterdir() if d.is_dir()}


def _no_constants(name):
    raise ValueError(f'{name} is not JSON')


def load_json(text: str):
    """json.loads that refuses NaN and Infinity, which Python writes and other readers refuse."""
    return json.loads(text, parse_constant=_no_constants)


def fenced_blocks(text: str):
    """(info string, body, first line number) of each ``` block."""
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        m = re.match(r'^\s*(```+|~~~+)\s*([^\s`]*)', lines[i])
        if not m:
            i += 1
            continue
        fence, info, start, body = m.group(1), m.group(2).lower(), i + 1, []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith(fence[:3]):
            body.append(lines[i])
            i += 1
        out.append((info, '\n'.join(body), start + 1))
        i += 1
    return out


# ---------------------------------------------------------------------------------- outputs

def load_runner():
    spec = importlib.util.spec_from_file_location('run_selftests', ROOT / 'tools' / 'run-selftests.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_schemas(rep: Report) -> dict:
    """{stamp: validator}; None when jsonschema is missing."""
    try:
        import jsonschema
    except ImportError:
        rep.broken('outputs: jsonschema is not installed (pip install jsonschema)')
        return None
    out = {}
    for f in sorted(SCHEMAS.glob('*-*.json')):
        m = re.fullmatch(r'(.+)-(\d+)\.json', f.name)
        try:
            schema = load_json(f.read_text(encoding='utf-8'))
            cls = jsonschema.validators.validator_for(schema)
            cls.check_schema(schema)
        except Exception as e:
            rep.broken(f'outputs: {rel(f)} is not a valid schema: {e}')
            continue
        out[f'{m.group(1)}/{m.group(2)}'] = cls(schema)
    return out


def schema_errors(validator, doc) -> list:
    errs = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    return [f'{"/".join(str(p) for p in e.absolute_path) or "(top)"}: {e.message[:200]}' for e in errs[:5]]


def check_timeline(validators, lines: list, where: str, rep: Report) -> bool:
    """Per-line timeline/1 validation plus the file rules. lines: [(line no, text)]."""
    v, ok, docs = validators['timeline/1'], True, []
    for no, text in lines:
        try:
            docs.append((no, load_json(text)))
        except ValueError as e:
            rep.bad(f'{where}:{no}: not JSON ({e})')
            ok = False
    for no, d in docs:
        for err in schema_errors(v, d):
            rep.bad(f'{where}:{no}: timeline/1 {err}')
            ok = False
    if not docs:
        return ok
    if not (isinstance(docs[0][1], dict) and docs[0][1].get('meta') is True):
        rep.bad(f'{where}: the first line is not the meta line')
        ok = False
    ends = [i for i, (_, d) in enumerate(docs) if isinstance(d, dict) and d.get('end') is True]
    samples = sum(1 for _, d in docs if isinstance(d, dict) and 'n' in d)
    if len(ends) > 1 or (ends and ends[0] != len(docs) - 1):
        rep.bad(f'{where}: an end line that is not the single last line')
        ok = False
    elif ends and docs[-1][1].get('samples') != samples:
        rep.bad(f'{where}: end.samples is {docs[-1][1].get("samples")} but the file has {samples} samples')
        ok = False
    return ok


def check_file(validators, path: pathlib.Path, rep: Report) -> bool:
    where = rel(path)
    try:
        text = path.read_text(encoding='utf-8')
    except OSError as e:
        rep.broken(f'{where}: unreadable ({e})')
        return False
    expect = next((s for suf, s in SUFFIX_STAMP.items() if path.name.endswith(suf)), None)
    if path.suffix == '.jsonl':
        lines = [(i + 1, t) for i, t in enumerate(text.splitlines()) if t.strip()]
        try:
            stamp = load_json(lines[0][1]).get('schema') if lines else None
        except (ValueError, AttributeError):
            stamp = None
        if stamp != 'timeline/1':
            rep.bad(f'{where}: the meta line is stamped {stamp!r}, not "timeline/1"')
            return False
        return check_timeline(validators, lines, where, rep)
    try:
        doc = load_json(text)
    except ValueError as e:
        rep.bad(f'{where}: not JSON ({e})')
        return False
    stamp = doc.get('schema') if isinstance(doc, dict) else None
    if stamp not in validators:
        rep.bad(f'{where}: stamp {stamp!r} names no schema in schemas/')
        return False
    if expect and stamp != expect:
        rep.bad(f'{where}: the file name says {expect} but the stamp is {stamp}')
        return False
    errs = schema_errors(validators[stamp], doc)
    for err in errs:
        rep.bad(f'{where}: {stamp} {err}')
    return not errs


def check_doc_examples(validators, rep: Report) -> int:
    """Fenced JSON in the docs that carries a known stamp must validate. Returns how many."""
    n = 0
    for md in sorted(SKILLS.rglob('*.md')):
        for info, body, line in fenced_blocks(md.read_text(encoding='utf-8')):
            if info not in ('json', 'jsonl', 'jsonc', ''):
                continue
            if '"schema"' not in body:
                continue
            where = f'{rel(md)}:{line}'
            try:
                doc = load_json(body)
                if isinstance(doc, dict) and doc.get('schema') in validators:
                    n += 1
                    for err in schema_errors(validators[doc['schema']], doc):
                        rep.bad(f'{where}: example {doc["schema"]} {err}')
                continue
            except ValueError:
                pass
            lines = [(line + i + 1, t) for i, t in enumerate(body.splitlines()) if t.strip()]
            try:
                first = load_json(lines[0][1]) if lines else None
            except ValueError:
                continue    # an example with ellipses or comments: not checkable
            if isinstance(first, dict) and first.get('schema') == 'timeline/1':
                n += 1
                check_timeline(validators, lines, rel(md), rep)
    return n


def check_outputs(rep: Report, blender, only_rows) -> None:
    validators = load_schemas(rep)
    if validators is None:
        return
    for need in ('frames/1', 'gate/1', 'timeline/1'):
        if need not in validators:
            rep.broken(f'outputs: schemas/ has no schema for {need}')
            return
    runner = load_runner()
    out_dir = tempfile.mkdtemp(prefix='unity-dev-contracts-')
    os.environ['UNITY_DEV_CONTRACT_OUT'] = out_dir      # runner.run() passes os.environ on
    files = ran = skipped = 0
    for path, argv, deps in runner.SELFTESTS:
        if only_rows and only_rows not in path:
            continue
        script = SKILLS / path
        if not script.is_file():
            rep.broken(f'outputs: skills/{path} is in run-selftests but missing')
            continue
        src = script.read_text(encoding='utf-8', errors='replace')
        if not HANDS_OFF.search(src):
            continue
        label = f'{path} {" ".join(argv)}' + (' (Blender)' if 'bpy' in deps else '')
        missing = runner.missing_deps(deps, blender)
        if missing:
            skipped += 1
            print(f'SKIP (missing dep: {", ".join(missing)}) {label}')
            continue
        if 'bpy' in deps:
            cmd = [blender, '-b', '--factory-startup', '-P', str(script), '--', *argv]
        else:
            cmd = [sys.executable, str(script), *argv]
        ran += 1
        code, out = runner.run(cmd, runner.TIMEOUT)
        paths = OUTPUT_LINE.findall(out)
        if code != 0:
            rep.broken(f'outputs: {label} exited {code}, nothing verified{runner.tail(out, 8)}')
            continue
        if not paths:
            rep.broken(f'outputs: {label} hands off samples but printed no selftest-output line')
            continue
        good = 0
        for p in paths:
            f = pathlib.Path(p)
            if not f.is_file():
                rep.broken(f'outputs: {label} printed {p}, which does not exist')
                continue
            files += 1
            good += check_file(validators, f, rep)
        print(f'{"ok  " if good == len(paths) else "FAIL"} {label}: {good}/{len(paths)} samples valid')
    examples = check_doc_examples(validators, rep)
    print(f'outputs: {ran} selftests ran, {skipped} skipped, {files} samples checked, '
          f'{examples} doc examples checked')


# ------------------------------------------------------------------------------------ flags

SCRIPT_TOKEN = re.compile(r'(?:^|.*/)scripts/(?:[\w.-]+/)*[\w.-]+\.py$')


def defined_flags(script: pathlib.Path, cache={}) -> set:
    """Every whole string constant that looks like a long flag, in the script and in the
    modules beside it that it imports (a subcommand's flags often live there). A script that
    builds its flags as f"--{name}" gets every identifier-like constant in it as a flag too."""
    if script in cache:
        return cache[script]
    cache[script] = flags = set()
    try:
        tree = ast.parse(script.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        return flags
    near, words, built = set(), set(), False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            m = re.fullmatch(r'(--[A-Za-z0-9][\w-]*)=?', node.value)
            if m:
                flags.add(m.group(1))
            elif re.fullmatch(r'[A-Za-z][\w-]*', node.value):
                words.add(node.value)
        elif isinstance(node, ast.JoinedStr) and node.values:
            head = node.values[0]
            built |= isinstance(head, ast.Constant) and head.value == '--'
        elif isinstance(node, ast.Import):
            near.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            near.add(node.module.split('.')[0])
    if built:
        flags |= {f'--{w}' for w in words}
    for name in near:
        sib = script.parent / f'{name}.py'
        if sib.is_file() and sib != script:
            flags |= defined_flags(sib)
    return flags


def resolve_script(token: str, own_skill: str, names: set):
    """The skills/ file a documented script names, or None. A path with scripts/ in it is read
    as that skill's (or this doc's skill's) script; a bare `name.py` is looked up by name in
    this skill's scripts/, then in every skill's, and must be unique."""
    token = token.strip('"\'`')
    m = re.search(r'(?:^|/)([a-z0-9-]+)/scripts/((?:[\w.-]+/)*[\w.-]+\.py)$', token)
    skill = m.group(1) if m and m.group(1) in names else own_skill
    if m or 'scripts/' in token:
        tail = m.group(2) if m else token.split('scripts/', 1)[1]
        cand = SKILLS / skill / 'scripts' / tail
        if cand.is_file():
            return cand
    name = pathlib.Path(token).name
    own = SKILLS / skill / 'scripts'
    hits = sorted(own.rglob(name)) if own.is_dir() else []
    if len(hits) != 1:
        hits = sorted(SKILLS.glob(f'*/scripts/**/{name}'))
    return hits[0] if len(hits) == 1 else None


def command_lines(body: str):
    """Logical lines of a code block, backslash continuations joined: (offset, text)."""
    out, buf, start = [], '', 0
    for i, line in enumerate(body.splitlines()):
        if not buf:
            start = i
        if line.rstrip().endswith('\\'):
            buf += line.rstrip()[:-1] + ' '
            continue
        out.append((start, buf + line))
        buf = ''
    if buf:
        out.append((start, buf))
    return out


def split_tokens(line: str) -> list:
    # A shell comment starts a word; `--key-color=#00ff00` and "#00ff00" are values, not comments.
    line = re.sub(r'(?:^|\s)#(?:\s.*|$)', ' ', line)
    lex = shlex.shlex(line, posix=True, punctuation_chars='|&;')
    lex.whitespace_split = True
    lex.commenters = ''
    try:
        return list(lex)
    except ValueError:      # an unbalanced quote: fall back to whitespace
        return line.split()


# -executeMethod targets the docs name as the reader's own project code, not something a skill
# ships: an illustration of the syntax, or a class the reader writes. Each with its reason.
PROJECT_CODE = {
    'Builder.Build': 'unity-cli: the shape of a `unity run -- -executeMethod` call, any build method',
    'Company.Build.BuildScript.BuildAndroid': 'unity-android-release: how a namespace changes the name',
    'Game.Editor.VenueAssetsBuilder.Build': "unity-3d-level: the game's own venue importer",
}
EXECUTE = re.compile(r'-executeMethod\s+["\']?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)')
STATIC_ENTRY = r'\bstatic\s+(?:async\s+)?(?:void|int|(?:System\.Threading\.Tasks\.)?Task(?:<int>)?)\s+{m}\s*\('


def csharp_sources() -> list:
    """(where, code, declarations) of shipped C# and of each doc's C# blocks. A doc may name its
    class and namespace in prose and show only the methods, so its declarations are its text."""
    out = []
    for f in sorted(SKILLS.rglob('*.cs')):
        src = f.read_text(encoding='utf-8', errors='replace')
        out.append((rel(f), src, src))
    for md in sorted(SKILLS.rglob('*.md')):
        text = md.read_text(encoding='utf-8')
        code = '\n'.join(body for info, body, _ in fenced_blocks(text) if info in ('csharp', 'cs', 'c#'))
        if code:
            out.append((rel(md), code, text))
    return out


def check_command(toks: list, where: str, own: str, names: set, rep: Report) -> tuple:
    """(commands, flags) checked in one tokenised command line."""
    commands = flags = 0
    for i, tok in enumerate(toks):
        bare = tok.strip('"\'`')
        if not bare.endswith('.py') or any(c in bare for c in '*?{<'):
            continue
        script = resolve_script(bare, own, names)
        if script is None:
            if SCRIPT_TOKEN.match(bare):
                rep.bad(f'flags: {where}: {bare} names no script under skills/')
            continue    # a bare name.py that is not a skill script: the reader's own tool
        commands += 1
        have = defined_flags(script)
        for arg in toks[i + 1:]:
            if arg in ('|', '||', '&&', '&', ';', ';;'):
                break
            flag = arg.split('=', 1)[0]
            if not re.fullmatch(r'--[A-Za-z][\w-]*', flag) or flag == '--help':
                continue
            flags += 1
            if flag not in have:
                rep.bad(f'flags: {where}: {rel(script)} defines no {flag}')
        break
    return commands, flags


def check_flags(rep: Report) -> None:
    names = skill_names()
    commands = flags_checked = 0
    for md in sorted(SKILLS.rglob('*.md')):
        own = md.relative_to(SKILLS).parts[0]
        text = md.read_text(encoding='utf-8')
        units = []      # (line no, command text)
        for info, body, line in fenced_blocks(text):
            units += [(line + off, cmd) for off, cmd in command_lines(body)]
        prose = re.sub(r'(?ms)^\s*```.*?^\s*```', lambda m: '\n' * m.group(0).count('\n'), text)
        for no, ln in enumerate(prose.splitlines(), 1):
            units += [(no, span) for span in re.findall(r'`([^`]*\.py\b[^`]*)`', ln)]
        for no, cmd in units:
            c, f = check_command(split_tokens(cmd), f'{rel(md)}:{no}', own, names, rep)
            commands += c
            flags_checked += f
    sources = csharp_sources()
    targets = found = 0
    for md in sorted(SKILLS.rglob('*.md')):
        for no, text in enumerate(md.read_text(encoding='utf-8').splitlines(), 1):
            for target in EXECUTE.findall(text):
                if target in PROJECT_CODE:
                    continue
                parts = target.split('.')
                cls, method, prefix = parts[-2], parts[-1], '.'.join(parts[:-2])
                targets += 1
                entry = re.compile(STATIC_ENTRY.format(m=re.escape(method)))
                decl = re.compile(rf'\b(?:class|struct)\s+{re.escape(cls)}\b')
                hits = [(w, d) for w, code, d in sources if decl.search(d) and entry.search(code)]
                if prefix:
                    ns = re.compile(rf'\bnamespace\s+{re.escape(prefix)}\b|\b(?:class|struct)\s+{re.escape(parts[-3])}\b')
                    hits = [(w, d) for w, d in hits if ns.search(d)]
                if hits:
                    found += 1
                else:
                    rep.bad(f'flags: {rel(md)}:{no}: -executeMethod {target}: no static {method}() in a '
                            f'class {cls}{" in " + prefix if prefix else ""} in skills/ C# or a doc C# block')
    print(f'flags: {commands} documented commands, {flags_checked} flags, '
          f'{found}/{targets} -executeMethod targets found')


# ------------------------------------------------------------------------------------- deps

def _chain(node) -> list:
    """The operands of a / chain, left to right."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _chain(node.left) + _chain(node.right)
    return [node]


def _is_home(node) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'home'
               for n in ast.walk(node))


def python_refs(path: pathlib.Path, own: str, names: set) -> set:
    """Other skills this script builds a path into."""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        return set()
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    found = set()
    pat = re.compile(r'(?:skills/|\.\./)([a-z0-9-]+)/')
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            ops = _chain(node)
            if any(_is_home(o) for o in ops):
                continue    # ~/.codex/<skill>/config.json is a settings folder, not the skill
            for o in ops:
                if isinstance(o, ast.Constant) and o.value in names and o.value != own:
                    found.add(o.value)
        elif isinstance(node, ast.Call):
            f = node.func
            fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')
            if fname in ('join', 'insert', 'append', 'Path', 'PurePath'):
                for a in node.args:
                    if isinstance(a, ast.Constant) and a.value in names and a.value != own:
                        found.add(a.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if '\n' in node.value or ' ' in node.value.strip():
                continue    # prose (a help text or message), not a path
            for b in pat.findall(node.value):
                if b in names and b != own:
                    found.add(b)
    return found


def shell_refs(path: pathlib.Path, own: str, names: set) -> set:
    found = set()
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        code = '' if line.lstrip().startswith('#') else line
        for b in re.findall(r'(?:skills/|\.\./)([a-z0-9-]+)/', code):
            if b in names and b != own:
                found.add(b)
    return found


def read_declared(rep: Report) -> dict:
    """{(source, target skill): (target path, reason)} from cross-skill-deps.txt."""
    out = {}
    if not DEPS_FILE.is_file():
        rep.bad(f'deps: {rel(DEPS_FILE)} is missing')
        return out
    for no, line in enumerate(DEPS_FILE.read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.fullmatch(r'(\S+)\s*->\s*(\S+)\s+\|\s*(.+)', line)
        if not m:
            rep.bad(f'deps: {rel(DEPS_FILE)}:{no}: not "SOURCE -> TARGET | reason"')
            continue
        src, tgt, why = m.groups()
        for p in (src, tgt):
            if not (SKILLS / p).exists():
                rep.bad(f'deps: {rel(DEPS_FILE)}:{no}: skills/{p} does not exist')
        if src.split('/')[0] == tgt.split('/')[0]:
            rep.bad(f'deps: {rel(DEPS_FILE)}:{no}: {src} and {tgt} are in the same skill')
        out[(src, tgt.split('/')[0])] = (tgt, why)
    return out


def check_deps(rep: Report) -> None:
    names = skill_names()
    declared = read_declared(rep)
    detected = set()
    for skill in sorted(names):
        sdir = SKILLS / skill / 'scripts'
        if not sdir.is_dir():
            continue
        for f in sorted(sdir.rglob('*')):
            if '__pycache__' in f.parts or not f.is_file():
                continue
            if f.suffix == '.py':
                refs = python_refs(f, skill, names)
            elif f.suffix == '.sh':
                refs = shell_refs(f, skill, names)
            else:
                continue
            src = f.relative_to(SKILLS).as_posix()
            for b in sorted(refs):
                detected.add((src, b))
                if (src, b) not in declared:
                    rep.bad(f'deps: skills/{src} reaches into {b} but tools/cross-skill-deps.txt does not declare it')
    for key in sorted(set(declared) - detected):
        print(f'WARN deps: {key[0]} -> {key[1]} is declared but not detected (stale, or a path the detector cannot see)')
    print(f'deps: {len(detected)} cross-skill references, {len(declared)} declared')


# --------------------------------------------------------------------------------- versions

TOKEN = re.compile(r'^([A-Za-z][\w.-]*?)(@|>=|=)(\S+)$')
VER = r'(\d+(?:\.(?:\d+|x))*)'
OPS = {'@': 'pin', '>=': 'floor', '=': 'value'}


def read_tokens(rep: Report) -> dict:
    """{key: {'pin'|'floor'|'value': set of values}} from the Token column of VERSIONS.md."""
    keys = {}
    if not VERSIONS.is_file():
        rep.bad('versions: VERSIONS.md is missing')
        return keys
    header = None
    for no, line in enumerate(VERSIONS.read_text(encoding='utf-8').splitlines(), 1):
        if not line.startswith('|'):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if header is None:
            header = cells
            continue
        if set(line) <= set('|-: '):
            continue
        if 'Token' not in header:
            rep.bad(f'versions: VERSIONS.md:{no}: the table has no Token column')
            continue
        row = dict(zip(header, cells))
        tok = row.get('Token', '')
        named = re.search(r'`(com\.unity\.[\w.-]+)`', row.get('Fact', ''))
        if tok in ('—', '-'):
            if named:
                rep.bad(f'versions: VERSIONS.md:{no}: the row names {named.group(1)} but has no token')
            continue
        tokens = re.findall(r'`([^`]+)`', tok)
        if not tokens:
            rep.bad(f'versions: VERSIONS.md:{no}: empty Token cell (— for a fact that names no package or key)')
        for t in tokens:
            m = TOKEN.match(t)
            if not m:
                rep.bad(f'versions: VERSIONS.md:{no}: token {t!r} is not KEY@VERSION, KEY>=VERSION or KEY=VALUE')
                continue
            keys.setdefault(m.group(1), {}).setdefault(OPS[m.group(2)], set()).add(m.group(3))
    return keys


def value_ok(found: str, allowed: set) -> bool:
    """One version is a dotted prefix of the other (`5.4` and `5.4+` match 5.4.4), and an `x`
    matches any part (`17.x` matches 17.4.0 and 17.x.y)."""
    f = found.rstrip('+').split('.')
    for a in allowed:
        a = a.split('.')
        if all(x == y or 'x' in (x, y) for x, y in zip(a, f)):
            return True
    return False


def occurrences(text: str, key: str, kinds: dict):
    """(line no, kind, value) of each place a skill carries a value of a tracked kind for key."""
    k = re.escape(key)
    pats = []
    if 'pin' in kinds:
        pats += [('pin', rf'"{k}"\s*:\s*"{VER}'), ('pin', rf'(?<![\w.-]){k}@{VER}')]
    if 'floor' in kinds:
        pats += [('floor', rf'^\|\s*`{k}`\s*\|\s*\**{VER}'),          # a package table row
                 ('floor', rf'`{k}`\s*\**{VER}\+'),                    # `pkg` 1.2+
                 ('floor', rf'(?<![\w.-]){k}`?\s*>=\s*`?{VER}')]      # pkg >= 1.2
    if 'value' in kinds:
        stem = re.escape(key[:-len('Version')] if key.endswith('Version') else key)
        pats += [('value', rf'\b{stem}(?:Version)?\s*=\s*(?:\(AndroidSdkVersions\)\s*|AndroidSdkVersions\.AndroidApiLevel)(\d+)'),
                 ('value', rf'\b{stem}(?:Version)?\s*[=:]\s*"?(\d+)\b(?![.\w])')]
    for no, line in enumerate(text.splitlines(), 1):
        seen = set()
        for kind, p in pats:
            for m in re.finditer(p, line):
                if m.start(1) not in seen:
                    seen.add(m.start(1))
                    yield no, kind, m.group(1)


def check_versions(rep: Report) -> None:
    keys = read_tokens(rep)
    checked = 0
    exts = {'.md', '.cs', '.json', '.py', '.sh', '.txt', '.yml', '.yaml', '.gradle', '.kts', '.example'}
    for f in sorted(SKILLS.rglob('*')):
        if not f.is_file() or f.suffix not in exts or '__pycache__' in f.parts:
            continue
        text = f.read_text(encoding='utf-8', errors='replace')
        for key, kinds in keys.items():
            stem = key[:-len('Version')] if key.endswith('Version') else key
            if stem not in text:
                continue
            for no, kind, val in occurrences(text, key, kinds):
                checked += 1
                if not value_ok(val, kinds[kind]):
                    rep.bad(f'versions: {rel(f)}:{no}: {key} {val} is not a VERSIONS.md {kind} '
                            f'({", ".join(sorted(kinds[kind]))})')
    print(f'versions: {len(keys)} tracked keys, {checked} occurrences in skills/')


# ------------------------------------------------------------------------------------- main

class UsageParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f'{self.prog}: error: {message}\n')


def main() -> int:
    ap = UsageParser(description=__doc__.split('\n')[0])
    ap.add_argument('--only', action='append', choices=CHECKS, help='run only this check (repeatable)')
    ap.add_argument('--rows', metavar='TEXT', help='outputs: only the selftest rows whose path contains TEXT')
    ap.add_argument('--blender', metavar='PATH', help='outputs: also run the selftests that need Blender')
    a = ap.parse_args()
    rep = Report()
    for check in a.only or CHECKS:
        print(f'== {check}')
        try:
            if check == 'outputs':
                check_outputs(rep, a.blender, a.rows)
            elif check == 'flags':
                check_flags(rep)
            elif check == 'deps':
                check_deps(rep)
            else:
                check_versions(rep)
        except Exception as e:      # a crash here is the harness, never a verdict
            rep.broken(f'{check}: {type(e).__name__}: {e}')
    print(f'{len(rep.violations)} contract violations, {len(rep.harness)} harness errors')
    if rep.harness:
        return 3
    return 2 if rep.violations else 0


if __name__ == '__main__':
    sys.exit(main())
