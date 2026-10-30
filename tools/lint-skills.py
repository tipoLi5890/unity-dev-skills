#!/usr/bin/env python3
"""Gate every skills/*/SKILL.md and every shipped executable.

A YAML failure means the skill silently fails to load — it does not error, it
just is not there. That is why CI runs this on every push and pull request, not
only at release time.

Checks: the frontmatter block exists, its YAML parses, `name` equals the skill
directory name, `description` is non-empty and inside its character budget, and
SKILL.md is inside its size budget; and that the skill listing as a whole (every
name and description together) fits the listing budget. Then syntax-gates what
ships alongside: `bash -n` for shell, the builtin `compile()` for Python (so no
__pycache__ is written), `node --check` for JS when node is present.

  python3 tools/lint-skills.py
"""
import pathlib
import re
import shutil
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The two budgets a skill stays inside. `description` is trigger text that every
# session loads, so it is charged on every conversation; SKILL.md is a router, and
# depth belongs in the reference/ files it names rather than in the router itself.
MAX_SKILL_BYTES = 12 * 1024
MAX_DESCRIPTION_CHARS = 250

# Claude Code budgets the skill listing at about 1% of the context window — about
# 8,000 characters at 200K — and drops descriptions once the listing overflows, so a
# skill past the budget is listed by name alone and stops triggering. The estimate is
# each line as the listing writes it: `- unity-dev:<name>: <description>`.
PLUGIN_PREFIX = 'unity-dev'
LISTING_BUDGET_CHARS = 8000


def lint_executables() -> list:
    errors = []
    for f in ROOT.glob('skills/**/*.sh'):
        r = subprocess.run(['bash', '-n', str(f)], capture_output=True, text=True)
        if r.returncode != 0:
            errors.append(f'{f.relative_to(ROOT)}: bash -n failed: {r.stderr.strip()[:120]}')
    pys = [p for p in list(ROOT.glob('skills/**/*.py')) + list(ROOT.glob('tools/*.py'))
           if '__pycache__' not in p.parts]
    for f in pys:
        try:
            compile(f.read_bytes(), str(f), 'exec')
        except (SyntaxError, ValueError) as e:
            errors.append(f'{f.relative_to(ROOT)}: compile failed: {str(e)[:120]}')
    if shutil.which('node'):
        for f in ROOT.glob('skills/**/*.js'):
            r = subprocess.run(['node', '--check', str(f)], capture_output=True, text=True)
            if r.returncode != 0:
                errors.append(f'{f.relative_to(ROOT)}: node --check failed: {r.stderr.strip()[:120]}')
    return errors


def main() -> int:
    skills = sorted(ROOT.glob('skills/*/SKILL.md'))
    if not skills:
        print('no skills found under skills/ — wrong directory?')
        return 1
    fm_errors = []
    listing_chars = 0
    for f in skills:
        rel = f.relative_to(ROOT)
        size = f.stat().st_size
        if size > MAX_SKILL_BYTES:
            fm_errors.append(f'{rel}: {size} bytes, over the {MAX_SKILL_BYTES}-byte limit')
        m = re.match(r'^---\n(.*?)\n---\n', f.read_text(encoding='utf-8'), re.DOTALL)
        if not m:
            fm_errors.append(f'{rel}: no frontmatter block')
            continue
        try:
            fm = yaml.safe_load(m.group(1))
        except yaml.YAMLError as e:
            fm_errors.append(f'{rel}: YAML does not parse: {str(e)[:120]}')
            continue
        if not isinstance(fm, dict):
            fm_errors.append(f'{rel}: frontmatter is not a mapping')
            continue
        if fm.get('name') != f.parent.name:
            fm_errors.append(f"{rel}: name={fm.get('name')!r} != directory {f.parent.name!r}")
        description = str(fm.get('description') or '')
        listing_chars += len(f'- {PLUGIN_PREFIX}:{f.parent.name}: {description}\n')
        if not description.strip():
            fm_errors.append(f'{rel}: empty description')
        elif len(description) > MAX_DESCRIPTION_CHARS:
            fm_errors.append(f'{rel}: description is {len(description)} characters, over the '
                             f'{MAX_DESCRIPTION_CHARS}-character limit')

    listing_errors = []
    if listing_chars > LISTING_BUDGET_CHARS:
        listing_errors.append(f'skill listing: about {listing_chars} characters for {len(skills)} skills, '
                              f'over the {LISTING_BUDGET_CHARS}-character listing budget')

    exe_errors = lint_executables()
    errors = fm_errors + listing_errors + exe_errors
    for e in errors:
        print('ERROR', e)
    # Count the OK skills from the SKILL.md failures alone. A broken script is keyed on
    # its own path, so counting those here would report fewer good skills than there are.
    ok = len(skills) - len({e.split(':')[0] for e in fm_errors})
    print(f'{len(skills)} SKILL.md scanned, {ok} OK, '
          f'{len(errors)} errors; listing {listing_chars}/{LISTING_BUDGET_CHARS} characters; '
          f'executables gate: {"FAILED" if exe_errors else "OK"}')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
