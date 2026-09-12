#!/usr/bin/env python3
"""Regenerate the Codex-format manifests from the Claude-format sources of truth.

Sources of truth (edit these):   .claude-plugin/plugin.json
                                 .claude-plugin/marketplace.json
Generated (never hand-edit):     .codex-plugin/plugin.json
                                 .agents/plugins/marketplace.json

  python3 tools/sync-codex-manifests.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(p: pathlib.Path):
    return json.loads(p.read_text(encoding='utf-8'))


def dump(p: pathlib.Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main() -> int:
    plugin = load(ROOT / '.claude-plugin' / 'plugin.json')
    market = load(ROOT / '.claude-plugin' / 'marketplace.json')

    # Codex plugin manifest: the Claude one plus where its skills live.
    codex_plugin = dict(plugin)
    codex_plugin['skills'] = './skills/'
    dump(ROOT / '.codex-plugin' / 'plugin.json', codex_plugin)

    entries = []
    for e in market.get('plugins', []):
        src = e.get('source')
        source = {'source': 'local', 'path': src} if isinstance(src, str) else src
        entry = {'name': e['name'], 'description': e['description'], 'source': source}
        if 'homepage' in e:
            entry['homepage'] = e['homepage']
        entries.append(entry)
    dump(ROOT / '.agents' / 'plugins' / 'marketplace.json', {
        'name': market['name'],
        'description': market['description'],
        'plugins': entries,
    })
    print(f'synced 1 plugin manifest, {len(entries)} marketplace entry/entries')
    return 0


if __name__ == '__main__':
    sys.exit(main())
