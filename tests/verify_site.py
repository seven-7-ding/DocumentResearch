"""Real Chromium rendering and HTTP verification, with all evidence in one run."""
import argparse
import functools
import http.server
import json
from pathlib import Path
import ssl
import sys
import threading
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publisher as p
from browser_cdp import Browser


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', required=True, type=Path)
    parser.add_argument('--url', help='Verify deployed bytes and rendering against this cloud URL')
    parser.add_argument('--browser', default='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    args = parser.parse_args()
    run = p.new_run('browser')
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(args.site.resolve())))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = args.url.rstrip('/') + '/' if args.url else f'http://127.0.0.1:{server.server_port}/'
    result = {'files_verified': 0, 'browser': []}
    try:
        for file in args.site.rglob('*'):
            if file.is_file():
                path = file.relative_to(args.site).as_posix()
                if path.startswith('.'): continue
                context = ssl.create_default_context(cafile=ssl.get_default_verify_paths().cafile)
                with urllib.request.urlopen(base + path, timeout=30, context=context) as response:
                    if response.read() != file.read_bytes():
                        raise ValueError('HTTP mismatch: ' + path)
                result['files_verified'] += 1
        reports = sorted((args.site / 'reports').iterdir())
        redirect='https://huggingface.co/spaces/seven-7-ding/DocumentResearch' in (args.site/'index.html').read_text(encoding='utf-8')
        route='reports/'+reports[-1].name+'/' if redirect else ''
        cases = [('desktop', route, 1440, 1000), ('mobile', route, 390, 844)]
        browser = Browser(args.browser, run / 'chromium')
        try:
            for name, route, width, height in cases:
                data = browser.capture(base + route, name, width, height)
                if data['errors'] or data['scrollWidth'] > data['width'] + 1:
                    raise ValueError(name + ': render error or horizontal page overflow: ' + str(data))
                if not route and not data['cards']: raise ValueError('Catalog is empty')
                result['browser'].append({'case': name, **data})
            if redirect:
                result['private_portal_redirect']=True
                (run / 'result.json').write_bytes(p.encode(result))
                print(json.dumps({'run_dir':str(run),**result},indent=2))
                return
            browser.call('Page.navigate', {'url': base})
            # Reuse the loaded catalog to test an actual UI event.
            browser.capture(base, 'filter-before', 390, 844)
            month=reports[-1].name[:7]
            expression="""(async()=>{const month=MONTH,select=document.querySelector('#month');select.value=month;select.dispatchEvent(new Event('change'));for(let i=0;i<150;i++){await new Promise(r=>setTimeout(r,100));const cards=[...document.querySelectorAll('.report-card')];if(cards.length&&cards.every(c=>c.innerText.startsWith(month)))return cards.length;}throw new Error('Month filter did not render');})()""".replace('MONTH',json.dumps(month))
            found=browser.evaluate(expression)
            result['month_filter_matches']=found
        finally:
            browser.close()
        (run / 'result.json').write_bytes(p.encode(result))
        print(json.dumps({'run_dir': str(run), **result}, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
