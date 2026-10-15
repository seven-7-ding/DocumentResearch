"""Dependency-free, incremental daily-paper publisher. Python 3.10+ in conda bit."""
import argparse
import base64
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.avif', '.svg'}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def new_run(label):
    path = ROOT / 'logdir' / (dt.datetime.now().strftime('%Y%m%d_%H%M%S_') + label + '_' + uuid.uuid4().hex[:8])
    path.mkdir(parents=True)
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        os.environ[key] = str(path)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    return path


def trace(message):
    path = ROOT / 'codex-executor.log'
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    important = [line for line in lines if line.startswith('[IMPORTANT]')][:1]
    recent = [line for line in lines if not line.startswith('[IMPORTANT]')]
    recent.append(f'[{dt.datetime.now().isoformat(timespec="seconds")}] {message}')
    path.write_text('\n'.join(important + recent[-5:]) + '\n', encoding='utf-8')


def credentials():
    token = os.environ.get('GITHUB_TOKEN', '')
    env = ROOT / '.env'
    if not token and env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            if line.startswith('GITHUB_TOKEN='):
                token = line.partition('=')[2].strip().strip('"\'')
    if not token:
        result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                                text=True, capture_output=True, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'})
        token = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line).get('password', '')
    if not token:
        raise ValueError('No GitHub credential. Configure Git Credential Manager or GITHUB_TOKEN in .env.')
    return token


class GitHub:
    def __init__(self, repo):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
            raise ValueError('repository must be owner/name')
        self.repo = repo
        self.token = credentials()

    def api(self, path, method='GET', body=None, missing=False):
        url = 'https://api.github.com' + path
        request = urllib.request.Request(url, data=encode(body) if body is not None else None, method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'User-Agent': 'DocumentResearch',
                     'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'})
        try:
            # Explicit CA bundle avoids malformed certificates in Windows' user store.
            context = ssl.create_default_context(cafile=ssl.get_default_verify_paths().cafile)
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise RuntimeError(f'GitHub {method} {path}: HTTP {error.code}') from None

    def endpoint(self, suffix):
        return '/repos/' + self.repo + suffix

    def snapshot(self, branch):
        ref = self.api(self.endpoint('/git/ref/heads/' + branch), missing=True)
        if not ref:
            return None, {}
        head = ref['object']['sha']
        commit = self.api(self.endpoint('/git/commits/' + head))
        tree = self.api(self.endpoint('/git/trees/' + commit['tree']['sha'] + '?recursive=1'))
        if tree.get('truncated'):
            raise ValueError('Remote tree truncated; split archive before publishing.')
        return head, {item['path']: item for item in tree['tree'] if item['type'] == 'blob'}

    def read(self, item):
        blob = self.api(self.endpoint('/git/blobs/' + item['sha']))
        return base64.b64decode(blob['content'])

    def publish(self, branch, head, remote, payload, deleted):
        changed = {path: data for path, data in payload.items() if remote.get(path, {}).get('sha') != sha(data)}
        if not changed and not deleted:
            return {'changed_files': 0, 'uploaded_bytes': 0, 'commit': head}
        entries = []
        for path, data in sorted(changed.items()):
            blob = self.api(self.endpoint('/git/blobs'), 'POST', {'content': base64.b64encode(data).decode(), 'encoding': 'base64'})
            entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        entries.extend({'path': path, 'mode': '100644', 'type': 'blob', 'sha': None} for path in sorted(deleted))
        body = {'tree': entries}
        if head:
            body['base_tree'] = self.api(self.endpoint('/git/commits/' + head))['tree']['sha']
        tree = self.api(self.endpoint('/git/trees'), 'POST', body)
        commit = self.api(self.endpoint('/git/commits'), 'POST', {
            'message': 'Publish daily papers', 'tree': tree['sha'], 'parents': [head] if head else []})
        # Non-forced update is an optimistic lock: concurrent publication must be retried.
        if head:
            self.api(self.endpoint('/git/refs/heads/' + branch), 'PATCH', {'sha': commit['sha'], 'force': False})
        else:
            self.api(self.endpoint('/git/refs'), 'POST', {'ref': 'refs/heads/' + branch, 'sha': commit['sha']})
        return {'changed_files': len(changed), 'deleted_files': len(deleted),
                'uploaded_bytes': sum(map(len, changed.values())), 'commit': commit['sha']}


class Report(HTMLParser):
    """Preserve script/style text and rewrite only explicit local image references."""
    def __init__(self, source, max_file, allow_missing=False, previous=None):
        super().__init__(convert_charrefs=False)
        self.source = source.resolve()
        self.day = source.stem
        self.max_file = max_file
        self.output = []
        self.assets = {}
        self.title = []
        self.in_title = False
        self.allow_missing = allow_missing
        self.warnings = []
        self.previous = previous or {}
        self.asset_map = {}
        self.retained_bytes = 0
        self.retained = set()

    def local_url(self, value):
        parsed = urllib.parse.urlsplit(value)
        if value.startswith(('#', '//')) or parsed.scheme in ('https', 'http', 'data', 'mailto'):
            return value
        if parsed.scheme or value.startswith(('/', '\\')):
            raise ValueError(f'{self.day}: unsupported absolute/local URL')
        if not parsed.path:
            return value
        file = (self.source.parent / urllib.parse.unquote(parsed.path)).resolve()
        if not file.is_relative_to(self.source.parent) or file.suffix.lower() not in IMAGES:
            raise ValueError(f'{self.day}: local references must be images within source_dir: {parsed.path}')
        source_key = hashlib.sha256(file.relative_to(self.source.parent).as_posix().encode()).hexdigest()
        if not file.is_file():
            if source_key in self.previous:
                saved = self.previous[source_key]
                self.asset_map[source_key] = saved['path']
                if saved['path'] not in self.retained:
                    self.retained_bytes += saved['size']
                    self.retained.add(saved['path'])
                return 'assets/' + saved['path'].rsplit('/', 1)[-1]
            if self.allow_missing:
                self.warnings.append(f'Missing historical image: {parsed.path}')
                return None
            raise ValueError(f'{self.day}: missing image {parsed.path}; restore it before publishing')
        data = file.read_bytes()
        if len(data) > self.max_file:
            raise ValueError(f'{self.day}: image exceeds max_file_mb')
        name = hashlib.sha256(data).hexdigest()[:24] + file.suffix.lower()
        path = f'reports/{self.day}/assets/{name}'
        self.assets[path] = data
        self.asset_map[source_key] = path
        return 'assets/' + name + ('#' + parsed.fragment if parsed.fragment else '')

    def tag(self, tag, attrs, close=False):
        attrs = dict(attrs)
        if tag == 'base':
            raise ValueError(f'{self.day}: base URLs are unsupported')
        for key in ('src', 'href', 'poster', 'data-src'):
            if attrs.get(key):
                value = attrs[key]
                # Local paper PDFs are not uploaded; use their public arXiv originals.
                paper = re.search(r'(\d{4}\.\d{4,5})(?:v\d+)?\.pdf$', value)
                if key == 'href' and not urllib.parse.urlsplit(value).scheme and paper:
                    attrs[key] = 'https://arxiv.org/pdf/' + paper.group(1)
                else:
                    attrs[key] = self.local_url(value)
                    if attrs[key] is None:
                        attrs.pop(key)
                        attrs['alt'] = '历史图片原文件已清理，无法显示；请参阅论文原文。'
                        attrs['title'] = attrs['alt']
                        self.output.append('<p role="note" class="missing-asset">历史图片原文件已清理，无法显示；请参阅论文原文。</p>')
        if tag == 'a' and attrs.get('href', '').startswith(('https://', 'http://')):
            attrs['target'] = '_blank'
            attrs['rel'] = 'noopener noreferrer'
        if attrs.get('srcset'):
            raise ValueError(f'{self.day}: use a single src instead of srcset before publishing')
        if tag == 'img':
            attrs.setdefault('loading', 'lazy')
        text = '<' + tag + ''.join(' ' + key + ('' if value is None else '="' + html.escape(value, quote=True) + '"') for key, value in attrs.items())
        self.output.append(text + ('/>' if close else '>'))
        if tag == 'title':
            self.in_title = True

    def handle_starttag(self, tag, attrs): self.tag(tag, attrs)
    def handle_startendtag(self, tag, attrs): self.tag(tag, attrs, True)
    def handle_endtag(self, tag):
        self.output.append('</' + tag + '>')
        if tag == 'title': self.in_title = False
    def handle_data(self, data):
        self.output.append(data)
        if self.in_title: self.title.append(data)
    def handle_entityref(self, name): self.output.append('&' + name + ';')
    def handle_charref(self, name): self.output.append('&#' + name + ';')
    def handle_comment(self, data): self.output.append('<!--' + data + '-->')
    def handle_decl(self, decl): self.output.append('<!' + decl + '>')


def build_report(file, max_file, allow_missing=False, previous=None):
    text = file.read_text(encoding='utf-8-sig')
    if '\ufffd' in text or re.search(r'(?:file:///|[A-Z]:[\\/])', text):
        raise ValueError(f'{file.name}: encoding error or absolute local path')
    if re.search(r'url\(\s*[\'"]?(?!https:|http:|data:|#)', text, re.I):
        raise ValueError(f'{file.name}: unsupported local CSS resource')
    parser = Report(file, max_file, allow_missing, previous)
    parser.feed(text)
    parser.close()
    data = ''.join(parser.output).encode('utf-8')
    if len(data) > max_file:
        raise ValueError(f'{file.name}: HTML exceeds max_file_mb')
    payload = {f'reports/{file.stem}/index.html': data,
               f'reports/{file.stem}/asset-map.json': encode(parser.asset_map), **parser.assets}
    return payload, {'date': file.stem, 'title': ''.join(parser.title) or file.stem,
                     'url': f'reports/{file.stem}/', 'bytes': sum(map(len, payload.values())) + parser.retained_bytes,
                     'missing_images': len(parser.warnings)}


def plan(files, config, remote, read):
    payload = {file.name: file.read_bytes() for file in (ROOT / 'web').iterdir() if file.is_file()}
    payload['.nojekyll'] = b''
    deleted = set()
    months = {}
    max_file = config['max_file_mb'] * 1024 * 1024
    for file in files:
        prefix = f'reports/{file.stem}/'
        map_key = prefix + 'asset-map.json'
        previous = {}
        if map_key in remote:
            for key, path in json.loads(read(remote[map_key])).items():
                if path.startswith(prefix + 'assets/') and path in remote:
                    previous[key] = {'path': path, 'size': remote[path].get('size', 0)}
        report, item = build_report(file, max_file, config.get('allow_missing_images', False), previous)
        retained = set(json.loads(report[map_key]).values())
        deleted.update(path for path in remote if path.startswith(prefix) and path not in report and path not in retained)
        payload.update(report)
        month = file.stem[:7]
        if month not in months:
            key = f'catalog/{month}.json'
            months[month] = {row['date']: row for row in json.loads(read(remote[key]))} if key in remote else {}
        months[month][file.stem] = item
    all_months = {p[8:-5] for p in remote if re.fullmatch(r'catalog/\d{4}-\d{2}\.json', p)} | set(months)
    for month, entries in months.items():
        payload[f'catalog/{month}.json'] = encode(sorted(entries.values(), key=lambda item: item['date'], reverse=True))
    payload['catalog/months.json'] = encode(sorted(all_months, reverse=True))
    total = sum(item.get('size', 0) for path, item in remote.items() if path not in payload and path not in deleted) + sum(map(len, payload.values()))
    changed = {path: data for path, data in payload.items() if remote.get(path, {}).get('sha') != sha(data)}
    upload = sum(map(len, changed.values()))
    if total > config['max_site_mb'] * 1024 * 1024:
        raise ValueError('Site exceeds max_site_mb; archive to another repository before publishing.')
    if upload > config['max_upload_mb'] * 1024 * 1024:
        raise ValueError('Upload exceeds max_upload_mb; publish fewer days at a time.')
    return payload, deleted, {'site_bytes': total, 'changed_files': len(changed), 'upload_bytes': upload, 'reports': len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'publish', 'status'])
    parser.add_argument('--date', help='YYYY-MM-DD; default latest HTML report')
    parser.add_argument('--all', action='store_true', help='Explicit backfill of all daily HTML reports')
    parser.add_argument('--allow-missing-images', action='store_true', help='Historical backfill only: visibly mark lost images instead of failing')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    args = parser.parse_args()
    run = new_run(args.command)
    try:
        config = json.loads(args.config.read_text(encoding='utf-8-sig'))
        config['allow_missing_images'] = args.allow_missing_images
        if config['branch'] != 'gh-pages':
            raise ValueError('Only the dedicated gh-pages deployment branch is allowed')
        api = GitHub(config['repository']) if args.command != 'build' else None
        if args.command == 'status':
            result = api.api(api.endpoint('/pages'))
            result = {key: result.get(key) for key in ('html_url', 'status', 'source', 'build_type')}
        else:
            source = (args.config.resolve().parent / config['source_dir']).resolve()
            files = sorted(file for file in source.glob('*.html') if DATE.fullmatch(file.stem))
            if args.date:
                dt.date.fromisoformat(args.date)
                files = [file for file in files if file.stem == args.date]
            elif not args.all:
                files = files[-1:]
            if not files:
                raise ValueError('No matching daily HTML report found')
            head, remote = api.snapshot(config['branch']) if api else (None, {})
            if api:
                repository = api.api(api.endpoint(''))
                if repository.get('size', 0) > config.get('max_repo_mb', 850) * 1024:
                    raise ValueError('Repository history exceeds max_repo_mb; migrate new reports to a fresh annual archive.')
            payload, deleted, summary = plan(files, config, remote, api.read if api else None)
            for path, data in payload.items():
                target = run / 'site' / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            result = {'run_dir': str(run), **summary}
            if api:
                result.update(api.publish(config['branch'], head, remote, payload, deleted))
                result['url'] = 'https://' + config['repository'].split('/')[0] + '.github.io/' + config['repository'].split('/')[1] + '/'
        (run / 'result.json').write_bytes(encode(result))
        trace(f'{args.command}: success; evidence {run.name}')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        # API errors are deliberately sanitized; no headers or credential output.
        result = {'error': str(error), 'run_dir': str(run)}
        (run / 'result.json').write_bytes(encode(result))
        trace(f'{args.command}: failed; evidence {run.name}')
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
