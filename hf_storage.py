"""Private Dataset persistence. Credentials remain in the Space process only."""
import base64
import datetime as dt
import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.request


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def empty():
    return {'tags': [], 'notes': '', 'rating': None}


class Conflict(Exception):
    def __init__(self, remote):
        self.remote = remote


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('无效笔记')
    tags, notes, rating = (value.get(k) for k in ('tags', 'notes', 'rating'))
    if (not isinstance(tags, list) or len(tags) > 20 or
        any(not isinstance(t, str) or len(t) > 40 for t in tags) or
        not isinstance(notes, str) or len(notes) > 10000 or
        not (rating is None or type(rating) is int and 1 <= rating <= 5)):
        raise ValueError('标签最多20个、每个40字，笔记最多10000字，评分为1至5。')
    return {'tags': list(dict.fromkeys(t.strip() for t in tags if t.strip())), 'notes': notes, 'rating': rating}


def merge(base, local, remote):
    base, local, remote = map(validate, (base, local, remote))
    merged = dict(remote)
    for key in ('tags', 'notes', 'rating'):
        if local[key] == base[key]:
            continue
        if remote[key] != base[key] and remote[key] != local[key]:
            raise Conflict(remote)
        merged[key] = local[key]
    return merged


def bucket(ident):
    # Compatible with the previous browser store's FNV-1a partitioning.
    value = 2166136261
    for char in ident:
        value = ((value ^ ord(char)) * 16777619) & 0xffffffff
    return f'notes/{value & 15:x}.json'


class Hub:
    def __init__(self, token):
        self.token = token
        self.context = ssl.create_default_context(cafile=ssl.get_default_verify_paths().cafile)

    def call(self, path, method='GET', body=None, raw=False):
        request = urllib.request.Request('https://huggingface.co' + path, method=method,
            headers={'Authorization': 'Bearer ' + self.token,
                     'Content-Type': 'application/x-ndjson' if raw else 'application/json'},
            data=body if raw else encode(body) if body is not None else None)
        with urllib.request.urlopen(request, context=self.context, timeout=30) as response:
            data = response.read(3_000_001)
            if len(data) > 3_000_000:
                raise ValueError('云端文件超过容量限制')
            if not data:return None
            try:return json.loads(data)
            except (ValueError, UnicodeDecodeError):return None


class Store:
    def __init__(self, hub, repo):
        self.hub, self.repo = hub, repo
        self.lock = threading.RLock()
        self.head = None
        self.items = {}
        self.meta = {'schema': 2, 'buckets': [], 'writes': 0, 'history_bytes': 0}

    def pull(self):
        with self.lock:
            info = self.hub.call('/api/datasets/' + self.repo)
            if info.get('private') is not True:
                raise ValueError('笔记仓库必须为私有；已停止同步。')
            if info.get('sha') == self.head and self.head:
                return self.snapshot()
            head = info.get('sha')
            doc = {'schema': 2, 'buckets': [], 'writes': 0, 'history_bytes': 0}
            def read(path):
                return self.hub.call('/datasets/' + self.repo + '/resolve/' + head + '/' + path)
            if head:
                try:
                    doc = read('annotations.json')
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
            if doc.get('schema') == 1:
                items = doc['items']
            else:
                paths = doc.get('buckets')
                if doc.get('schema') != 2 or not isinstance(paths, list) or len(paths) > 16 or any(not re.fullmatch(r'notes/[0-9a-f]\.json', p) for p in paths):
                    raise ValueError('笔记目录格式异常')
                items = {}
                for path in paths:
                    items.update(read(path))
            if len(encode(items)) > 2_000_000:
                raise ValueError('笔记超过2MB容量限制')
            for ident, value in items.items():
                if not isinstance(ident, str) or len(ident) > 180:
                    raise ValueError('无效论文标识')
                validate(value)
            self.head, self.items, self.meta = head, items, doc
            return self.snapshot()

    def snapshot(self):
        return {'items': self.items, 'head': self.head, 'meta': self.meta}

    def commit(self, files):
        header = {'summary': 'Update reading notes'}
        if self.head:
            header['parentCommit'] = self.head
        lines = [{'key': 'header', 'value': header}]
        for path, data in files.items():
            lines.append({'key': 'file', 'value': {'path': path, 'content': base64.b64encode(data).decode(), 'encoding': 'base64'}})
        return self.hub.call('/api/datasets/' + self.repo + '/commit/main', 'POST',
                             b'\n'.join(encode(line) for line in lines) + b'\n', raw=True)

    def save(self, ident, value, base):
        if not isinstance(ident, str) or not ident or len(ident) > 180:
            raise ValueError('无效论文标识')
        validate(value); validate(base)
        with self.lock:
            for _ in range(3):
                self.pull()
                remote = self.items.get(ident, empty())
                merged = merge(base, value, remote)
                if merged == validate(remote):
                    return self.snapshot()
                items = {**self.items, ident: {**merged, 'updated_at': dt.datetime.now(dt.timezone.utc).isoformat()}}
                if len(encode(items)) > 2_000_000:
                    raise ValueError('笔记总量已达2MB，请先导出并整理。')
                paths = {bucket(i) for i in items} if self.meta['schema'] == 1 else {bucket(ident)}
                files = {path: encode({i: v for i, v in items.items() if bucket(i) == path}) for path in paths}
                doc = {'schema': 2, 'buckets': sorted(set(self.meta.get('buckets', [])) | paths),
                       'writes': self.meta.get('writes', 0) + 1,
                       'history_bytes': self.meta.get('history_bytes', 0) + sum(map(len, files.values())) + 512}
                if doc['history_bytes'] > 100_000_000:
                    raise ValueError('笔记历史达到维护阈值，请先导出并整理历史。')
                files['annotations.json'] = encode(doc)
                try:
                    self.commit(files)
                    self.head = None
                    return self.pull()
                except urllib.error.HTTPError as e:
                    if e.code not in (409, 412):
                        raise
            raise ValueError('另一台设备正在更新，请稍后重试。')

    def compact(self):
        with self.lock:
            self.pull()
            self.hub.call('/api/datasets/' + self.repo + '/super-squash/main', 'POST',
                          {'message': 'Compact history; preserve current notes'})
            for _ in range(3):
                self.head = None
                self.pull()
                try:
                    self.commit({'annotations.json': encode({**self.meta, 'history_bytes': 0})})
                    self.head = None
                    return self.pull()
                except urllib.error.HTTPError as e:
                    if e.code not in (409, 412):
                        raise
            raise ValueError('另一台设备正在更新，整理后请重试。')
