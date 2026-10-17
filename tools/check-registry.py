#!/usr/bin/env python3
"""Gate the asset registry and where the 3D budget defaults live.

The registry is the one place a project records what it has and how it was made,
and the default budget table is the one place a 3D asset class's numbers start
from. Both are easy to break without anything else noticing.

  a  `registry.py selftest` exits 0.
  b  Every fixture directory under the registry's `fixtures/negative/` makes
     `registry.py check` exit 2 or 3 and print each line of the fixture's EXPECT
     file. The check runs from the fixture directory; its arguments are the
     fixture's ARGS file (shell words) when there is one, otherwise
     `--ledger <ledger>` when the fixture holds exactly one *.jsonl, which is also
     set as ART_LEDGER.
  c  The default budget table exists once: unity-3d-models/reference/budgets.md
     has a table whose first column is `class` and which has a triangle, face or
     texture column; no other skill file has such a table listing three or more
     of its classes as rows (a one-row example is fine); and
     codex-visual/reference/art-direction-schema.md points at
     `unity-3d-models` → `reference/budgets.md` instead.
  d  No skill file still carries one of the four fixed triangle bands the skills
     used to quote (OBSOLETE_TRIS below) or the old `hero` budget class, unless the
     line says it is removed or obsolete. A budget is a row a person chose in the
     project's ART_DIRECTION.md, not a number written in prose.

Stdlib only.

  python3 tools/check-registry.py
"""
import os
import pathlib
import re
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

REGISTRY = 'skills/art-asset-registry/scripts/registry.py'
NEGATIVE = 'skills/art-asset-registry/scripts/fixtures/negative'
BUDGETS = 'skills/unity-3d-models/reference/budgets.md'
SCHEMA = 'skills/codex-visual/reference/art-direction-schema.md'

TIMEOUT = 900

OBSOLETE_TRIS = re.compile(r'(?<![\d.])(?:0\.5[–-]2k|2[–-]5k|3[–-]10k|1[–-]5k)(?![A-Za-z0-9])')
HERO_ROW = re.compile(r'\bhero\s*\|')
HERO_PY = re.compile(r'''(["'])hero\1''')
EXEMPT = re.compile(r'removed|obsolete', re.I)
RULE_ROW = re.compile(r'^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$')
BUDGET_COLUMN = re.compile(r'\btris?\b|_tris\b|triangle|\bfaces?\b|_faces\b|tex_px|texture', re.I)
POINTER = re.compile(r'`unity-3d-models`\s*(?:→|->)\s*`reference/budgets\.md`')


def run(args: list, cwd: pathlib.Path = ROOT, env: dict | None = None) -> tuple:
    """(exit code, stdout + stderr) of `python <args>`; the code is None on a timeout."""
    env = dict(os.environ if env is None else env, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    try:
        r = subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, f'timed out after {TIMEOUT}s'
    return r.returncode, r.stdout + r.stderr


def tail(out: str, n: int = 15) -> str:
    lines = out.rstrip().splitlines()[-n:]
    return ''.join(f'\n    {line}' for line in lines)


def stage_registry_selftest() -> tuple:
    if not (ROOT / REGISTRY).is_file():
        return [f'{REGISTRY}: missing, so its selftest cannot run'], None
    code, out = run([str(ROOT / REGISTRY), 'selftest'])
    return ([] if code == 0 else [f'{REGISTRY}: `selftest` exited {code}, expected 0{tail(out)}']), None


def stage_negative_fixtures() -> tuple:
    base = ROOT / NEGATIVE
    if not base.is_dir():
        return [], f'{NEGATIVE}/ not present'
    if not (ROOT / REGISTRY).is_file():
        return [], f'{REGISTRY} not present (stage a reports it)'
    fixtures = sorted(d for d in base.iterdir() if d.is_dir())
    if not fixtures:
        return [f'{NEGATIVE}: no fixture directories'], None
    errors = []
    for d in fixtures:
        rel = d.relative_to(ROOT)
        expect = d / 'EXPECT'
        wanted = [line.strip() for line in expect.read_text(encoding='utf-8').splitlines()
                  if line.strip() and not line.lstrip().startswith('#')] if expect.is_file() else []
        if not wanted:
            errors.append(f'{rel}: no EXPECT file naming the error this fixture must produce')
            continue
        env = {k: v for k, v in os.environ.items() if k != 'ART_LEDGER'}
        if (d / 'ARGS').is_file():
            args = shlex.split((d / 'ARGS').read_text(encoding='utf-8'), comments=True)
        else:
            ledgers = sorted(d.rglob('*.jsonl'))
            args = ['--ledger', str(ledgers[0])] if len(ledgers) == 1 else []
            if len(ledgers) == 1:
                env['ART_LEDGER'] = str(ledgers[0])
        code, out = run([str(ROOT / REGISTRY), 'check', *args], cwd=d, env=env)
        if code not in (2, 3):
            errors.append(f'{rel}: `registry.py check` exited {code}, expected 2 or 3{tail(out)}')
        for name in wanted:
            if name not in out:
                errors.append(f'{rel}: `registry.py check` never printed {name!r}{tail(out)}')
    return errors, None


def _cells(line: str) -> list:
    return [re.sub(r'[`*]', '', c).strip().lower() for c in line.strip().strip('|').split('|')]


def budget_tables(text: str) -> list:
    """(line number, {first-column cells of its rows}) of each Markdown table, outside code
    fences, whose header starts with a `class` cell and has a triangle, face or texture column:
    the shape of a budget table."""
    lines, found, fence = text.splitlines(), [], None
    for i, line in enumerate(lines[:-1]):
        m = re.match(r'\s*(`{3,}|~{3,})', line)
        if m:
            mark = m.group(1)[0]
            fence = mark if fence is None else (None if fence == mark else fence)
            continue
        if fence is not None or '|' not in line or not RULE_ROW.match(lines[i + 1]):
            continue
        cells = _cells(line)
        if cells and cells[0] == 'class' and any(BUDGET_COLUMN.search(c) for c in cells[1:]):
            rows = set()
            for row in lines[i + 2:]:
                if '|' not in row:
                    break
                rows.add(_cells(row)[0])
            found.append((i + 1, rows))
    return found


COPIED = 3        # a table outside BUDGETS listing this many default classes is a copy


def stage_budget_home() -> tuple:
    errors = []
    budgets, schema = ROOT / BUDGETS, ROOT / SCHEMA
    defaults = set()
    if not budgets.is_file():
        errors.append(f'{BUDGETS}: missing; the default budget table lives there')
    else:
        tables = budget_tables(budgets.read_text(encoding='utf-8'))
        if not tables:
            errors.append(f'{BUDGETS}: no table whose first column is `class` with a triangle, '
                          'face or texture column; the default budget table lives here')
        defaults = set().union(*(rows for _, rows in tables)) - {''}
    for f in sorted((ROOT / 'skills').rglob('*.md')):
        rel = f.relative_to(ROOT).as_posix()
        if rel == BUDGETS:
            continue
        for n, rows in budget_tables(f.read_text(encoding='utf-8')):
            if len(rows & defaults) >= COPIED:
                errors.append(f'{rel}:{n}: a copy of the default budget table '
                              f'({", ".join(sorted(rows & defaults))}); the defaults live only in '
                              f'{BUDGETS}: point at `unity-3d-models` → `reference/budgets.md`')
    if not schema.is_file():
        errors.append(f'{SCHEMA}: missing')
        return errors, None
    text = schema.read_text(encoding='utf-8')
    if not POINTER.search(text):
        errors.append(f'{SCHEMA}: no pointer `unity-3d-models` → `reference/budgets.md` for the '
                      'default budget table')
    return errors, None


def stage_obsolete_budgets() -> tuple:
    errors = []
    files = sorted(p for pattern in ('*.md', '*.py') for p in (ROOT / 'skills').rglob(pattern)
                   if '__pycache__' not in p.parts)
    for f in files:
        rel = f.relative_to(ROOT)
        for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            if EXEMPT.search(line):
                continue
            if m := OBSOLETE_TRIS.search(line):
                errors.append(f'{rel}:{n}: fixed triangle budget {m.group(0)!r}: a budget is a row '
                              f'of the project\'s ART_DIRECTION.md, its defaults in {BUDGETS}')
            if f.suffix == '.md' and line.lstrip().startswith('|') and HERO_ROW.search(line):
                errors.append(f'{rel}:{n}: `hero` as a budget class: the classes are the rows of '
                              f'{BUDGETS}')
            if f.suffix == '.py' and HERO_PY.search(line):
                errors.append(f'{rel}:{n}: "hero" as a budget class: the classes are the rows of '
                              f'{BUDGETS}')
    return errors, None


def main() -> int:
    stages = (
        ('a registry selftest', stage_registry_selftest),
        ('b negative fixtures', stage_negative_fixtures),
        ('c the default budget table lives in one place', stage_budget_home),
        ('d no fixed triangle budgets', stage_obsolete_budgets),
    )
    sys.dont_write_bytecode = True
    total = 0
    for label, fn in stages:
        errors, skipped = fn()
        total += len(errors)
        for e in errors:
            print('ERROR', e)
        print(f'{label}: {"FAILED" if errors else f"SKIPPED ({skipped})" if skipped else "OK"}')
    print(f'{len(stages)} registry and budget stages, {total} errors')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
