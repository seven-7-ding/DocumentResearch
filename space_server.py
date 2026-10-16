"""Same-origin private portal. HF access control is the sole login boundary."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
from hf_storage import Hub, Store, Conflict, encode

SPACE = 'seven-7-ding/DocumentResearch'
ORIGIN = 'https://seven-7-ding-documentresearch.hf.space'


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log annotation contents, request credentials, or private titles.

    def reply(self, value, status=200):
        data = encode(value)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def private_gate(self):
        # Fail closed if someone changes this Space to public. Short cache bounds
        # API traffic and expires even after a later upstream outage.
        if time.monotonic() >= getattr(self.server, 'private_until', 0):
            info = self.server.store.hub.call('/api/spaces/' + SPACE)
            if info.get('private') is not True or info.get('sdk') != 'docker':
                raise ValueError('门户必须运行在私有 Docker Space，已停止访问。')
            self.server.private_until = time.monotonic() + 10

    def do_GET(self):
        try:
            self.private_gate()
            path = urllib.parse.urlsplit(self.path).path
            if path == '/api/session':
                return self.reply({'user': SPACE.split('/')[0], 'sub': SPACE})
            if path == '/api/annotations':
                return self.reply(self.server.store.pull())
            decoded = urllib.parse.unquote(path)
            # Only site assets can be served, never server source or credentials.
            if '..' in decoded.split('/') or '\\' in decoded or not (
                decoded in ('/', '/index.html', '/app.js', '/style.css', '/sync.js') or
                decoded.startswith(('/catalog/', '/library/', '/readings/'))):
                return self.reply({'error': 'Not found'}, 404)
            target = Path(self.translate_path(path))
            if not target.is_file() and path != '/':
                return self.reply({'error': 'Not found'}, 404)
            return super().do_GET()
        except Exception as e:
            return self.error(e)

    def do_HEAD(self):
        # Avoid inherited HEAD bypassing the GET allowlist and privacy check.
        self.reply({'error': 'Method not allowed'}, 405)

    def do_POST(self):
        try:
            self.private_gate()
            origin = self.headers.get('Origin')
            if (origin and origin != self.server.origin or
                self.headers.get('Sec-Fetch-Site') == 'cross-site' or
                self.headers.get('X-DocumentResearch') != '1' or
                self.headers.get_content_type() != 'application/json'):
                return self.reply({'error': 'Invalid request origin'}, 403)
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 150_000:
                return self.reply({'error': 'Invalid request size'}, 413)
            body = json.loads(self.rfile.read(size))
            if self.path == '/api/annotations':
                return self.reply(self.server.store.save(body['id'], body['value'], body['base']))
            if self.path == '/api/compact' and body.get('confirm') is True:
                return self.reply(self.server.store.compact())
            return self.reply({'error': 'Not found'}, 404)
        except Exception as e:
            return self.error(e)

    def error(self, error):
        if isinstance(error, Conflict):
            return self.reply({'error': '笔记冲突，请合并后保存。', 'remote': error.remote}, 409)
        if isinstance(error, (ValueError, KeyError, TypeError)):
            return self.reply({'error': str(error) if isinstance(error, ValueError) else '无效请求'}, 400)
        return self.reply({'error': '云端暂时无法连接，草稿仍保存在本机，请稍后重试。'}, 503)


def make_server(root, store, port=7860, host='0.0.0.0', origin=ORIGIN):
    server = ThreadingHTTPServer((host, port), partial(Handler, directory=str(root)))
    server.store, server.origin = store, origin
    return server


if __name__ == '__main__':
    hub = Hub(os.environ['NOTES_HF_TOKEN'])
    store = Store(hub, SPACE.split('/')[0] + '/document-research-notes')
    make_server(Path(__file__).parent / 'site', store).serve_forever()
