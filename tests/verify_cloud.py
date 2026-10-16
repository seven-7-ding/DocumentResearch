"""Opt-in live HF storage contract test using a newly created private scratch Dataset.

Credentials never print. The scratch repo contains only synthetic test data and is
removed in finally. Does not create the app's production notes repository.
"""
import base64
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import publisher
from browser_cdp import Browser

def credential():
    token=os.environ.get('HF_TOKEN')
    if not token:
        r=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=huggingface.co\n\n',capture_output=True,text=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'})
        token=dict(l.split('=',1) for l in r.stdout.splitlines() if '=' in l).get('password')
    if not token:
        path=Path.home()/'.cache/huggingface/token'
        if path.exists():token=path.read_text().strip()
    if not token:raise RuntimeError('HF credential unavailable')
    return token

def verify():
    run=publisher.new_run('cloud_verify');token=credential()
    def api(path,method='GET',body=None,authorized=True):
        request=urllib.request.Request('https://huggingface.co'+path,method=method,
          headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if authorized else {})},
          data=publisher.encode(body) if body is not None else None)
        try:
            with urllib.request.urlopen(request,timeout=30,context=ssl.create_default_context(cafile=ssl.get_default_verify_paths().cafile)) as response:
                data=response.read()
                return json.loads(data) if data and response.headers.get('Content-Type','').startswith('application/json') else {}
        except urllib.error.HTTPError as e:raise RuntimeError('HF API HTTP '+str(e.code)) from None
    owner=api('/api/whoami-v2')['name'];name='document-research-qa-'+uuid.uuid4().hex[:12];repo=owner+'/'+name
    browser=None;created=False
    try:
        api('/api/repos/create','POST',{'type':'dataset','name':name,'private':True});created=True
        info=api('/api/datasets/'+repo);assert info['private']
        browser=Browser('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',run/'edge')
        browser.capture('https://seven-7-ding.github.io/DocumentResearch/','live',1100,850)
        # Never return auth or script to output. Two independent stores model two devices.
        expression='''(async()=>{
          const {CloudStore,emptyAnnotation,Conflict}=await import('./sync.js');
          const auth=AUTH,repo=REPO; const a=new CloudStore(auth),b=new CloudStore(auth);a.repo=repo;b.repo=repo;
          await a.connect();await b.connect();
          const empty=emptyAnnotation();
          await a.save('test:paper',{...empty,notes:'手机端测试笔记',tags:['测试'],rating:4},empty);
          await b.pull();if(b.items['test:paper'].notes!=='手机端测试笔记')throw new Error('Cross-device read failed');
          const base=structuredClone(b.items['test:paper']);
          await a.save('test:paper',{...base,rating:5},base);
          await b.save('test:paper',{...base,notes:'电脑端合并笔记'},base);
          await a.pull();if(a.items['test:paper'].rating!==5||a.items['test:paper'].notes!=='电脑端合并笔记')throw new Error('Independent field merge failed');
          let conflict=false;try{await a.save('test:paper',{...base,notes:'过期修改'},base);}catch(e){conflict=e instanceof Conflict;}
          if(!conflict)throw new Error('Conflict was not detected');
          const c=new CloudStore(auth);c.repo=repo;await c.connect();
          const before=c.head;await c.save('test:paper',c.items['test:paper'],c.items['test:paper']);
          if(c.head!==before)throw new Error('Identical save created a commit');
          await c.compact();const d=new CloudStore(auth);d.repo=repo;await d.connect();
          if(d.items['test:paper'].notes!=='电脑端合并笔记'||d.meta.history_bytes!==0)throw new Error('Compaction lost latest notes');
          return {privateRepo:true,crossDevice:true,mergedRating:d.items['test:paper'].rating,persistentNotes:d.items['test:paper'].notes,conflictDetected:conflict,noop:true,compactionPreservesNotes:true,shards:d.meta.buckets.length};
        })()'''.replace('AUTH',json.dumps({'token':token,'user':owner,'sub':owner})).replace('REPO',json.dumps(repo))
        # Cloud requests may exceed the transport's normal 25 second read timeout.
        browser.sock.settimeout(120)
        result=browser.evaluate(expression)
        try:api('/api/datasets/'+repo,authorized=False);raise AssertionError('Private data was publicly readable')
        except RuntimeError:result['anonymousBlocked']=True
        (run/'result.json').write_bytes(publisher.encode(result));print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        if browser:browser.close()
        if created:api('/api/repos/delete','DELETE',{'type':'dataset','name':name})
        print('Private scratch dataset removed' if created else 'No scratch dataset created')

if __name__=='__main__':verify()
