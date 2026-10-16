"""Metadata privacy, stable sharding, and historical deep-read detection."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import portal
import publisher
RUN=publisher.new_run('portal_tests')

class PortalTests(unittest.TestCase):
    def test_placeholders_not_deep_reads(self):
        source=publisher.ROOT.parent/'EveryDayPaper'
        rows,reports,_=portal.library_records(source)
        self.assertEqual(len({p['id'] for p in rows}),len(rows))
        self.assertEqual(len(reports['2026-08-10']),20)
        self.assertEqual(sum(c['deep_read'] for c in reports['2026-08-10']),4)
        self.assertGreaterEqual(len(rows),132)
        self.assertTrue(all(p['pdf_url'].startswith('https://') for p in rows))
        self.assertTrue(any(p['added']<'2026-08-01' for p in rows))

    def test_public_allowlist_and_latest_version(self):
        source=RUN/'source';source.mkdir()
        index={'papers':[{'arxiv_id':'2601.12345','title':'Original','authors':['First','Last'],
          'deep_read':True,'date_published':'2026-01-01','date_added':'2026-01-03','topics':['RL'],
          'notes':'PRIVATE_NOTE','password':'PRIVATE_PASSWORD','recommended_by':'PRIVATE_EMAIL'}]}
        (source/'paper_index.json').write_text(json.dumps(index))
        (source/'library_metadata.json').write_text(json.dumps({'arxiv:2601.12345':{'date_updated':'2026-10-01','version':'v3','title':'Latest'}}))
        payload,_,_=portal.library_payload(source)
        public=b''.join(payload.values()).decode()
        self.assertNotIn('PRIVATE_',public)
        self.assertIn('2026-10-01',public)
        rows,_,_=portal.library_records(source)
        self.assertEqual(rows[0]['first_author'],'First');self.assertEqual(rows[0]['last_author'],'Last')
        self.assertEqual(rows[0]['notes'],'')
        second,_,_=portal.library_payload(source);self.assertEqual(payload,second)
        index['papers'].append({**index['papers'][0],'arxiv_id':'2601.99999'})
        (source/'paper_index.json').write_text(json.dumps(index))
        third,_,_=portal.library_payload(source)
        changed=[k for k,v in third.items() if payload.get(k)!=v]
        self.assertLessEqual(len(changed),2)

    def test_type_and_pdf(self):
        self.assertEqual(portal.paper_type({'title':'A Survey of RL'}),'综述')
        self.assertEqual(portal.paper_type({'title':'New research','comment':'arXiv preprint'}),'一般论文')
        self.assertEqual(portal.pdf_url({'url':'https://openreview.net/forum?id=abc'}),'https://openreview.net/pdf?id=abc')

if __name__=='__main__':unittest.main()
