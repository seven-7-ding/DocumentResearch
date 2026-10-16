"""Build a public, allowlisted library from local reading records; no private state is published."""
import collections
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse

ARXIV = re.compile(r'(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?')
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []

    @property
    def text(self):
        return ' '.join(''.join(c.text if isinstance(c, Node) else c for c in self.children).split())

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node): yield from child.walk()

    def has(self, cls): return cls in self.attrs.get('class', '').split()


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node(); self.stack = [self.root]; self.feed(text)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs); self.stack[-1].children.append(n)
        if tag not in VOID: self.stack.append(n)

    def handle_startendtag(self, tag, attrs): self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; break

    def handle_data(self, text):
        if self.stack[-1].tag not in {'script','style'}: self.stack[-1].children.append(text)


def normalized(value):
    return re.sub(r'[^\w]', '', html.unescape(str(value)).casefold())


def list_value(value):
    if isinstance(value, list): return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in re.split(r';|；|\n', str(value or '')) if v.strip()]


def clean_institutions(values):
    result = []
    for value in list_value(values):
        if re.search(r'not explicitly|未明确|未列|未核验|unknown|n/a|待核验|待确认|未提供', value, re.I): continue
        value = re.sub(r'[*🆕⭐]', '', value).strip()
        if value and value not in result: result.append(value)
    return result


def identity(paper):
    url = paper.get('url', '')
    found = ARXIV.search(str(paper.get('arxiv_id', ''))) or ARXIV.search(url)
    if found: return 'arxiv:' + found.group(1)
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname == 'openreview.net':
        key = urllib.parse.parse_qs(parsed.query).get('id', [''])[0]
        if key: return 'openreview:' + key
    return 'paper:' + hashlib.sha256(normalized(paper.get('title', '')).encode()).hexdigest()[:16]


def pdf_url(paper):
    if paper.get('pdf_url','').startswith('https://'): return paper['pdf_url']
    ident = identity(paper)
    if ident.startswith('arxiv:'): return 'https://arxiv.org/pdf/' + ident.split(':', 1)[1]
    if ident.startswith('openreview:'): return 'https://openreview.net/pdf?id=' + ident.split(':', 1)[1]
    url = paper.get('pdf_url') or paper.get('url', '')
    if not url.startswith(('https://','http://')): return ''
    return url


def cards_from_html(text):
    root = Document(text).root
    cards = []
    for node in root.walk():
        if not node.has('paper-card'): continue
        children = list(node.walk())
        heading = next((n.text for n in children if n.tag in {'h2','h3'}), '')
        title = re.sub(r'^\s*(?:\[?\d+\]?\s*[.、·:]?\s*)', '', heading)
        ident = node.attrs.get('data-paper-id', '')
        links = [n.attrs.get('href', '') for n in children if n.tag == 'a']
        url = next((u for u in links if 'arxiv.org/abs/' in u or 'openreview.net/' in u), '')
        if not url and ARXIV.search(ident): url = 'https://arxiv.org/abs/' + ARXIV.search(ident).group(1)
        deep = node.has('is-deep-read') or node.attrs.get('data-deep-read') == 'true'
        # Empty placeholder deep-reading divs are not evidence of a completed read.
        substantial = [n for n in children if n.has('deep-reading-content') and len(n.text)>500 and not n.text.startswith(('尚未','待精读'))]
        deep = deep or bool(substantial)
        institutions = []
        for n in children:
            if n.tag == 'div' and len(n.text)<550:
                label = next((c.text for c in n.children if isinstance(c,Node) and c.tag in {'b','strong'}), '')
                if label in {'机构','Institutions','Institution'}:
                    institutions.extend(clean_institutions(n.text[len(label):]))
            if n.tag == 'tr':
                cells = [c.text for c in n.children if isinstance(c,Node) and c.tag in {'td','th'}]
                if len(cells)>=2 and len(cells[0])<100 and any(x in cells[1] for x in ['University','Institute','DeepMind','Mila','NVIDIA','Stanford','大学','研究院']):
                    institutions.extend(clean_institutions([cells[1]]))
        cards.append({'arxiv_id':ident,'title':title,'url':url,'deep_read':deep,'anchor':node.attrs.get('id',''),'institutions':list(dict.fromkeys(institutions))})
    return cards


def source_papers(source):
    path = source/'paper_index.json'
    raw = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'papers':[]}
    records = raw.get('papers', []) if isinstance(raw,dict) else raw
    papers = {identity(p):dict(p) for p in records if p.get('deep_read')}
    by_title = {normalized(p.get('title','')):p for p in records}
    reports = {}
    for file in sorted(source.glob('????-??-??.html')):
        cards = cards_from_html(file.read_text(encoding='utf-8-sig')); reports[file.stem]=cards
        for card in cards:
            if not card['deep_read']: continue
            old = by_title.get(normalized(card['title']), {})
            candidate = {**old, **{k:v for k,v in card.items() if v and k not in {'institutions','title'}}}
            candidate['title'] = old.get('title') or card['title']
            candidate.setdefault('date_added',file.stem)
            key = identity(candidate)
            p = papers.setdefault(key,candidate)
            p.setdefault('date_added',file.stem)
            if not clean_institutions(p.get('institutions')): p['institutions']=card['institutions']
            p['reading_report']=file.stem; p['reading_anchor']=card['anchor']
    # Older Markdown contains author tables that were not copied into the JSON index.
    for key,p in papers.items():
        md=source/(p.get('date_added','')+'.md')
        if not md.is_file(): continue
        text=md.read_text(encoding='utf-8-sig')
        headings=list(re.finditer(r'^#{2,4}\s+(.+)$',text,re.M))
        positions=[m for m in headings if normalized(p['title']) in normalized(m[1])]
        if positions and not clean_institutions(p.get('institutions')):
            pos=positions[-1].end(); excerpt=text[pos:pos+9000]
            institutions=[]
            for line in excerpt.splitlines():
                cells=[v.strip() for v in line.strip().strip('|').split('|')]
                if len(cells)>=2 and any(normalized(a) in normalized(cells[0]) for a in p.get('authors',[]) if a):
                    institutions.extend(clean_institutions([cells[1]]))
            p['institutions']=list(dict.fromkeys(institutions))
    return list(papers.values()),reports,records


def paper_type(p):
    explicit = p.get('paper_type')
    if explicit in {'技术报告','综述','一般论文','草稿论文/不完整论文'}: return explicit
    context=' '.join(str(p.get(k,'')) for k in ['title','comment','journal_ref'])
    if re.search(r'withdrawn|incomplete manuscript|work in progress|preliminary draft',context,re.I): return '草稿论文/不完整论文'
    if re.search(r'\bsurvey\b|systematic review|综述',context,re.I): return '综述'
    if re.search(r'technical report|技术报告',context,re.I): return '技术报告'
    return '一般论文'


def venue(p):
    if p.get('venue'): return p['venue']
    if p.get('journal_ref'): return p['journal_ref']
    comment = p.get('comment','')
    match=re.search(r'(?:accepted (?:to|at|by|for)|published (?:in|at)|to appear in)\s+([^.;\n]{3,120})',comment,re.I)
    if match: return match[1].strip()
    return 'arXiv 预印本' if identity(p).startswith('arxiv:') else '未注明'


def library_records(source):
    papers,reports,index = source_papers(source)
    metadata_path=source/'library_metadata.json'
    metadata=json.loads(metadata_path.read_text(encoding='utf-8-sig')) if metadata_path.exists() else {}
    output=[]
    for paper in papers:
        key=identity(paper); cached=metadata.get(key,{})
        p={**paper,**cached}
        authors=list_value(p.get('authors')); institutions=clean_institutions(p.get('institutions')) or clean_institutions(paper.get('institutions'))
        # Strict allowlist: never spread the private paper index into deployment data.
        item={'id':key,'title':p.get('title',''),'title_zh':paper.get('title_zh',''),
              'authors':authors,'first_author':authors[0] if authors else '', 'last_author':authors[-1] if authors else '',
              'type':paper_type(p),'institutions':institutions,
              'published':p.get('date_updated') or p.get('date_published',''),
              'venue':venue(p),'added':paper.get('deep_read_date') or paper.get('date_added',''),
              'url':p.get('url',''),'pdf_url':pdf_url(p),'version':p.get('version',''),
              'topics':list_value(paper.get('topics')),'tags':[],'notes':'','rating':None,
              'metadata_checked':cached.get('checked_at',''),
              'version_verified':bool(cached.get('date_updated'))}
        day=paper.get('reading_report')
        if day: item['reading_url']='reports/'+day+'/#'+paper.get('reading_anchor','')
        output.append(item)
    return sorted(output,key=lambda p:(p['added'],p['id']),reverse=True),reports,index


def report_summary(day,cards,index):
    related=[p for p in index if p.get('date_added')==day]
    topics=collections.Counter(t for p in related for t in list_value(p.get('topics')))
    return {'paper_count':len(cards) if cards else len(related),
            'deep_count':sum(bool(c['deep_read']) for c in cards) if cards else sum(bool(p.get('deep_read')) for p in related),
            'topics':[t for t,_ in topics.most_common(4)]}


def encode(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')


def library_payload(source):
    papers,reports,index=library_records(source)
    if len(encode(papers)) > 5 * 1024 * 1024:
        raise ValueError('Library exceeds the 5 MiB client search budget; split the archive before publishing.')
    # Partition by the stable identity hash so new entries do not reshuffle every shard.
    buckets=collections.defaultdict(list)
    for p in papers:buckets[hashlib.sha256(p['id'].encode()).hexdigest()[0]].append(p)
    payload={}; shards=[]
    for bucket,rows in sorted(buckets.items()):
        rows.sort(key=lambda p:p['id']);data=encode(rows)
        name=f'library/{bucket}-{hashlib.sha256(data).hexdigest()[:12]}.json'
        payload[name]=data;shards.append({'url':name,'count':len(rows),'bytes':len(data)})
    payload['library/manifest.json']=encode({'schema':1,'count':len(papers),'shards':shards})
    return payload,reports,index
