#!/usr/bin/env python3
"""Collect the PDF attachments published on each registered trail's official page.

Uses only Python's standard library. An HTML cache outside the checkout makes
interrupted refreshes resumable. Failed requests abort publication of the index.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import time
import threading
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REGISTER = 'https://services-eu1.arcgis.com/CltcWyRoZmdwaB7T/ArcGIS/rest/services/GetIrelandActiveTrailRoutes/FeatureServer/0/query'
SOURCE_BLOCKED = threading.Event()

class SourceVerificationRequired(RuntimeError):
    pass

class MapParser(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.stack, self.links, self.anchor, self.title = base, [], [], None, []
        self.title_depth = None
        self.heading, self.in_heading = [], False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        in_maps = any('trail__maps' in c for _, c in self.stack)
        if tag == 'a' and in_maps:
            self.anchor = {'url': urljoin(self.base, attrs.get('href', ''))}
            self.title = []
        if self.anchor and 'file-downloads__item-title' in classes:
            self.title_depth = len(self.stack)
        if tag == 'h1': self.in_heading = True
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag):
        if tag == 'h1': self.in_heading = False
        if tag == 'a' and self.anchor:
            link = self.anchor
            if urlsplit(link['url']).path.lower().endswith('.pdf'):
                link['title'] = ' '.join(''.join(self.title).split()) or 'Trail map'
                if link['url'] not in {x['url'] for x in self.links}: self.links.append(link)
            self.anchor, self.title_depth = None, None
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                if self.title_depth is not None and i <= self.title_depth: self.title_depth = None
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.anchor and self.title_depth is not None: self.title.append(data)
        if self.in_heading: self.heading.append(data)


def fetch(url):
    for attempt in range(3):
        if SOURCE_BLOCKED.is_set(): raise SourceVerificationRequired('Source requires browser verification; refresh stopped')
        try:
            with urlopen(Request(url, headers={'User-Agent': 'IrelandTrailAtlas/1.0 (official map link index refresh)'}), timeout=45) as response:
                text = response.read().decode('utf-8')
                if any(marker in text.lower() for marker in ('browser verification', 'botbuster', 'verify you are human', 'checking your browser')):
                    SOURCE_BLOCKED.set()
                    raise SourceVerificationRequired('Source requires browser verification; refresh stopped')
                return text, response.geturl()
        except SourceVerificationRequired:
            raise
        except HTTPError as error:
            if error.code == 404: return '', url
            if error.code in (403, 429): raise
            if attempt == 2: raise
        except Exception:
            if attempt == 2: raise
        time.sleep(1 + attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--register', type=Path)
    parser.add_argument('--cache', type=Path, default=Path('/tmp/ireland-trail-map-pages'))
    parser.add_argument('--output', type=Path, default=Path('dist/data/trail-map-links.json'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--cached-only', action='store_true', help='Use saved HTML only and mark uncached pages as not checked')
    parser.add_argument('--allow-unavailable', action='store_true', help='Record inaccessible source pages instead of aborting')
    parser.add_argument('--recoveries', type=Path, help='Verified source-based recovery entries keyed by TrailID')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.register:
        register = json.loads(args.register.read_text())
    else:
        if args.cached_only: raise ValueError('--cached-only requires --register')
        text, _ = fetch(REGISTER + '?' + urlencode({'where':'1=1','outFields':'TrailID,Name,Website','returnGeometry':'false','f':'json'}))
        register = json.loads(text)
    if register.get('exceededTransferLimit') or not register.get('features'): raise RuntimeError('Incomplete register')
    routes = [f['attributes'] for f in register['features']]

    def collect(route):
        url = route['Website']
        if urlsplit(url).hostname != 'www.sportireland.ie': raise ValueError('Unexpected trail website: '+url)
        cached = args.cache / (sha256(url.encode()).hexdigest() + '.json')
        if cached.exists():
            document = json.loads(cached.read_text())
        elif args.cached_only:
            return str(route['TrailID']), {'name':route['Name'], 'pageUrl':url, 'status':'not_checked', 'maps':[]}
        else:
            text, final_url = fetch(url)
            document = {'html':text, 'url':final_url}
            cached.write_text(json.dumps(document))
        page = MapParser(document['url'])
        if any(marker in document['html'].lower() for marker in ('browser verification', 'botbuster', 'verify you are human', 'checking your browser')):
            raise SourceVerificationRequired('Cached verification page is not a trail page')
        page.feed(document['html'])
        status = 'available' if page.links else 'no_pdf' if document['html'] else 'page_unavailable'
        return str(route['TrailID']), {'name':route['Name'], 'pageUrl':url, 'pageTitle':' '.join(''.join(page.heading).split()), 'status':status, 'maps':page.links}

    entries, errors = {}, []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(collect,r):r for r in routes}
        for i, future in enumerate(as_completed(futures),1):
            try:
                key, entry = future.result()
                entries[key] = entry
            except Exception as error:
                errors.append((futures[future]['Name'], str(error)))
                print('Fetch failed: '+repr(errors[-1]),flush=True)
                if args.allow_unavailable:
                    route = futures[future]
                    entries[str(route['TrailID'])] = {'name':route['Name'], 'pageUrl':route['Website'], 'status':'page_unavailable', 'maps':[]}
            if i % 50 == 0 or i == len(routes): print(f'Processed {i}/{len(routes)}; PDFs on {sum(bool(e["maps"]) for e in entries.values())} trails; errors {len(errors)}', flush=True)
    if SOURCE_BLOCKED.is_set(): raise SourceVerificationRequired('Source requires browser verification; no new index written')
    if errors and not args.allow_unavailable: raise RuntimeError(json.dumps(errors,ensure_ascii=False))
    if args.recoveries:
        recovered = json.loads(args.recoveries.read_text())
        for key, entry in recovered.items():
            if key not in entries:
                continue
            current = entries[key]
            by_url = {item['url']: item for item in current.get('maps', []) if item.get('url')}
            for item in entry.get('maps', []):
                url = item.get('url')
                if not url:
                    continue
                by_url[url] = {**by_url.get(url, {}), **item}
            current['maps'] = list(by_url.values())
            if current['maps']:
                current['status'] = 'available'
    result = {'source':'Sport Ireland trail pages and linked map publishers', 'checkedAt':datetime.now(timezone.utc).isoformat(), 'trailCount':len(routes), 'checkedTrailCount':sum(e['status'] != 'not_checked' for e in entries.values()), 'complete':all(e['status'] != 'not_checked' for e in entries.values()), 'trails':dict(sorted(entries.items(),key=lambda x:int(x[0])))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'trails':len(entries),'checked':result['checkedTrailCount'],'with_maps':sum(bool(e['maps']) for e in entries.values()),'map_links':sum(len(e['maps']) for e in entries.values()),'not_checked':sum(e['status']=='not_checked' for e in entries.values())}),flush=True)

if __name__ == '__main__': main()
