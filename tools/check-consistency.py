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


# A skill is self-contained, so code that several skills need is pasted into
# each of them between these two markers. The canonical copy is
# tools/shared-blocks/<name>.py, whose first line names every file that carries it.
SHARED_BLOCKS = ROOT / 'tools' / 'shared-blocks'
SHARED_MARKER = re.compile(r'^\s*# (>>>|<<<) shared:([A-Za-z0-9_.-]+)(?:\s.*)?$')
TARGETS_LINE = re.compile(r'^# targets:(.*)$')


def _trim_blank_ends(lines: list) -> list:
    start = next((i for i, line in enumerate(lines) if line.strip()), len(lines))
    end = next((i for i in range(len(lines), start, -1) if lines[i - 1].strip()), start)
    return lines[start:end]


def _shared_regions(path: pathlib.Path, errors: list) -> dict:
    """{name: [(first line number, body lines), ...]} for the marked regions in one file."""
    rel, regions, open_name, open_at, body = path.relative_to(ROOT), {}, None, 0, []
    for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        m = SHARED_MARKER.match(line)
        if not m:
            if open_name:
                body.append(line)
            continue
        kind, name = m.groups()
        if kind == '>>>':
            if open_name:
                errors.append(f'{rel}:{n}: `# >>> shared:{name}` opens inside '
                              f'`shared:{open_name}`, which line {open_at} opened and never closed')
            open_name, open_at, body = name, n, []
        elif name != open_name:
            errors.append(f'{rel}:{n}: `# <<< shared:{name}` closes a region that was never opened')
        else:
            regions.setdefault(name, []).append((open_at, _trim_blank_ends(body)))
            open_name = None
    if open_name:
        errors.append(f'{rel}:{open_at}: `# >>> shared:{open_name}` is never closed')
    return regions


def check_shared_blocks() -> list:
    """Every pasted copy of a tools/shared-blocks/<name>.py equals the canonical file.

    The canonical body is everything after its `# targets:` line, without leading
    or trailing blank lines; a copy is what sits between `# >>> shared:<name>` and
    `# <<< shared:<name>`, trimmed the same way. A listed target that does not exist
    yet is skipped; one that exists without the region is an error, and so is a
    region in a file the canonical does not list, since nothing keeps it in step.
    """
    canon = sorted(SHARED_BLOCKS.glob('*.py')) if SHARED_BLOCKS.is_dir() else []
    errors, blocks = [], {}
    for f in canon:
        rel, lines = f.relative_to(ROOT), f.read_text(encoding='utf-8').splitlines()
        m = TARGETS_LINE.match(lines[0]) if lines else None
        targets = [pathlib.PurePosixPath(t.strip()).as_posix()
                   for t in m.group(1).split(',') if t.strip()] if m else []
        if not targets:
            errors.append(f'{rel}: the first line must be `# targets: <path>, <path>` naming '
                          'the repo-relative files that carry a copy')
            continue
        body = _trim_blank_ends(lines[1:])
        if not body:
            errors.append(f'{rel}: nothing after the `# targets:` line')
            continue
        blocks[f.stem] = (rel, targets, body)

    files = {p for p in (ROOT / 'skills').rglob('*.py') if '__pycache__' not in p.parts}
    files |= {ROOT / t for _, targets, _ in blocks.values() for t in targets if (ROOT / t).is_file()}
    found = {p.relative_to(ROOT).as_posix(): _shared_regions(p, errors) for p in sorted(files)}

    for name, (rel, targets, body) in blocks.items():
        for t in targets:
            if t not in found:
                continue                       # not written yet: nothing to drift
            copies = found[t].get(name, [])
            if len(copies) != 1:
                errors.append(f'{t}: listed as a target of {rel}, but carries {len(copies)} '
                              f'`# >>> shared:{name}` regions, expected 1')
                continue
            at, copy = copies[0]
            if copy == body:
                continue
            i = next((i for i, (a, b) in enumerate(zip(copy, body)) if a != b), min(len(copy), len(body)))
            errors.append(f'{t}:{at}: the shared:{name} region differs from {rel} at block line '
                          f'{i + 1} (len {len(copy)} vs {len(body)}): '
                          f'{copy[i] if i < len(copy) else "<end>"!r} vs '
                          f'{body[i] if i < len(body) else "<end>"!r} — copy the canonical back in')
    for t, regions in found.items():
        for name in regions:
            if name not in blocks:
                errors.append(f'{t}: carries `# >>> shared:{name}`, but there is no '
                              f'tools/shared-blocks/{name}.py to check it against')
            elif t not in blocks[name][1]:
                errors.append(f'{t}: carries a copy of shared:{name}, but {blocks[name][0]} does '
                              'not list it under `# targets:` — add it there')
    return errors


def main() -> int:
    checks = (
        ('manifests agree', check_manifests_agree),
        ('external routing is declared', check_external_routing_is_declared),
        ('shared blocks match their canonical copy', check_shared_blocks),
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
