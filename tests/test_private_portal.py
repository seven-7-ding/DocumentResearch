"""Private API boundaries, optimistic concurrency, and publication isolation."""
import copy
import io
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hf_storage as s
import publisher
import portal
from space_server import make_server


class FakeHub:
    def __init__(self):
        self.private=True;self.head='0';self.files={};self.commits=0;self.race=False
    def call(self,path,method='GET',body=None,raw=False):
        if path.startswith('/api/spaces/'):
            return {'private':self.private,'sdk':'docker'}
        if '/commit/' in path:
            lines=[json.loads(line) for line in body.splitlines()]
            if self.race:
                self.race=False;self.head=str(int(self.head)+1)
                raise urllib.error.HTTPError('',409,'conflict',{},io.BytesIO())
            if lines[0]['value'].get('parentCommit')!=self.head:
                raise urllib.error.HTTPError('',409,'conflict',{},io.BytesIO())
            for line in lines[1:]:
                f=line['value'];self.files[f['path']]=json.loads(s.base64.b64decode(f['content']))
            self.commits+=1;self.head=str(int(self.head)+1);return {}
        if '/resolve/' in path:
            name=path.split('/resolve/')[1].split('/',1)[1]
            if name not in self.files:raise urllib.error.HTTPError('',404,'missing',{},io.BytesIO())
            return copy.deepcopy(self.files[name])
        return {'private':self.private,'sha':self.head}


class PrivateTests(unittest.TestCase):
    def test_merge_retry_noop_and_reconnect(self):
        hub=FakeHub();a=s.Store(hub,'owner/test');b=s.Store(hub,'owner/test')
        base=s.empty();value={**base,'notes':'手机笔记','rating':4}
        hub.race=True;a.save('arxiv:test',value,base)
        b.pull();base=b.items['arxiv:test'].copy()
        a.save('arxiv:test',{**base,'rating':5},base)
        b.save('arxiv:test',{**base,'notes':'电脑笔记'},base)
        c=s.Store(hub,'owner/test');c.pull()
        self.assertEqual(c.items['arxiv:test']['rating'],5)
        self.assertEqual(c.items['arxiv:test']['notes'],'电脑笔记')
        with self.assertRaises(s.Conflict):a.save('arxiv:test',{**base,'notes':'过期修改'},base)
        n=hub.commits;c.save('arxiv:test',c.items['arxiv:test'],c.items['arxiv:test'])
        self.assertEqual(n,hub.commits)
        self.assertEqual(len(c.meta['buckets']),1)

    def test_private_gate_and_origin(self):
        run=publisher.new_run('api_tests');(run/'index.html').write_text('private portal');(run/'secret.txt').write_text('NEVER_SERVE')
        hub=FakeHub();server=make_server(run,s.Store(hub,'owner/test'),0,'127.0.0.1')
        root='http://127.0.0.1:'+str(server.server_port);server.origin=root
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def call(path,method='GET',body=None,headers=None):
            req=urllib.request.Request(root+path,method=method,data=s.encode(body) if body else None,headers=headers or {})
            try:
                with urllib.request.urlopen(req) as r:return r.status,r.read()
            except urllib.error.HTTPError as e:return e.code,e.read()
        try:
            self.assertEqual(call('/')[0],200)
            self.assertEqual(call('/secret.txt')[0],404)
            self.assertEqual(call('/hf_storage.py')[0],404)
            self.assertEqual(call('/secret.txt','HEAD')[0],405)
            body={'id':'x','value':s.empty(),'base':s.empty()}
            self.assertEqual(call('/api/annotations','POST',body,{'Origin':'https://evil.example','Content-Type':'application/json','X-DocumentResearch':'1'})[0],403)
            self.assertEqual(call('/api/annotations','POST',body,{'Content-Type':'application/json'})[0],403)
            self.assertEqual(call('/api/annotations','POST',body,{'Content-Type':'application/json','X-DocumentResearch':'1','Origin':root})[0],200)
            hub.private=False;server.private_until=0
            self.assertNotEqual(call('/')[0],200)
            self.assertNotEqual(call('/api/annotations')[0],200)
        finally:server.shutdown();server.server_close()

    def test_venues_and_affiliations(self):
        for raw in ['ICML 2026','ICML 2026 (Oral presentation)','The International Conference on Machine Learning (ICML) 2026']:
            self.assertEqual(portal.venue({'venue':raw}),'ICML')
        self.assertEqual(portal.venue({'venue':'ICML 2026 Workshop RLxF'}),'ICML Workshop')
        self.assertEqual(portal.clean_institutions(['未披露','Institution not listed on arXiv abstract page','MIT；Google DeepMind','Massachusetts Institute of Technology']),['MIT','Google DeepMind'])

    def test_reading_is_not_invented_and_math_preserved(self):
        from reading_reports import render
        body='# Test\n\n$$V_t=\\sum_i x_i$$\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))'
        page,_=render(body,Path('test.md'),'Test','https://arxiv.org/pdf/1')
        self.assertIn(b'$$V_t=\\sum_i x_i$$',page)
        self.assertNotIn(b'<script>alert',page)
        self.assertNotIn(b'href="javascript:',page)
        source=publisher.ROOT.parent/'EveryDayPaper'
        from reading_reports import find_readings
        self.assertEqual(find_readings(source,[{'title':'Wasserstein Policy Optimization','arxiv_id':'2505.00663'}]),{})


if __name__=='__main__':unittest.main()
