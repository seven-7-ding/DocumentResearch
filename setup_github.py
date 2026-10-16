"""Explicit first-time setup after choosing public GitHub Pages publication."""
import json
from pathlib import Path
import subprocess
import sys
import publisher as p


def main():
    if '--public' not in sys.argv:
        raise SystemExit('Run with --public only after deciding to publish selected reports publicly.')
    run = p.new_run('setup')
    config = json.loads((p.ROOT / 'config.json').read_text(encoding='utf-8'))
    api = p.GitHub(config['repository'])
    repo = api.api(api.endpoint(''), missing=True)
    if not repo:
        owner, name = config['repository'].split('/')
        user = api.api('/user')['login']
        if owner != user:
            raise SystemExit('Automatic creation supports your personal account only.')
        repo = api.api('/user/repos', 'POST', {'name': name, 'private': False,
            'description': 'Incremental daily-paper archive and publisher', 'auto_init': False})
    if repo['private']:
        raise SystemExit('Existing repository is private; visibility was not changed.')
    # Source is pushed separately. Never stage the entire working directory here.
    expected = 'https://github.com/' + config['repository'] + '.git'
    origin = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=p.ROOT, capture_output=True, text=True)
    if origin.returncode:
        subprocess.run(['git', 'remote', 'add', 'origin', expected], cwd=p.ROOT, check=True)
    elif origin.stdout.strip() != expected:
        raise SystemExit('Existing origin differs from config; inspect it before continuing.')
    result = {'repository': repo['html_url'], 'next': 'Push main, publish reports, then enable Pages with --enable-pages.'}
    if '--enable-pages' in sys.argv:
        pages = api.api(api.endpoint('/pages'), missing=True)
        desired = {'branch': 'gh-pages', 'path': '/'}
        if pages and pages.get('source') != desired:
            raise SystemExit('Existing Pages configuration differs; left unchanged.')
        if not pages:
            pages = api.api(api.endpoint('/pages'), 'POST', {'build_type': 'legacy', 'source': desired})
        result['url'] = pages['html_url']
        config['publication_enabled'] = True
        (p.ROOT / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
