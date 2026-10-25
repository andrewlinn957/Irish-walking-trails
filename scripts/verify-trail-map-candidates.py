#!/usr/bin/env python3
"""Validate supplemental map links with one paced request at a time, then merge.

Candidates must carry a matching trail ID and Sport Ireland source page. The
script reads only a small response prefix, identifies file signatures, and saves
results after each request. Verification/rate limits stop further requests to
that host. Existing maps are preserved.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MARKERS=('browser verification','botbuster','verify you are human','checking your browser','just a moment...')
MIME_FORMATS={'application/pdf':'pdf','image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/gif':'gif','text/html':'web'}


def file_format(data):
    if b'%PDF-' in data[:1024]: return 'pdf'
    if data.startswith(b'\xff\xd8\xff'): return 'jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'png'
    if data[:6] in (b'GIF87a',b'GIF89a'): return 'gif'
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP': return 'webp'
    return None


def save_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--index',type=Path,default=Path('dist/data/trail-map-links.json'))
    parser.add_argument('--report',type=Path,default=Path('docs/trail-map-download-checks.json'))
    parser.add_argument('--interval',type=float,default=5)
    parser.add_argument('--trust-verified',action='store_true',help='Accept documented prevalidated candidates without duplicate requests')
    args=parser.parse_args()
    if args.interval<5: parser.error('Use an interval of at least five seconds')
    candidates=json.loads(args.candidates.read_text())['candidates']
    index=json.loads(args.index.read_text())
    report=json.loads(args.report.read_text()) if args.report.exists() else {'checks':{}}
    blocked=set()
    last_request=None
    added=0
    for candidate in candidates:
        url=candidate['url']
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or parsed.username or parsed.password: raise ValueError('Invalid map URL')
        resource_type=candidate.get('resourceType','map')
        if resource_type not in ('map','guide'): raise ValueError('Unsupported resource type')
        allow_secondary=candidate.get('kind')=='map-image' or candidate.get('allowSecondary')
        associations=[a for a in candidate['associations'] if a['trailId'] in index['trails'] and index['trails'][a['trailId']]['pageUrl']==a['sourcePage'] and (allow_secondary or not index['trails'][a['trailId']].get('maps')) and url not in {m['url'] for m in index['trails'][a['trailId']].get('maps',[])}]
        if not associations: continue
        check=report['checks'].get(url)
        candidate_mime=(candidate.get('contentType') or '').split(';')[0].lower()
        candidate_format=MIME_FORMATS.get(candidate_mime)
        trusted_pdf=candidate_format=='pdf' and candidate.get('kind')=='pdf'
        trusted_image=bool(candidate.get('signatureVerified')) and candidate_format in {'jpg','png','webp','gif'}
        trusted_web=candidate_format=='web' and candidate.get('mapPageVerified') and candidate.get('kind')=='download-endpoint'
        if not check and args.trust_verified and candidate.get('verifiedAt') and candidate_format and (trusted_pdf or trusted_image or trusted_web):
            check={'status':'available','format':candidate_format,'verifiedAt':candidate['verifiedAt'],'contentType':candidate_mime,'sourcePage':candidate.get('sourcePage'),'evidence':candidate.get('evidence','Signature and content type verified from source audit')}
        if not check:
            if parsed.hostname in blocked: continue
            if last_request is not None: time.sleep(max(0,args.interval-(time.monotonic()-last_request)))
            print('Checking '+url,flush=True)
            try:
                with urlopen(Request(url,headers={'User-Agent':'IrelandTrailAtlas/1.0 (official map link index refresh)','Range':'bytes=0-32767','Accept-Encoding':'identity'}),timeout=25) as response:
                    data=response.read(32768)
                    mime=response.headers.get('Content-Type','').split(';')[0].lower()
                    final=response.geturl()
                    fmt=file_format(data)
                    text=data.decode('utf-8',errors='replace').lower() if not fmt else ''
                    if any(m in text for m in MARKERS):
                        blocked.add(parsed.hostname)
                        check={'status':'verification_required'}
                    elif fmt:
                        check={'status':'available','format':fmt,'contentType':mime,'resolvedUrl':final}
                    elif mime=='text/html' and candidate['kind'] in ('download-endpoint','map-attachment'):
                        check={'status':'available','format':'web','contentType':mime,'resolvedUrl':final}
                    else:
                        check={'status':'not_map_file','contentType':mime,'resolvedUrl':final}
            except HTTPError as error:
                body=error.read(32768).decode(errors='replace').lower()
                restricted=error.code==429 or any(m in body for m in MARKERS)
                if restricted: blocked.add(parsed.hostname)
                check={'status':'verification_required' if restricted else 'unavailable','httpStatus':error.code}
            except Exception as error:
                check={'status':'request_failed','error':str(error)}
            last_request=time.monotonic()
            check['verifiedAt']=datetime.now(timezone.utc).isoformat()
            print(check['status'],flush=True)
        report['checks'][url]=check
        save_json(args.report,report)
        if check['status']!='available': continue
        for assoc in associations:
            entry=index['trails'][assoc['trailId']]
            if url in {m['url'] for m in entry['maps']}: continue
            publisher=candidate.get('sourcePage')
            suffix=Path(urlsplit(publisher).path).suffix.lower() if publisher else ''
            map_source={'mapSourcePage':publisher} if publisher and not suffix else {}
            entry['maps'].append({'url':url,'title':assoc.get('title') or 'Official trail map','format':check['format'],'resourceType':resource_type,'sourcePage':assoc['sourcePage'],'verifiedAt':check['verifiedAt'],**map_source,**({'evidence':assoc.get('matchedRoutesEvidence') or candidate.get('evidence')} if assoc.get('matchedRoutesEvidence') or candidate.get('evidence') else {}),**({'publisherNotice':candidate['publisherNotice']} if candidate.get('publisherNotice') else {})})
            entry['status']='available'
            added+=1
        index['checkedTrailCount']=sum(e['status']!='not_checked' for e in index['trails'].values())
        index['complete']=all(e['status']!='not_checked' for e in index['trails'].values())
        index['checkedAt']=datetime.now(timezone.utc).isoformat()
        save_json(args.index,index)
    print(json.dumps({'map_links_added':added,'urls_checked':len(report['checks']),'blocked_hosts':sorted(blocked)}),flush=True)

if __name__=='__main__': main()
