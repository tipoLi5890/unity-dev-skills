#!/usr/bin/env python3
"""Gate the two things that can drift silently between a file and its duplicate.

Each check exists because the fact it guards is written down in two places, and
nothing else notices when only one of them is updated.

1. The two manifests under `.claude-plugin/` are both sources of truth and both
   carry the plugin's description, author, homepage and licence. Editing one is
   the normal way to leave the other stale.
2. This plugin claims to be self-contained. It does route to a handful of
   sibling plugins, deliberately — but each of those has to be declared here, so
   that adding an external dependency is an edit someone made on purpose.

  python3 tools/check-consistency.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# External plugins and skills that live outside this repo, which a routing
# section may point at. Adding an entry is how you declare a new dependency —
# the gate exists so that it cannot happen by accident.
COMPANIONS: dict[str, str] = {}

# Sections whose job is to send the reader somewhere else. A plugin name in one
# of these is a routing target; the same name in body prose is a mention.
ROUTING_HEADING = re.compile(r'^## (Scope —|Related skills|Load what|Symptom →|Getting there)')

# Kebab-case, which is the shape a plugin or skill name takes. Deliberately does
# not match `com.unity.pipeline`, `eval_file` or `OnGUI`.
KEBAB = re.compile(r'`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`')

INSTALL_DIRECTIVE = re.compile(r'(claude )?plugin (install|marketplace add)')


def skill_names() -> set:
    return {d.name for d in (ROOT / 'skills').iterdir() if d.is_dir()}


def check_manifests_agree() -> list:
    """`.claude-plugin/plugin.json` and the marketplace entry describe one plugin."""
    plugin = json.loads((ROOT / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))
    market = json.loads((ROOT / '.claude-plugin' / 'marketplace.json').read_text(encoding='utf-8'))

    entries = [e for e in market.get('plugins', []) if e.get('name') == plugin.get('name')]
    if len(entries) != 1:
        return [f"marketplace.json has {len(entries)} entries named {plugin.get('name')!r}, expected 1"]

    errors = []
    for field in ('description', 'author', 'homepage', 'license'):
        a, b = plugin.get(field), entries[0].get(field)
        if a == b:
            continue
        if isinstance(a, str) and isinstance(b, str):
            # These run to thousands of characters and usually share a long prefix,
            # so say where they diverge rather than printing two identical-looking heads.
            i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            errors.append(f'{field}: plugin.json and the marketplace entry diverge at character {i} '
                          f'(len {len(a)} vs {len(b)}): ...{a[i:i + 50]!r} vs ...{b[i:i + 50]!r}')
        else:
            errors.append(f'{field}: plugin.json has {a!r}, the marketplace entry has {b!r}')
    return errors


def check_external_routing_is_declared() -> list:
    """Every plugin a routing section points at is either in this repo or declared above."""
    names = skill_names()
    errors, seen = [], set()

    for f in sorted((ROOT / 'skills').rglob('*.md')):
        text = f.read_text(encoding='utf-8')
        rel = f.relative_to(ROOT)

        if m := INSTALL_DIRECTIVE.search(text):
            errors.append(f'{rel}: contains an install directive ({m.group(0)!r}) — '
                          'a skill must not tell the reader to go install something first')

        keep, region = False, []
        for line in text.splitlines() + ['## ']:      # sentinel closes the last section
            if line.startswith('## '):
                for tok in KEBAB.findall('\n'.join(region)):
                    if tok in names:
                        continue
                    seen.add(tok)
                    if tok not in COMPANIONS:
                        errors.append(f'{rel}: routing section points at `{tok}`, which is neither a '
                                      'skill in this repo nor a declared companion — add it to '
                                      'COMPANIONS in tools/check-consistency.py, with the reason')
                keep, region = bool(ROUTING_HEADING.match(line)), []
            if keep:
                region.append(line)

    if stale := sorted(set(COMPANIONS) - seen):
        errors.append(f'COMPANIONS declares {stale}, which no routing section points at any more — '
                      'drop the entry')
    return errors


def main() -> int:
    checks = (
        ('manifests agree', check_manifests_agree),
        ('external routing is declared', check_external_routing_is_declared),
    )
    total = 0
    for label, fn in checks:
        errors = fn()
        total += len(errors)
        for e in errors:
            print('ERROR', e)
        print(f'{label}: {"FAILED" if errors else "OK"}')
    print(f'{len(checks)} consistency checks, {total} errors')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
