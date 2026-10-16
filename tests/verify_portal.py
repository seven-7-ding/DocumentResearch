"""Real Edge interaction checks, including bounded rendering and cloud merge contract."""
import argparse
import base64
import functools
import http.server
import json
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import publisher
from browser_cdp import Browser

def verify(site,url=None):
    run=publisher.new_run('portal_browser')
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    browser=Browser('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',run/'edge')
    base=url or f'http://127.0.0.1:{server.server_port}/'
    try:
        result={'desktop':browser.capture(base,'desktop',1440,1100)}
        deadline=time.monotonic()+25
        while browser.evaluate("document.querySelectorAll('.paper-card').length")!=12:
            if time.monotonic()>deadline:raise RuntimeError(browser.evaluate('document.body.innerText'))
            time.sleep(.2)
        result['library']=browser.evaluate("({total:document.querySelector('#total').textContent,reports:document.querySelectorAll('.report-card').length,papers:document.querySelectorAll('.paper-card').length,pdf:[...document.querySelectorAll('.paper-link')].every(a=>/arxiv.org\\/pdf|openreview.net\\/pdf|\\.pdf/.test(a.href))})")
        assert result['library']['reports']==6 and result['library']['pdf']
        result['search']=browser.evaluate("""(async()=>{const input=document.querySelector('[name=title]');input.value='Plasticity';input.dispatchEvent(new Event('input',{bubbles:true}));return {count:document.querySelectorAll('.paper-card').length,titles:[...document.querySelectorAll('.paper-card h3')].map(x=>x.textContent)};})()""")
        assert result['search']['count']>0 and all('plasticity' in t.lower() for t in result['search']['titles'])
        browser.evaluate("document.querySelector('#filters').reset()")
        browser.evaluate("document.querySelector('#next').click()")
        assert browser.evaluate("document.querySelector('#page-label').textContent.startsWith('2 /') && document.querySelectorAll('.paper-card').length===12")
        result['filters']=browser.evaluate("""(async()=>{const {matches}=await import('./app.js');const p={title:'Continual RL',title_zh:'持续学习',authors:['Alice Doe','Bob Lee'],first_author:'Alice Doe',last_author:'Bob Lee',institutions:['Example Lab'],venue:'ICLR',type:'一般论文',published:'2026-05-02',added:'2026-06-01'};const checks=[matches(p,{title:'continual',author:'DOE',first_author:'Alice Doe',last_author:'Bob Lee',institution:'Example Lab',venue:'ICLR',published_from:'2026-05-01',published_to:'2026-05-31',added_from:'2026-06-01',added_to:'2026-06-01',tag:'复现'},{tags:['复现']}),!matches(p,{last_author:'Alice Doe'}),!matches(p,{published_to:'2026-05-01'}),!matches(p,{added_from:'2026-06-02'}),!matches(p,{tag:'不存在'})];return checks;})()""")
        assert all(result['filters'])
        result['merge']=browser.evaluate("""(async()=>{const {mergeAnnotation,emptyAnnotation,Conflict,validate}=await import('./sync.js');const base=emptyAnnotation();const merged=mergeAnnotation(base,{...base,notes:'手机笔记'},{...base,rating:5});let conflict=false,invalid=false;try{mergeAnnotation(base,{...base,notes:'手机'},{...base,notes:'电脑'});}catch(e){conflict=e instanceof Conflict;}try{validate({...base,rating:6});}catch{invalid=true;}return {merged,conflict,invalid};})()""")
        assert result['merge']['merged']['notes']=='手机笔记' and result['merge']['merged']['rating']==5 and result['merge']['conflict'] and result['merge']['invalid']
        browser.evaluate("document.querySelector('.edit-button').click()")
        assert browser.evaluate("document.querySelector('#account-dialog').open")
        browser.evaluate("document.querySelector('#account-dialog').close()")
        result['mobile']=browser.capture(base,'mobile',390,844)
        deadline=time.monotonic()+25
        while browser.evaluate("document.querySelectorAll('.paper-card').length")!=12:
            if time.monotonic()>deadline:raise RuntimeError('Mobile library did not load')
            time.sleep(.2)
        assert result['mobile']['width']==result['mobile']['scrollWidth']
        browser.evaluate("document.querySelector('.filter-panel').open=true")
        assert browser.evaluate('document.documentElement.scrollWidth===innerWidth')
        browser.evaluate("document.querySelector('#library').scrollIntoView({behavior:'instant'})")
        (run/'edge'/'mobile-library.png').write_bytes(base64.b64decode(browser.call('Page.captureScreenshot',{'format':'png'})['data']))
        # Exercise actual editor, failed save, persisted draft, retry and safe rendering.
        browser.call('Page.addScriptToEvaluateOnNewDocument',{'source':(Path(__file__).parent/'mock_hf.js').read_text(encoding='utf-8')})
        browser.call('Page.reload')
        def wait_for(expression):
            deadline=time.monotonic()+25
            while not browser.evaluate(expression):
                if time.monotonic()>deadline:raise RuntimeError('UI wait failed: '+expression)
                time.sleep(.15)
        wait_for("document.querySelectorAll('.paper-card').length===12 && document.querySelector('#sync-status').textContent.includes('已同步')")
        browser.evaluate("document.querySelector('.edit-button').click();document.querySelector('#edit-tags').value='复现，长期';document.querySelector('#edit-rating').value='5';document.querySelector('#edit-notes').value='<img src=x onerror=alert(1)> 手机笔记';window.__testOffline=true;document.querySelector('#annotation-form').requestSubmit()")
        wait_for("document.querySelector('#edit-status').textContent.includes('尚未同步')")
        assert browser.evaluate("JSON.parse(localStorage.getItem('document-research:pending:portal-qa')) && document.querySelector('.note-preview').textContent.includes('<img') && document.querySelector('.note-preview img')===null")
        browser.call('Page.reload')
        wait_for("document.querySelector('#sync-status').textContent.includes('已同步') && document.querySelector('.note-preview')!==null")
        result['editor'] = browser.evaluate("({notes:document.querySelector('.note-preview').textContent,rating:document.querySelector('.stars').textContent,pending:Object.keys(JSON.parse(localStorage.getItem('document-research:pending:portal-qa'))).length,tags:[...document.querySelectorAll('.chip.user')].map(x=>x.textContent)})")
        assert result['editor']['pending']==0 and result['editor']['rating']=='★★★★★' and '长期' in result['editor']['tags']
        (run/'result.json').write_bytes(publisher.encode(result));print(json.dumps(result,ensure_ascii=False,indent=2));print('Evidence:',run)
    finally:browser.close();server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--site',required=True,type=Path);parser.add_argument('--url');args=parser.parse_args();verify(args.site.resolve(),args.url)
