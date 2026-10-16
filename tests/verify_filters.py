"""Browser regression checks; temporary fixtures only, no saved logs/screenshots."""
import base64
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_cdp import Browser
from test_private_portal import FakeHub
from hf_storage import Store,empty
from space_server import make_server
import portal
import publisher


def verify(preview=False):
    run=publisher.new_run('filter_ui')
    payload,reports,index=portal.library_payload(publisher.ROOT.parent/'EveryDayPaper')
    manifest=json.loads(payload['library/manifest.json'])
    rows=[p for shard in manifest['shards'] for p in json.loads(payload[shard['url']])]
    target=next(p for p in rows if p['title'].lower()=='loss of plasticity in deep continual learning')
    store=Store(FakeHub(),'local/filters')
    store.save(target['id'],{**empty(),'tags':['Continual Learning','Plasticity','重点','待复现'],'rating':5},empty())
    for name in ('index.html','app.js','style.css','sync.js'):payload[name]=(publisher.ROOT/'web'/name).read_bytes()
    cards=[{'date':day,'url':'#daily',**portal.report_summary(day,cards,index)} for day,cards in sorted(reports.items(),reverse=True)]
    months=sorted({r['date'][:7] for r in cards},reverse=True)
    payload['catalog/months.json']=publisher.encode(months)
    for month in months:payload['catalog/'+month+'.json']=publisher.encode([r for r in cards if r['date'].startswith(month)])
    for path,data in payload.items():
        output=run/'site'/path;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
    server=make_server(run/'site',store,0,'127.0.0.1');url='http://127.0.0.1:'+str(server.server_port);server.origin=url
    threading.Thread(target=server.serve_forever,daemon=True).start()
    browser=Browser('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',run/'edge')
    result={};shots=[]
    try:
        browser.call('Page.enable')
        browser.call('Page.addScriptToEvaluateOnNewDocument',{'source':"window.uiErrors=[];addEventListener('error',e=>uiErrors.push(e.message));addEventListener('unhandledrejection',e=>uiErrors.push(String(e.reason)));"})
        browser.capture(url,'desktop',1280,950)
        def js(code):return browser.evaluate(code)
        def until(condition):return js("(async()=>{const end=Date.now()+15000;while(!("+condition+")){if(Date.now()>end)throw Error('timeout');await new Promise(r=>setTimeout(r,100));}return true;})()")
        until("document.querySelector('#sync-status').textContent.includes('seven-7-ding')&&document.querySelectorAll('.paper-card').length===12")
        js('window.example='+json.dumps(target,ensure_ascii=False))
        checks=js("""(async()=>{const {matches,colorFor}=await import('./app.js');const p={title:'A [RL] <img>',authors:['Alice','Bob'],first_author:'Alice',last_author:'Bob',institutions:['Lab A','Lab B'],venue:'ICML',type:'一般论文',published:'2025',added:'2026-10-16'};const a={tags:['tag A','tag B'],rating:4};return [
          matches(p,{author:['Nobody','Alice'],institution:['Lab B','Other'],venue:['ICLR','ICML'],tag:['tag C','tag A']},a),
          !matches(p,{author:['Nobody'],institution:['Lab B']},a),
          !matches(p,{author:['Alice'],venue:['Nature']},a),
          matches(p,{first_author:['Alice','Other'],last_author:['Bob'],type:['一般论文','综述'],title:'[RL]',author_query:'lic'},a),
          !matches(p,{first_author:['Bob']},a),matches(p,{tag:[]},a),
          matches(p,{rating_min:'4',rating_max:'5',published_from:'2025-06-01'},a),
          colorFor('Plasticity')===colorFor('Plasticity'),colorFor('tag A')!==colorFor('tag B')];})()""")
        assert all(checks),checks
        # Real checkbox interaction, including searches and two selections per field.
        js("""window.choose=(name,values)=>{const select=document.querySelector('[name="'+name+'"]'),widget=select.nextElementSibling;document.querySelector('.filter-panel').open=true;widget.open=true;for(const value of values){const search=widget.querySelector('input[type=search]');search.value=value;search.dispatchEvent(new Event('input',{bubbles:true}));const box=[...widget.querySelectorAll('input[type=checkbox]')].find(e=>e.value===value);if(!box)throw Error('Missing option '+value);if(!box.checked)box.click();}widget.open=false;};
          choose('author',[example.authors[0],example.authors.at(-1)]);choose('institution',example.institutions);choose('venue',['Nature','ICML']);choose('tag',['Plasticity','Continual Learning']);
          const title=document.querySelector('[name=title]');title.value='plasticity';title.dispatchEvent(new Event('input',{bubbles:true}));""")
        assert js("document.querySelectorAll('.paper-card').length")==1
        assert js("new FormData(document.querySelector('#filters')).getAll('author').length")==2
        for selector in ('.paper-link','.authors','.institutions','.venue','.chips'):
            assert js('!!document.querySelector('+json.dumps(selector+' mark')+')'),selector
        assert js("document.querySelector('.authors').classList.contains('has-match')")
        assert js("new Set([...document.querySelectorAll('.paper-card .chip')].map(e=>getComputedStyle(e).backgroundColor)).size")>1
        assert js("[document.body,document.querySelector('input'),document.querySelector('button')].every(e=>getComputedStyle(e).fontFamily.startsWith('\"Times New Roman\"'))")
        result.update(multiOR_AND=True,checkboxes=True,highlights=True,stableColors=True,timesFont=True)
        # Special characters must be literal and never interpreted as HTML/regex.
        js("const q=document.querySelector('[name=title]');q.value='[<img.*';q.dispatchEvent(new Event('input',{bubbles:true}))")
        assert js("document.querySelectorAll('.paper-card').length")==0
        assert not js('window.uiErrors')
        js("document.querySelector('#filters').reset()")
        until("document.querySelectorAll('.paper-card').length===12")
        assert js("[...document.querySelectorAll('#filters select[multiple]')].every(s=>s.selectedOptions.length===0)")
        assert not js("document.querySelector('#papers mark')")
        # Highlight actual bracketed title characters, if one is present in this catalog.
        js("document.querySelector('[name=title]').value='plasticity';document.querySelector('#filters').dispatchEvent(new Event('input',{bubbles:true}))")
        js("choose('tag',['Plasticity','Continual Learning'])")
        for width,height in [(1280,950),(390,844)]:
            browser.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<600})
            js("document.documentElement.style.scrollBehavior='auto';document.querySelector('#papers').scrollIntoView({behavior:'instant'})")
            assert js('document.documentElement.scrollWidth<=innerWidth')
            assert js("[...document.querySelectorAll('.multi-select>summary')].every(e=>{const r=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();return r.width<=p.width+1})")
            if preview and width<600:shots.append(browser.call('Page.captureScreenshot',{'format':'jpeg','quality':35})['data'])
            js("(()=>{document.querySelector('.filter-panel').open=true;const d=document.querySelector('[name=venue]').nextElementSibling;d.open=true;d.scrollIntoView({behavior:'instant'})})()")
            assert js("(()=>{const r=document.querySelector('[name=venue]').nextElementSibling.querySelector('.multi-menu').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth})()")
            if preview and width<600:shots.append(browser.call('Page.captureScreenshot',{'format':'jpeg','quality':35})['data'])
            js("document.querySelector('[name=venue]').nextElementSibling.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
            assert not js("document.querySelector('[name=venue]').nextElementSibling.open")
        assert not js('window.uiErrors')
        result.update(reset=True,literalSearch=True,mobile=True,keyboard=True)
        return {'checks':result,'screenshots':shots}
    finally:
        browser.close();server.shutdown();server.server_close()


if __name__=='__main__':print(json.dumps(verify()['checks'],ensure_ascii=False,indent=2))
