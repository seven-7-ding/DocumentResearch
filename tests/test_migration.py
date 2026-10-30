import json
from pathlib import Path
import tempfile
import unittest
import publish_space as space

class MigrationTest(unittest.TestCase):
    def test_preserves_old_readings_and_merges_new_allowlisted_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib=root/'site/library';lib.mkdir(parents=True)
            reading=root/'site/readings/paper.html';reading.parent.mkdir();reading.write_text('historical reading')
            (reading.parent/'private.json').write_text('must not copy')
            old=[{'id':'openreview:old','url':'https://arxiv.org/abs/2601.12345','title':'old','reading_url':'readings/paper.html','notes':'private','tags':['private'],'authors':['A']}, {'id':'arxiv:2','title':'only remote'}]
            (lib/'a-old.json').write_text(json.dumps(old));(lib/'manifest.json').write_text(json.dumps({'shards':[{'url':'library/a-old.json'}]}))
            new=[{'id':'arxiv:2601.12345','url':'https://arxiv.org/abs/2601.12345','title':'updated','authors':[]}, {'id':'arxiv:3','title':'new'}]
            payload={'site/library/manifest.json':json.dumps({'shards':[{'url':'library/b-new.json'}]}).encode(),'site/library/b-new.json':json.dumps(new).encode()}
            result=space.preserve_deployed_library(payload,root)
            manifest=json.loads(result['site/library/manifest.json']);rows={row['id']:row for s in manifest['shards'] for row in json.loads(result['site/'+s['url']])}
            self.assertEqual(manifest['count'],3)
            self.assertEqual(rows['openreview:old']['title'],'updated');self.assertEqual(rows['openreview:old']['authors'],['A'])
            self.assertEqual(rows['openreview:old']['reading_url'],'readings/paper.html')
            self.assertEqual(rows['openreview:old']['notes'],'');self.assertEqual(rows['openreview:old']['tags'],[])
            self.assertNotIn('arxiv:2601.12345',rows)
            self.assertEqual(result['site/readings/paper.html'],b'historical reading')
            self.assertNotIn('site/readings/private.json',result)
            self.assertEqual(space.preserve_deployed_library(dict(result),root),result)

if __name__=='__main__':unittest.main()
