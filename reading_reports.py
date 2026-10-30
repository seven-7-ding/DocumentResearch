"""Extract existing paper-specific Markdown readings, without daily private logs."""
import hashlib
import html
from html.parser import HTMLParser
from pathlib import Path
import re
import urllib.parse


def key(text):
    return re.sub(r'[^\w]', '', html.unescape(text).casefold())


def find_readings(source, papers):
    sections = []
    for file in sorted(source.glob('????-??-??.md')):
        text = file.read_text(encoding='utf-8-sig')
        headings = list(re.finditer(r'^(#{1,4})\s+(.+)$', text, re.M))
        for i, match in enumerate(headings):
            end = next((n.start() for n in headings[i+1:] if len(n[1]) <= len(match[1])), len(text))
            body = text[match.start():end]
            if len(body) > 900:
                sections.append((key(match[2]), body, file))
    result = {}
    for p in papers:
        if p.get('reading_report'):
            continue
        candidates=[]
        target=key(p['title'])
        for title,body,file in sections:
            if target not in title:continue
            prefix=title.split(target,1)[0]
            # Heading decorations/numbers are allowed; another paper's longer title
            # is not (e.g. "A note on convergence of Wasserstein Policy Optimization").
            primary=re.search(r'https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})',body[:900])
            if primary and p.get('arxiv_id') and primary[1]!=p['arxiv_id']:continue
            if re.search(r'[a-zA-Z]',re.sub(r'^paper\d*','',prefix)) and not (primary and primary[1]==p.get('arxiv_id')):continue
            candidates.append((body,file))
        if candidates:
            # Prefer the most substantive existing reading over a short recommendation.
            result[key(p['title'])] = max(candidates, key=lambda row: len(row[0]))
    return result


class SafeHTML(HTMLParser):
    tags = set('h1 h2 h3 h4 h5 h6 p div span strong em b i ul ol li blockquote pre code table thead tbody tr th td hr br a img del sup sub'.split())
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source, self.output, self.assets = source, [], {}

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:return
        values = dict(attrs); safe = {}
        if tag in {'a','img'}:
            field = 'href' if tag == 'a' else 'src'; url = values.get(field, '')
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme == 'https' or url.startswith('#'):
                safe[field] = url
            elif tag == 'img' and not parsed.scheme and not url.startswith(('/', '\\')):
                path = (self.source.parent / urllib.parse.unquote(parsed.path)).resolve()
                if path.is_relative_to(self.source.parent.resolve()) and path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif','.svg'} and path.is_file():
                    data = path.read_bytes()
                    if len(data) > 15*1024*1024:raise ValueError('Reading image exceeds 15MB')
                    name = hashlib.sha256(data).hexdigest()[:24]+path.suffix.lower()
                    self.assets['readings/assets/'+name] = data; safe[field] = 'assets/'+name
                else:
                    self.output.append('<p class="missing">原记录图片已缺失，请参阅论文原文。</p>');return
            if tag == 'img':safe.update(alt=values.get('alt',''),loading='lazy')
            else:safe.update(target='_blank',rel='noopener noreferrer')
        self.output.append('<'+tag+''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in safe.items())+'>')
    def handle_endtag(self, tag):
        if tag in self.tags:self.output.append('</'+tag+'>')
    def handle_data(self, data):self.output.append(html.escape(data))
    def handle_entityref(self, name):self.output.append('&'+name+';')
    def handle_charref(self, name):self.output.append('&#'+name+';')


def path_for(ident):
    return 'readings/'+hashlib.sha256(ident.encode()).hexdigest()[:20]+'.html'


def render(body, source, title, pdf):
    import markdown  # Build-time dependency; install from requirements-build.txt into base.
    # Exclude appended conversation/execution logs. Only the selected paper section is exported.
    body = re.split(r'^#{1,4}\s+.*(?:对话记录|用户追问|执行日志|User:|Assistant:)', body, maxsplit=1, flags=re.M)[0]
    body = re.sub(r'(?:file:///)?[A-Za-z]:[\\/][^\s)\]<>]+', '[本地路径]', body)
    math = []
    def hold(m):
        math.append(m[0]);return 'MATHPLACEHOLDER'+str(len(math)-1)+'END'
    text = re.sub(r'\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|(?<!\$)\$(?!\$)[^\n$]+\$', hold, body)
    markup = markdown.markdown(text, extensions=['tables','fenced_code','sane_lists'])
    clean = SafeHTML(source);clean.feed(markup)
    content = ''.join(clean.output)
    for i, formula in enumerate(math):content=content.replace('MATHPLACEHOLDER'+str(i)+'END',html.escape(formula))
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer">
<title>'''+html.escape(title)+''' · 精读报告</title><style>body{font:16px/1.85 "Times New Roman","Noto Serif CJK SC","SimSun",serif;color:#253c3b;background:#fafbf9;max-width:940px;margin:32px auto;padding:0 22px}a{color:#186c5e}img{max-width:100%;height:auto}table{border-collapse:collapse;display:block;overflow:auto}th,td{border:1px solid #dfe7e2;padding:8px}pre{overflow:auto;background:#edf3ef;padding:15px}h1{font-size:26px}h2{font-size:23px}.missing{color:#805520}mjx-container[display="true"]{overflow-x:auto;overflow-y:hidden;padding:6px}</style>
<script>window.MathJax={tex:{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$'],['\\\\[','\\\\]']]},options:{skipHtmlTags:['script','style','textarea','pre','code']}};</script><script defer src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js"></script>
<nav><a href="../#library">图书馆</a> · <a href="'''+html.escape(pdf,quote=True)+'''" target="_blank" rel="noopener noreferrer">论文 PDF</a></nav><main>'''+content+'</main></html>'
    return page.encode('utf-8'), clean.assets
