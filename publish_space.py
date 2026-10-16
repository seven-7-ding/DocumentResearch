"""Publish private HF portal; public daily reports remain on GitHub Pages."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import publisher as p
import portal
from hf_storage import Hub

SPACE='seven-7-ding/DocumentResearch'
HOST='https://huggingface.co/spaces/'+SPACE
PAGES='https://seven-7-ding.github.io/DocumentResearch/'
README='''---
title: Document Research
emoji: 📚
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---
Private reading portal. Notes persist in a separate private Dataset.
Source: https://github.com/seven-7-ding/DocumentResearch
'''

def credential():
    token=os.environ.get('HF_TOKEN')
    if not token:
        r=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=huggingface.co\n\n',capture_output=True,text=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'})
        token=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line).get('password')
    if not token:
        path=Path.home()/'.cache/huggingface/token'
        if path.exists():token=path.read_text().strip()
    if not token:raise RuntimeError('HF credential unavailable')
    return token

def git(directory,*args):
    r=subprocess.run(['git','-C',str(directory),*args],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'})
    if r.returncode:raise RuntimeError('Git operation failed (exit '+str(r.returncode)+')')
    return r.stdout.strip()

def site_payload(source,remote,read):
    payload,_,_=portal.library_payload(source)
    payload.update({name:(p.ROOT/'web'/name).read_bytes() for name in ('index.html','app.js','style.css','sync.js')})
    for path in remote:
        if path.startswith('catalog/') and path.endswith('.json'):
            data=read(remote[path])
            if path!='catalog/months.json':
                rows=json.loads(data)
                for row in rows:row['url']=PAGES+row['url']
                data=p.encode(rows)
            payload[path]=data
    manifest=json.loads(payload['library/manifest.json'])
    for shard in manifest['shards']:
        rows=json.loads(payload.pop(shard['url']))
        for row in rows:
            if row.get('reading_url','').startswith('reports/'):row['reading_url']=PAGES+row['reading_url']
        data=p.encode(rows);name=shard['url'].split('-')[0]+'-'+hashlib.sha256(data).hexdigest()[:12]+'.json'
        payload[name]=data;shard.update(url=name,bytes=len(data))
    payload['library/manifest.json']=p.encode(manifest)
    return payload

def publish():
    run=p.new_run('space');hub=Hub(credential());info=hub.call('/api/spaces/'+SPACE)
    if info.get('private') is not True:
        hub.call('/api/spaces/'+SPACE+'/settings','PUT',{'private':True})
        if hub.call('/api/spaces/'+SPACE).get('private') is not True:raise RuntimeError('Private Space verification failed')
    config=json.loads((p.ROOT/'config.json').read_text(encoding='utf-8'))
    api=p.GitHub(config['repository']);_,remote=api.snapshot('gh-pages')
    payload={'site/'+name:data for name,data in site_payload((p.ROOT/config['source_dir']).resolve(),remote,api.read).items()}
    for name in ('Dockerfile','space_server.py','hf_storage.py'):payload[name]=(p.ROOT/name).read_bytes()
    payload['README.md']=README.encode('utf-8')
    # Compare deployed bytes, not Windows checkout line-ending conversions.
    checkout=run/'space';git(run,'clone','-c','core.autocrlf=false','--depth','1','https://huggingface.co/spaces/'+SPACE,str(checkout))
    previous=set()
    old_manifest=checkout/'site/library/manifest.json'
    history=checkout/'site/library/previous.json'
    if old_manifest.exists():
        if old_manifest.read_bytes()==payload['site/library/manifest.json'] and history.exists():
            previous=set(json.loads(history.read_bytes()))
        elif old_manifest.read_bytes()!=payload['site/library/manifest.json']:
            previous={'site/'+s['url'] for s in json.loads(old_manifest.read_bytes())['shards']}
    previous={path for path in previous if path.startswith('site/library/') and (checkout/path).is_file()}
    payload['site/library/previous.json']=p.encode(sorted(previous))
    total=sum(map(len,payload.values()))+sum((checkout/path).stat().st_size for path in previous if path not in payload and (checkout/path).is_file())
    if total>config['max_site_mb']*1024*1024 or any(len(data)>config['max_file_mb']*1024*1024 for data in payload.values()):raise ValueError('HF portal exceeds configured size budget')
    changed=sum(len(data) for path,data in payload.items() if not (checkout/path).is_file() or (checkout/path).read_bytes()!=data)
    if changed>config['max_upload_mb']*1024*1024:raise ValueError('HF upload exceeds configured size budget')
    for path in git(checkout,'ls-files').splitlines():
        if path not in payload and path not in previous and (path.startswith(('catalog/','library/','site/')) or path in ('index.html','app.js','style.css','sync.js','oauth-client.json')):git(checkout,'rm','--',path)
    for path,data in payload.items():
        target=checkout/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    git(checkout,'add','--',*sorted(payload))
    if git(checkout,'status','--porcelain'):
        git(checkout,'commit','-m','Publish private reading portal');git(checkout,'push','origin','HEAD:main')
    # Static Space secrets may reach browser JS. Install only after SDK verification.
    info=hub.call('/api/spaces/'+SPACE)
    if info.get('sdk')!='docker' or info.get('private') is not True:raise RuntimeError('Private Docker Space not active; secret not installed')
    repo=SPACE.split('/')[0]+'/document-research-notes'
    try:notes=hub.call('/api/datasets/'+repo)
    except urllib.error.HTTPError as e:
        if e.code!=404:raise
        hub.call('/api/repos/create','POST',{'type':'dataset','name':'document-research-notes','private':True});notes=hub.call('/api/datasets/'+repo)
    if notes.get('private') is not True:raise RuntimeError('Notes Dataset must be private')
    secrets=hub.call('/api/spaces/'+SPACE+'/secrets')
    if 'NOTES_HF_TOKEN' not in secrets:
        hub.call('/api/spaces/'+SPACE+'/secrets','POST',{'key':'NOTES_HF_TOKEN','value':hub.token})
    result={'space':SPACE,'url':HOST,'bytes':total,'upload_bytes':changed,'commit':git(checkout,'rev-parse','HEAD'),'stage':info.get('runtime',{}).get('stage')}
    p.trace('Private HF portal deployed: '+result['commit'])
    print(json.dumps(result,ensure_ascii=False,indent=2));return result

if __name__=='__main__':
    try:publish()
    except urllib.error.HTTPError as e:print('HF HTTP '+str(e.code),file=sys.stderr);sys.exit(1)
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
