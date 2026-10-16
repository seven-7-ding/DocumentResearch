"""Refresh public paper metadata from arXiv/OpenReview; use conda bit, no installs."""
import argparse
import datetime as dt
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
import portal
import publisher

def fetch(url):
    context=ssl.create_default_context(cafile=ssl.get_default_verify_paths().cafile)
    req=urllib.request.Request(url,headers={'User-Agent':'DocumentResearch/1.0 (personal research library)'})
    with urllib.request.urlopen(req,timeout=45,context=context) as r:return r.read()

def refresh(source,run):
    papers,_,_=portal.source_papers(source)
    cache_path=source/'library_metadata.json'
    cache=json.loads(cache_path.read_text(encoding='utf-8-sig')) if cache_path.exists() else {}
    today=dt.date.today().isoformat();ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}
    keys={}
    for p in papers:
        key=portal.identity(p)
        if cache.get(key,{}).get('checked_at')==today:continue
        ident=key.split(':',1)[1] if key.startswith('arxiv:') else cache.get(key,{}).get('canonical_arxiv_id')
        if ident:keys[ident]=key
    ids=list(keys)
    errors=[];refreshed=0
    for start in range(0,len(ids),20):
        batch=ids[start:start+20]
        url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'id_list':','.join(batch),'max_results':len(batch)})
        try:
            data=fetch(url);(run/f'arxiv-{start}.xml').write_bytes(data)
            for entry in ET.fromstring(data).findall('a:entry',ns):
                get=lambda k:' '.join(entry.findtext(k,'',ns).split())
                identifier=portal.ARXIV.search(get('a:id'))
                if not identifier:continue
                key=keys[identifier.group(1)]; old=cache.get(key,{})
                authors=[a.findtext('a:name','',ns) for a in entry.findall('a:author',ns)]
                institutions=[v.text for v in entry.findall('a:author/x:affiliation',ns) if v.text]
                version=re.search(r'v\d+$',get('a:id'))
                value={**old,'title':get('a:title'),'authors':authors,'date_published':get('a:published')[:10],
                       'date_updated':get('a:updated')[:10],'journal_ref':get('x:journal_ref'),'comment':get('x:comment'),
                       'url':'https://arxiv.org/abs/'+identifier.group(1),'version':version[0] if version else '',
                       'checked_at':today,'metadata_source':url}
                if institutions:value['institutions']=institutions
                cache[key]=value;refreshed+=1
        except Exception as e:errors.append({'ids':batch,'error':str(e)})
        print(json.dumps({'arxiv_checked':min(start+20,len(ids)),'refreshed':refreshed,'errors':len(errors)}),flush=True)
        if start+20<len(ids):time.sleep(3.2)
    for p in papers:
        key=portal.identity(p)
        if not key.startswith('openreview:'):continue
        if cache.get(key,{}).get('canonical_arxiv_id') or cache.get(key,{}).get('last_attempt')==today:continue
        ident=key.split(':',1)[1]
        try:
            url='https://api2.openreview.net/notes?id='+urllib.parse.quote(ident)
            data=fetch(url);(run/(ident+'.json')).write_bytes(data);notes=json.loads(data)['notes']
            if not notes:raise ValueError('No public note returned')
            note=notes[0];content=note['content']
            def field(k,default=''):
                v=content.get(k,default);return v.get('value',default) if isinstance(v,dict) else v
            modified=note.get('mdate') or note.get('tmdate') or note.get('pdate') or note.get('cdate')
            value={**cache.get(key,{}),'title':field('title',p['title']),'authors':field('authors',p.get('authors',[])),
                   'url':'https://openreview.net/forum?id='+ident,'checked_at':today,'metadata_source':url}
            if modified:value['date_updated']=dt.datetime.fromtimestamp(modified/1000,dt.timezone.utc).date().isoformat()
            if field('venue'):value['venue']=field('venue')
            cache[key]=value;refreshed+=1
        except Exception as e:errors.append({'id':key,'error':str(e)})
        cache.setdefault(key,{})['last_attempt']=today
    cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'refreshed':refreshed,'total':len(papers),'errors':errors}
    (run/'metadata_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=publisher.ROOT/'config.json');args=parser.parse_args()
    config=json.loads(args.config.read_text(encoding='utf-8-sig'));run=publisher.new_run('metadata')
    refresh((args.config.resolve().parent/config['source_dir']).resolve(),run)
