"""Publish the compact portal to HF; large daily reports stay in GitHub Pages."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import publisher as p

SPACE = 'seven-7-ding/DocumentResearch'
HOST = 'https://seven-7-ding-documentresearch.static.hf.space/'
PAGES = 'https://seven-7-ding.github.io/DocumentResearch/'
README = '''---
title: Document Research
emoji: 📚
colorFrom: green
colorTo: gray
sdk: static
app_file: index.html
pinned: false
license: apache-2.0
---

Daily papers and a personal reading library. Sign in with Hugging Face to sync
annotations into a private Dataset owned by your account.

Source: https://github.com/seven-7-ding/DocumentResearch
'''


def git(directory, *args):
    result = subprocess.run(['git', '-C', str(directory), *args], capture_output=True, text=True,
                            encoding='utf-8', env={**os.environ, 'GIT_TERMINAL_PROMPT':'0', 'GCM_INTERACTIVE':'never'})
    if result.returncode: raise RuntimeError('Git failed: '+result.stderr[-1200:])
    return result.stdout.strip()


def publish():
    run = p.new_run('space')
    config=json.loads((p.ROOT/'config.json').read_text(encoding='utf-8'))
    api=p.GitHub(config['repository']);_,remote=api.snapshot('gh-pages')
    if 'library/manifest.json' not in remote: raise ValueError('Publish GitHub portal first.')
    manifest=json.loads(api.read(remote['library/manifest.json']))
    # Only current shards and small catalogs. No report copies or private local index.
    allowed={'index.html','app.js','style.css','sync.js','oauth-client.json','library/manifest.json'}
    allowed.update(s['url'] for s in manifest['shards'])
    allowed.update(path for path in remote if path.startswith('catalog/') and path.endswith('.json'))
    checkout=run/'space'
    git(run,'clone','--depth','1','https://huggingface.co/spaces/'+SPACE,str(checkout))
    for path in git(checkout,'ls-files').splitlines():
        if path.startswith(('catalog/','library/')) and path not in allowed:
            git(checkout,'rm','--',path)
    total=0
    for path in sorted(allowed):
        data=api.read(remote[path])
        if path.startswith('catalog/') and path!='catalog/months.json':
            rows=json.loads(data)
            for row in rows: row['url']=PAGES+row['url']
            data=p.encode(rows)
        target=checkout/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);total+=len(data)
    (checkout/'README.md').write_text(README,encoding='utf-8')
    git(checkout,'add','--',*sorted(allowed),'README.md')
    if git(checkout,'status','--porcelain'):
        git(checkout,'commit','-m','Publish reading portal and private cloud sync')
        git(checkout,'push','origin','HEAD:main')
    result={'space':SPACE,'url':HOST,'bytes':total,'commit':git(checkout,'rev-parse','HEAD')}
    (run/'result.json').write_bytes(p.encode(result));p.trace('HF portal deployed: '+result['commit'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    try:publish()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
