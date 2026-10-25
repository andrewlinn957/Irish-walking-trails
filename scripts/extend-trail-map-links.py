#!/usr/bin/env python3
"""Extend the existing map index with sequential, paced requests for unchecked trails.

Each successful result is saved atomically. The updater stops on a verification
page or HTTP 429, and never retries a failed request during the same run.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

spec = importlib.util.spec_from_file_location('trail_maps', Path(__file__).with_name('build-trail-map-links.py'))
trail_maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trail_maps)
MARKERS = ('browser verification', 'botbuster', 'verify you are human', 'checking your browser')


def verification_page(text):
    return any(marker in text.lower() for marker in MARKERS)


def save(index, output):
    index['checkedAt'] = datetime.now(timezone.utc).isoformat()
    index['checkedTrailCount'] = sum(e['status'] != 'not_checked' for e in index['trails'].values())
    index['complete'] = all(e['status'] != 'not_checked' for e in index['trails'].values())
    temporary = output.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=Path('dist/data/trail-map-links.json'))
    parser.add_argument('--cache', type=Path, default=Path('/tmp/ireland-trail-map-pages'))
    parser.add_argument('--max-pages', type=int, default=60)
    parser.add_argument('--interval', type=float, default=15, help='Seconds of pause after each completed request (default 15; minimum 5)')
    parser.add_argument('--stop-file', type=Path, default=Path('/tmp/stop-trail-map-refresh'))
    args = parser.parse_args()
    if args.interval < 5 or args.max_pages < 1: parser.error('Use interval >= 5 and max-pages >= 1')
    index = json.loads(args.index.read_text())
    pending = [(k,e) for k,e in index['trails'].items() if e['status']=='not_checked']
    args.cache.mkdir(parents=True,exist_ok=True)
    added, processed, requests, errors = 0, 0, 0, 0
    before = sum(bool(e['maps']) for e in index['trails'].values())
    for key, entry in pending:
        if requests >= args.max_pages or args.stop_file.exists(): break
        url = entry['pageUrl']
        if urlsplit(url).hostname != 'www.sportireland.ie': raise ValueError('Unexpected source host')
        cached = args.cache / (sha256(url.encode()).hexdigest()+'.json')
        if cached.exists():
            document = json.loads(cached.read_text())
            text = document['html']
        else:
            if requests: time.sleep(args.interval)
            if args.stop_file.exists(): break
            requests += 1
            print(f'Request {requests}/{args.max_pages}: {entry["name"]}',flush=True)
            try:
                with urlopen(Request(url, headers={'User-Agent':'IrelandTrailAtlas/1.0 (official map link index refresh)'}),timeout=30) as response:
                    text = response.read().decode('utf-8')
                    document = {'url':response.geturl(), 'html':text}
            except HTTPError as error:
                body = error.read().decode(errors='replace')
                if verification_page(body) or error.code == 429:
                    print(f'STOP: source verification or rate limit (HTTP {error.code}).',flush=True)
                    break
                if error.code in (403,404):
                    entry['status'] = 'page_unavailable'
                    save(index,args.index)
                errors += 1
                print(f'HTTP {error.code}; no retry.',flush=True)
                if errors >= 3:
                    print('STOP: three consecutive source errors.',flush=True)
                    break
                continue
            except Exception as error:
                errors += 1
                print(f'Request failed; no retry: {type(error).__name__}: {error}',flush=True)
                if errors >= 3:
                    print('STOP: three consecutive request failures.',flush=True)
                    break
                continue
            if verification_page(text):
                print('STOP: source requires browser verification.',flush=True)
                break
            cached.write_text(json.dumps(document))
        if verification_page(text):
            print('STOP: verification page found in cache.',flush=True)
            break
        page = trail_maps.MapParser(document['url'])
        page.feed(text)
        # A nonempty response without the trail's heading is not a valid no-map result.
        if text and not page.heading:
            print('STOP: unexpected page response; no map status written.',flush=True)
            break
        entry.update({'maps':page.links,'status':'available' if page.links else 'no_pdf' if text else 'page_unavailable','pageTitle':' '.join(''.join(page.heading).split())})
        save(index,args.index)
        errors = 0
        processed += 1
        added += bool(page.links)
        print(f'Saved {entry["name"]}: {len(page.links)} PDFs. New trails with maps: {added}',flush=True)
    print(json.dumps({'requests':requests,'processed':processed,'additional_trails_with_maps':sum(bool(e['maps']) for e in index['trails'].values())-before,'total_trails_with_maps':sum(bool(e['maps']) for e in index['trails'].values()),'total_pdf_links':sum(len(e['maps']) for e in index['trails'].values()),'remaining_unchecked':sum(e['status']=='not_checked' for e in index['trails'].values())}),flush=True)

if __name__=='__main__': main()
