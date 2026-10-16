"""Real HF Dataset + private backend + desktop/mobile UI. Test notes only."""
import argparse
import base64
import json
from pathlib import Path
import sys
import threading
import time
import urllib.error
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_cdp import Browser
import publisher
import portal
from hf_storage import Hub,Store,empty,Conflict
from publish_space import credential,site_payload
from space_server import make_server


def verify():
    run=publisher.new_run('private_verify');hub=Hub(credential())
    owner=hub.call('/api/whoami-v2')['name'];name='document-research-qa-'+uuid.uuid4().hex[:12];repo=owner+'/'+name
    created=False;server=None;browser=None
    result={}
    try:
        hub.call('/api/repos/create','POST',{'type':'dataset','name':name,'private':True});created=True
        a,b=Store(hub,repo),Store(hub,repo)
        a.save('test:paper',{**empty(),'notes':'手机笔记','rating':4},empty());b.pull()
        old=dict(b.items['test:paper'])
        a.save('test:paper',{**old,'rating':5},old)
        b.save('test:paper',{**old,'notes':'电脑合并笔记'},old)
        c=Store(hub,repo);c.pull()
        assert c.items['test:paper']['rating']==5 and c.items['test:paper']['notes']=='电脑合并笔记'
        try:c.save('test:paper',{**old,'notes':'过期修改'},old)
        except Conflict:result['conflict']=True
        else:raise AssertionError('Lost update')
        before=c.head;c.save('test:paper',c.items['test:paper'],c.items['test:paper']);assert c.head==before
        c.compact();d=Store(hub,repo);d.pull();assert d.items['test:paper']['rating']==5 and d.meta['history_bytes']==0
        try:Hub('').call('/api/datasets/'+repo)
        except urllib.error.HTTPError as e:assert e.code in (401,403,404)
        else:raise AssertionError('Anonymous private Dataset access')
        result.update(persistence=True,fieldMerge=True,noop=True,compaction=True,anonymousDatasetBlocked=True)
        print(json.dumps(result),flush=True)
        source=publisher.ROOT.parent/'EveryDayPaper';rows,_,_=portal.library_records(source)
        first,second=rows[:2];d.save(first['id'],{**empty(),'rating':4,'tags':['验证标签']},empty());d.save(second['id'],{**empty(),'rating':2},empty())
        api=publisher.GitHub('seven-7-ding/DocumentResearch');_,remote=api.snapshot('gh-pages')
        payload=site_payload(source,remote,api.read)
        for path,data in payload.items():
            target=run/'site'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        server=make_server(run/'site',Store(hub,repo),0,'127.0.0.1')
        url='http://127.0.0.1:'+str(server.server_port);server.origin=url
        threading.Thread(target=server.serve_forever,daemon=True).start()
        browser=Browser('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',run/'edge');browser.sock.settimeout(120)
        browser.capture(url,'desktop',1280,950)
        def js(code):return browser.evaluate(code)
        def until(condition):
            return js("(async()=>{let until=Date.now()+85000;while(!("+condition+")){if(Date.now()>until)throw Error('Timed out');await new Promise(r=>setTimeout(r,200));}return true;})()")
        until("document.querySelector('#sync-status').textContent.includes('已同步')&&document.querySelectorAll('.paper-card').length===12")
        assert js("!document.querySelector('#login')&&!document.querySelector('#account-dialog')")
        info=js("({total:document.querySelector('#total').textContent,reports:document.querySelectorAll('.report-card').length,width:innerWidth,scroll:document.documentElement.scrollWidth,pdf:document.querySelectorAll('.paper-actions a').length})")
        assert info['total'].startswith(str(len(rows))) and info['reports']==6 and info['width']>=info['scroll'],info
        # Every range boundary, and unscored values, against the actual exported predicate.
        checks=js("""(async()=>{const {matches}=await import('./app.js');const p={title:'x',authors:[],institutions:[]};return [
          matches(p,{rating_min:'3',rating_max:'5'},{tags:[],rating:3}),
          matches(p,{rating_min:'3',rating_max:'5'},{tags:[],rating:5}),
          !matches(p,{rating_min:'3',rating_max:'5'},{tags:[],rating:2}),
          !matches(p,{rating_min:'3',rating_max:'5'},{tags:[],rating:null}),
          matches(p,{unrated:'only'},{tags:[],rating:null}),
          !matches(p,{rating_min:'5',rating_max:'2'},{tags:[],rating:4}),
          matches({...p,published:'2025'},{published_from:'2025-06-01'}),
          matches({...p,published:'2024-02'},{published_from:'2024-02-29'}),
          !matches({...p,published:'2023-02'},{published_from:'2023-03-01'}),
          !matches(p,{published_from:'2025-01-01'})];})()""")
        assert all(checks)
        js("document.querySelector('[name=rating_min]').value='4';document.querySelector('[name=rating_max]').value='5';document.querySelector('#filters').dispatchEvent(new Event('input'))")
        assert js("document.querySelectorAll('.paper-card').length")==1
        js("document.querySelector('.edit-button').click();document.querySelector('#edit-notes').value='<img src=x onerror=alert(1)>跨设备验证';document.querySelector('#edit-rating').value='5';document.querySelector('#annotation-form').requestSubmit()")
        until("!document.querySelector('#editor').open")
        fresh=Store(hub,repo);fresh.pull();assert fresh.items[first['id']]['rating']==5 and '跨设备验证' in fresh.items[first['id']]['notes']
        assert js("!document.querySelector('.note-preview img')")
        # Inject a failed write; save must retain its draft instead of claiming success.
        js("window.originalFetch=window.fetch;window.fetch=(u,o)=>u==='/api/annotations'&&o?.method==='POST'?Promise.reject(Error('Synthetic offline')):window.originalFetch(u,o);document.querySelector('.edit-button').click();document.querySelector('#edit-notes').value='离线草稿';document.querySelector('#annotation-form').requestSubmit()")
        until("document.querySelector('#edit-status').textContent.includes('尚未同步')")
        assert js("Object.keys(JSON.parse(localStorage.getItem('document-research:pending:seven-7-ding/DocumentResearch'))).length")==1
        js("window.fetch=window.originalFetch;document.querySelector('#close-editor').click();window.dispatchEvent(new Event('online'))")
        until("document.querySelector('#sync-status').textContent.includes('已同步')")
        fresh.pull();assert fresh.items[first['id']]['notes']=='离线草稿'
        js("document.querySelector('#filters').reset()")
        browser.capture(url,'mobile',390,844)
        until("document.querySelectorAll('.paper-card').length===12")
        assert js('innerWidth>=document.documentElement.scrollWidth')
        result.update(ui=info,ratingRange=True,noSecondLogin=True,browserCloudSave=True,offlineRecovery=True,mobile=True)
        # A real historical reading: title and math must survive standalone rendering.
        reading=next(p for p in rows if p.get('reading_url','').startswith('readings/') and b'$$' in payload[p['reading_url']])
        browser.call('Page.navigate',{'url':url+'/'+reading['reading_url']})
        until("document.readyState==='complete'&&document.querySelector('main')")
        until("document.querySelector('mjx-container')")
        result['readingMath']=js("document.querySelectorAll('mjx-container').length")
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    finally:
        if browser:browser.close()
        if server:server.shutdown();server.server_close()
        if created:hub.call('/api/repos/delete','DELETE',{'type':'dataset','name':name})
        print('Private test Dataset removed; production notes untouched.',flush=True)


if __name__=='__main__':verify()
