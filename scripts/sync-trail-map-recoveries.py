#!/usr/bin/env python3
"""Persist verified non-native map links for the next index rebuild."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def inferred_format(item):
    if item.get('format'):
        return item['format']
    path = urlsplit(item.get('url', '')).path.lower()
    for suffix, fmt in (('.pdf', 'pdf'), ('.jpeg', 'jpg'), ('.jpg', 'jpg'),
                        ('.png', 'png'), ('.webp', 'webp'), ('.gif', 'gif')):
        if path.endswith(suffix):
            return fmt
    return 'web'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=Path('dist/data/trail-map-links.json'))
    parser.add_argument('--recoveries', type=Path, default=Path('docs/trail-map-link-recoveries.json'))
    args = parser.parse_args()
    index = json.loads(args.index.read_text())
    recoveries = json.loads(args.recoveries.read_text()) if args.recoveries.exists() else {}
    saved = 0
    for tid, entry in index['trails'].items():
        extras = []
        for item in entry.get('maps', []):
            host = (urlsplit(item.get('url', '')).hostname or '').lower()
            if not host.endswith('sportireland.ie') or inferred_format(item) != 'pdf' or item.get('verifiedAt') or item.get('mapSourcePage'):
                extras.append({**item, 'format': inferred_format(item)})
        if not extras:
            continue
        recovery = recoveries.setdefault(tid, {
            'name': entry['name'], 'pageUrl': entry['pageUrl'], 'status': 'available', 'maps': []
        })
        merged = {m['url']: m for m in recovery.get('maps', []) if m.get('url')}
        for item in extras:
            merged[item['url']] = {**merged.get(item['url'], {}), **item}
            saved += 1
        recovery.update({'name': entry['name'], 'pageUrl': entry['pageUrl'], 'status': 'available', 'maps': list(merged.values())})
        if not recovery.get('recoverySource'):
            recovery['recoverySource'] = next((m.get('mapSourcePage') for m in extras if m.get('mapSourcePage')), entry['pageUrl'])
        if not recovery.get('recoveryEvidence'):
            recovery['recoveryEvidence'] = 'Verified publisher maps are retained in the individual map records.'
    args.recoveries.parent.mkdir(parents=True, exist_ok=True)
    args.recoveries.write_text(json.dumps(recoveries, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'recovered_trails': len(recoveries), 'non_native_maps_saved': saved}))


if __name__ == '__main__':
    main()
