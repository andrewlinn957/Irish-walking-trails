#!/usr/bin/env python3
"""Offline audit only; never makes network requests. Safe to rerun as HTML cache grows."""
import argparse
import json, re
from pathlib import Path
from hashlib import sha256
from urllib.parse import urlsplit, urljoin, unquote
from html.parser import HTMLParser
from datetime import datetime, timezone
INDEX=Path('dist/data/trail-map-links.json')
CACHE=Path('/tmp/ireland-trail-map-pages')
OUT=Path('/tmp/trail-external-map-candidates-full.json')
FLAGS=Path('/tmp/trail-non-pdf-map-flags-full.json')
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
EXCLUDE=re.compile(r'timetable|application[ _-]*form|access[ _-]*form|waiver|consent[ _-]*form|privacy|cookie|accessibility[ _-]*statement|feedback[ _-]*form|registration[ _-]*form|insurance|risk[ _-]*assessment|festival[ _-]*poster|festival[ _-]*itinerary|walking[ _-]*festival[ _-]*poster|itinerary\.docx',re.I)
MAP_WORD=re.compile(r'map|trail|walking|paddling|blueway|brochure|guide|route',re.I)
DOWNLOAD_WORD=re.compile(r'download|\.pdf(?:\W|$)|\.jpe?g(?:\W|$)|\.png(?:\W|$)|\.webp(?:\W|$)|attachment|/media/|/files/',re.I)
class Parser(HTMLParser):
 def __init__(self,base):
  super().__init__(convert_charrefs=True);self.base=base;self.stack=[];self.anchor=None;self.anchors=[];self.images=[]
 def context(self):
  cls={x for _,classes in self.stack for x in classes}
  return 'maps' if 'trail__maps' in cls else 'external-links' if 'trail__external-links' in cls else 'other'
 def handle_starttag(self,tag,attrs):
  a=dict(attrs);section=self.context()
  if tag=='a':self.anchor={'url':urljoin(self.base,a.get('href','')),'section':section,'text':[],'download':a.get('download')}
  if tag=='img' and section=='maps':
   for key in ['src','data-src']:
    if a.get(key):self.images.append({'url':urljoin(self.base,a[key]),'section':section,'title':a.get('alt',''),'kind':'map-image'})
  if tag not in VOID:self.stack.append((tag,a.get('class','').split()))
 def handle_endtag(self,tag):
  if tag=='a' and self.anchor:
   a=self.anchor;a['title']=' '.join(''.join(a.pop('text')).split());self.anchors.append(a);self.anchor=None
  for i in range(len(self.stack)-1,-1,-1):
   if self.stack[i][0]==tag:del self.stack[i:];break
 def handle_data(self,data):
  if self.anchor:self.anchor['text'].append(data)
def classify(a):
 u=urlsplit(a['url']);path=unquote(u.path).lower();text=a['title'];hint=unquote(a['url'])+' '+text
 if u.scheme not in {'http','https'} or EXCLUDE.search(hint):return None
 if re.search(r'\.(?:jpe?g|png|webp|gif)$',path) and (a['section']=='maps' or (a['section']=='external-links' and MAP_WORD.search(hint))):return 'map-image'
 if path.endswith('.pdf'):
  if a['section']=='maps' or (a['section']=='external-links' and (MAP_WORD.search(hint) or a['download'] is not None)):return 'pdf'
  if re.search(r'download.*map|map.*download',text,re.I):return 'pdf'
 if a['section'] in {'maps','external-links'} and (a['download'] is not None or re.search(r'download.*map|map.*download',text,re.I)):
  return 'download-endpoint'
 # A map attachment within the maps section can have an opaque filename/endpoint.
 if a['section']=='maps' and (MAP_WORD.search(text) or DOWNLOAD_WORD.search(path)):return 'map-attachment'
 return None

def main():
 global INDEX,CACHE,OUT,FLAGS
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--index',type=Path,default=INDEX)
 parser.add_argument('--cache',type=Path,default=CACHE)
 parser.add_argument('--output',type=Path,default=OUT)
 parser.add_argument('--flags',type=Path,default=FLAGS)
 args=parser.parse_args()
 INDEX,CACHE,OUT,FLAGS=args.index,args.cache,args.output,args.flags
 idx=json.loads(INDEX.read_text());grouped={};flags={};scanned=0;errors=[]
 for tid,e in idx['trails'].items():
  page=e['pageUrl'];cp=CACHE/(sha256(page.encode()).hexdigest()+'.json')
  if not cp.exists():continue
  try:d=json.loads(cp.read_text());p=Parser(d.get('url') or page);p.feed(d.get('html',''))
  except (ValueError,OSError) as err:errors.append({'trailId':tid,'cacheFile':str(cp),'error':str(err)});continue
  scanned+=1;known={m['url'] for m in e.get('maps',[])}
  for a in p.anchors:
   kind=classify(a)
   if not kind or a['url'] in known:continue
   assoc={'trailId':tid,'name':e['name'],'sourcePage':page,'title':a['title'] or 'Trail map','section':a['section'],'cacheFile':str(cp),'indexStatus':e['status']}
   g=grouped.setdefault(a['url'],{'url':a['url'],'kind':kind,'host':urlsplit(a['url']).hostname,'associations':[]})
   if not any(x['trailId']==tid for x in g['associations']):g['associations'].append(assoc)
   if kind!='pdf' and e['status']=='no_pdf':flags.setdefault(tid,{'trailId':tid,'name':e['name'],'sourcePage':page,'status':e['status'],'attachments':[]})['attachments'].append({'title':a['title'],'url':a['url'],'kind':kind,'section':a['section']})
  for a in p.images:
   if a['url'] in known or EXCLUDE.search(a['title']+' '+a['url']):continue
   flags.setdefault(tid,{'trailId':tid,'name':e['name'],'sourcePage':page,'status':e['status'],'attachments':[]})['attachments'].append(a)
 meta={'generatedAt':datetime.now(timezone.utc).isoformat(),'offlineOnly':True,'cachedPagesAudited':scanned,'indexCheckedAt':idx.get('checkedAt'),'uniqueCandidateCount':len(grouped),'associationCount':sum(len(v['associations']) for v in grouped.values()),'readErrors':errors}
 OUT.write_text(json.dumps({**meta,'candidates':sorted(grouped.values(),key=lambda v:v['url'])},ensure_ascii=False,indent=2)+'\n')
 FLAGS.write_text(json.dumps({**meta,'flaggedTrailCount':len(flags),'trails':list(flags.values())},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({**meta,'nonPdfFlaggedTrails':len(flags)}))
 for a in grouped.values():print(a['kind'],len(a['associations']),a['url'])
 if flags:print('NO_PDF flags:',json.dumps(list(flags.values()),ensure_ascii=False))
if __name__=='__main__':main()
