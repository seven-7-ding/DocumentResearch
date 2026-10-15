"""Real Chromium rendering and HTTP verification, with all evidence in one run."""
import argparse
import functools
import http.server
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publisher as p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', required=True, type=Path)
    parser.add_argument('--browser', default='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    args = parser.parse_args()
    run = p.new_run('browser')
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(args.site.resolve())))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/'
    result = {'files_verified': 0, 'browser': []}
    try:
        for file in args.site.rglob('*'):
            if file.is_file():
                path = file.relative_to(args.site).as_posix()
                with urllib.request.urlopen(base + path, timeout=15) as response:
                    if response.read() != file.read_bytes():
                        raise ValueError('HTTP mismatch: ' + path)
                result['files_verified'] += 1
        reports = sorted((args.site / 'reports').iterdir())
        cases = [('desktop', '', '1440,1000'), ('mobile', '', '390,844'),
                 ('latest-report', 'reports/' + reports[-1].name + '/', '390,844')]
        for name, route, size in cases:
            command = [args.browser, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                '--user-data-dir=' + str(run / ('profile-' + name)), '--window-size=' + size,
                '--virtual-time-budget=12000', '--dump-dom', '--screenshot=' + str(run / (name + '.png')), base + route]
            proc = subprocess.run(command, capture_output=True, timeout=55)
            (run / (name + '.html')).write_bytes(proc.stdout)
            (run / (name + '.stderr.txt')).write_bytes(proc.stderr)
            dom = proc.stdout.decode('utf-8', errors='replace')
            if proc.returncode or not (run / (name + '.png')).exists():
                raise ValueError(name + ': browser failed')
            if not route and 'class="card"' not in dom:
                raise ValueError(name + ': catalog did not render')
            if route and 'class="katex-error"' in dom:
                raise ValueError(name + ': KaTeX errors')
            count = len(re.findall(r'class="katex"', dom))
            if route and 'renderMathInElement' in dom and count == 0:
                raise ValueError(name + ': math did not render')
            result['browser'].append({'case': name, 'katex_count': count, 'screenshot': name + '.png'})
        (run / 'result.json').write_bytes(p.encode(result))
        print(json.dumps({'run_dir': str(run), **result}, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
