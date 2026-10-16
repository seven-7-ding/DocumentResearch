"""Behavioral checks with isolated fixtures; no third-party test dependency."""
import functools
import http.server
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publisher as p

RUN = p.new_run('tests')


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.source = RUN / self._testMethodName
        self.source.mkdir()
        self.file = self.source / '2026-10-15.html'
        self.config = {'max_file_mb': 1, 'max_site_mb': 10, 'max_upload_mb': 10}

    def write(self, text):
        self.file.write_text(text, encoding='utf-8')

    def test_references_and_privacy(self):
        (self.source / 'temp').mkdir()
        (self.source / 'temp' / 'figure.png').write_bytes(b'png-content')
        (self.source / '.env').write_text('GITHUB_TOKEN=private', encoding='utf-8')
        self.write('<title>中文日报</title><img src="temp/figure.png"><a href="#paper">go</a><a href="temp/2608.17163.pdf">paper</a>')
        payload, item = p.build_report(self.file, 1024)
        self.assertEqual(item['title'], '中文日报')
        self.assertEqual(len(payload), 3)
        result = payload['reports/2026-10-15/index.html'].decode()
        self.assertIn('https://arxiv.org/pdf/2608.17163', result)
        self.assertIn('src="assets/', result)
        self.assertIn('href="#paper"', result)
        self.assertNotIn('private', result)

    def test_missing_image_is_explicit(self):
        self.write('<img src="temp/missing.png">')
        with self.assertRaisesRegex(ValueError, 'missing image'):
            p.build_report(self.file, 1024)
        payload, item = p.build_report(self.file, 1024, True)
        self.assertEqual(item['missing_images'], 1)
        self.assertIn('原文件已清理', next(iter(payload.values())).decode())
        self.assertNotIn('src=', next(iter(payload.values())).decode())

    def test_cloud_images_survive_local_temp_cleanup(self):
        image = self.source / 'figure.png'
        image.write_bytes(b'existing cloud image')
        self.write('<title>saved</title><img src="figure.png">')
        first, _, _ = p.plan([self.file], self.config, {}, None)
        remote = {path: {'sha': p.sha(data), 'size': len(data), 'data': data} for path, data in first.items()}
        image.unlink()
        _, deleted, summary = p.plan([self.file], self.config, remote, lambda item: item['data'])
        self.assertEqual(summary['changed_files'], 0)
        self.assertEqual(deleted, set())
        self.write('<title>deep read updated</title><img src="figure.png">')
        _, deleted, summary = p.plan([self.file], self.config, remote, lambda item: item['data'])
        self.assertEqual(summary['changed_files'], 2)
        self.assertEqual(deleted, set())

    def test_traversal_and_secret_blocked(self):
        for url in ['../secret.png', '.env', '/etc/passwd', 'file:///C:/secret.png']:
            with self.subTest(url=url):
                self.write('<img src="' + url + '">')
                with self.assertRaises(ValueError):
                    p.build_report(self.file, 1024)

    def test_idempotent_update_and_asset_cleanup(self):
        self.write('<title>first</title>')
        first, _, _ = p.plan([self.file], self.config, {}, None)
        remote = {path: {'sha': p.sha(data), 'size': len(data), 'data': data} for path, data in first.items()}
        read = lambda item: item['data']
        _, _, summary = p.plan([self.file], self.config, remote, read)
        self.assertEqual(summary['upload_bytes'], 0)
        self.assertEqual(summary['changed_files'], 0)
        remote['reports/2026-10-15/assets/old.png'] = {'sha': 'old', 'size': 30}
        remote['reports/2026-10-14/index.html'] = {'sha': 'keep', 'size': 30}
        self.write('<title>updated</title>')
        payload, deleted, summary = p.plan([self.file], self.config, remote, read)
        self.assertEqual(deleted, {'reports/2026-10-15/assets/old.png'})
        self.assertNotIn('reports/2026-10-14/index.html', deleted)
        self.assertEqual(summary['changed_files'], 2)

    def test_capacity_guard(self):
        self.write('<title>bounded</title>')
        self.config['max_upload_mb'] = 0
        with self.assertRaisesRegex(ValueError, 'Upload exceeds'):
            p.plan([self.file], self.config, {}, None)

    def test_month_bounded_and_http_readable(self):
        for day in range(1, 29):
            (self.source / f'2026-02-{day:02}.html').write_text('<title>February</title>', encoding='utf-8')
        self.write('<title>October</title>')
        payload, _, _ = p.plan(sorted(self.source.glob('*.html')), self.config, {}, None)
        self.assertEqual(len(json.loads(payload['catalog/2026-02.json'])), 28)
        self.assertEqual(len(json.loads(payload['catalog/2026-10.json'])), 1)
        site = self.source / 'site'
        for name, data in payload.items():
            target = site / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args): pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(site)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}/'
            for path in ['index.html', 'app.js', 'style.css', 'catalog/months.json', 'reports/2026-10-15/']:
                with urllib.request.urlopen(base + path) as response:
                    self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_remote_noop_has_no_mutations(self):
        api = object.__new__(p.GitHub)
        api.api = lambda *args, **kwargs: self.fail('No network needed for noop')
        result = api.publish('gh-pages', 'head', {'a': {'sha': p.sha(b'unchanged')}}, {'a': b'unchanged'}, set())
        self.assertEqual(result['uploaded_bytes'], 0)

    def test_temporary_workspaces_are_removed_without_logdir(self):
        existed=(p.ROOT/'logdir').exists()
        code="import publisher; p=publisher.new_run('cleanup'); (p/'fixture.txt').write_text('test input'); print(p)"
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=p.ROOT,capture_output=True,text=True,check=True)
        scratch=Path(result.stdout.strip())
        self.assertFalse(scratch.is_relative_to(p.ROOT))
        self.assertFalse(scratch.exists())
        self.assertEqual((p.ROOT/'logdir').exists(),existed)

    def test_private_portal_leaves_only_public_reports_and_redirect(self):
        self.write('<title>public daily report</title>')
        first, _, _ = p.plan([self.file], self.config, {}, None)
        remote = {path: {'sha': p.sha(data), 'size': len(data), 'data': data} for path, data in first.items()}
        remote['readings/private.html']={'sha':'old','size':30}
        self.config['private_portal']=True
        payload, deleted, _=p.plan([self.file],self.config,remote,lambda item:item['data'])
        self.assertTrue(all(path.startswith(('reports/','catalog/')) or path in {'index.html','.nojekyll'} for path in payload))
        self.assertIn(b'https://huggingface.co/spaces/seven-7-ding/DocumentResearch',payload['index.html'])
        self.assertIn('readings/private.html',deleted)
        self.assertIn('library/manifest.json',deleted)
        self.assertEqual(payload['reports/2026-10-15/index.html'],first['reports/2026-10-15/index.html'])
        final={path:item for path,item in remote.items() if path not in deleted}
        final.update({path:{'sha':p.sha(data),'size':len(data),'data':data} for path,data in payload.items()})
        _,deleted,summary=p.plan([self.file],self.config,final,lambda item:item['data'])
        self.assertFalse(deleted)
        self.assertEqual(summary['upload_bytes'],0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
