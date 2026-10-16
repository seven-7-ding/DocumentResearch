import {CloudStore,session,emptyAnnotation,validate,Conflict} from './sync.js';
const $=s=>document.querySelector(s);
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const SIZE=12;
const titleOrder=new Intl.Collator('en',{sensitivity:'base',numeric:true,ignorePunctuation:true});
export function sortPapers(rows,field='added',direction='desc',saved={}){
  if(!['added','published','rating','title'].includes(field))field='added';
  const sign=direction==='asc'?1:-1;
  const value=p=>field==='rating'?(saved[p.id]?.rating??null):(p[field]?.trim()||null);
  return [...rows].sort((a,b)=>{
    const x=value(a),y=value(b);
    // Missing dates/titles and unrated entries stay last in either direction.
    if(x===null&&y!==null)return 1;if(y===null&&x!==null)return -1;
    const order=x===null?0:field==='rating'?x-y:field==='title'?titleOrder.compare(x,y):x<y?-1:x>y?1:0;
    return sign*order||titleOrder.compare(a.title||'',b.title||'')||String(a.id).localeCompare(String(b.id),'en');
  });
}
function sortLabels(){
  const labels={added:['升序 · 最早加入','降序 · 最新加入'],published:['升序 · 最早发表','降序 · 最新发表'],rating:['升序 · 低分优先','降序 · 高分优先'],title:['升序 · A → Z','降序 · Z → A']}[$('#sort-field').value];
  [...$('#sort-direction').options].forEach((option,i)=>option.textContent=labels[i]);
}
const MULTI=['author','first_author','last_author','institution','venue','tag','type'];
const widgets=new Map();
const list=v=>Array.isArray(v)?v.filter(Boolean):v?[v]:[];
const includes=(v,q)=>!q||String(v).toLocaleLowerCase().includes(q.trim().toLocaleLowerCase());
export function colorFor(value){let hash=2166136261;for(const c of value.normalize('NFC'))hash=Math.imul(hash^c.codePointAt(0),16777619);return (hash>>>0)%8;}
function highlighted(text,terms=[],whole=false){
  const fragment=document.createDocumentFragment(),value=String(text),ranges=[];
  if(whole&&value)ranges.push([0,value.length]);
  for(const term of list(terms).map(t=>t.trim()).filter(Boolean)){
    const escaped=term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    for(const match of value.matchAll(new RegExp(escaped,'giu')))ranges.push([match.index,match.index+match[0].length]);
  }
  ranges.sort((a,b)=>a[0]-b[0]);const merged=[];
  for(const range of ranges){const last=merged.at(-1);if(last&&range[0]<=last[1])last[1]=Math.max(last[1],range[1]);else merged.push([...range]);}
  let cursor=0;for(const [start,end] of merged){fragment.append(document.createTextNode(value.slice(cursor,start)),node('mark',value.slice(start,end)));cursor=end;}
  fragment.append(document.createTextNode(value.slice(cursor)));return fragment;
}
function marked(tag,text,cls,terms=[],whole=false){const e=node(tag,undefined,cls);e.append(highlighted(text,terms,whole));return e;}
let papers=[],page=1,cloud=null,auth=null,annotations={},editing=null,editBase=null,pending={},syncing=false;
const filters=$('#filters');
function notice(text){$('#notice').textContent=text;$('#notice').hidden=!text;}
async function data(url){const r=await fetch(url,{cache:'no-cache',signal:AbortSignal.timeout(25000)});if(!r.ok)throw new Error('目录暂时无法载入，请刷新重试。');return r.json();}
function chips(values,kind='',chosen=[]){const e=node('div',undefined,'chips');for(const v of values)e.append(marked('span',v,'chip '+kind+' tone-'+colorFor(v),[],chosen.includes(v)));return e;}
function filterValues(){const data=new FormData(filters),f=Object.fromEntries(data);for(const key of MULTI)f[key]=data.getAll(key);return f;}
function options(select,values){const selected=[...select.selectedOptions].map(o=>o.value);select.replaceChildren();for(const v of [...new Set([...values,...selected].filter(Boolean))].sort((a,b)=>a.localeCompare(b)))select.add(new Option(v,v,false,selected.includes(v)));widgets.get(select)?.refresh();}
function multiSelect(select){
  const title=select.dataset.label,details=node('details',undefined,'multi-select'),summary=node('summary'),panel=node('div',undefined,'multi-menu');
  const search=node('input'),choices=node('div',undefined,'multi-options'),clear=node('button','清除此项','multi-clear'),more=node('button','显示更多','multi-more');
  search.type='search';search.placeholder='搜索'+title;search.setAttribute('aria-label','搜索'+title+'选项');clear.type=more.type='button';
  let limit=80;
  function refresh(){
    const selected=[...select.selectedOptions].map(o=>o.value);summary.textContent=selected.length?selected.slice(0,2).join('、')+(selected.length>2?' 等 '+selected.length+' 项':''):'全部';summary.title=selected.join('、');summary.setAttribute('aria-label',title+'：'+(selected.length?selected.length+'项已选':'全部'));
    const rows=[...select.options].filter(o=>includes(o.value,search.value)).sort((a,b)=>Number(b.selected)-Number(a.selected));choices.replaceChildren();
    for(const option of rows.slice(0,limit)){
      const label=node('label',undefined,'multi-option'),check=node('input');check.type='checkbox';check.checked=option.selected;check.value=option.value;
      const text=marked('span',option.value,select.name==='tag'?'chip tone-'+colorFor(option.value):'',search.value?[search.value]:[]);
      check.addEventListener('change',()=>{option.selected=check.checked;const cursor=check.value;refresh();[...choices.querySelectorAll('input')].find(e=>e.value===cursor)?.focus();select.dispatchEvent(new Event('input',{bubbles:true}));});
      label.append(check,text);choices.append(label);
    }
    if(!rows.length)choices.append(node('p','没有匹配项','hint'));
    more.hidden=rows.length<=limit;more.textContent='显示更多（'+Math.min(limit,rows.length)+' / '+rows.length+'）';clear.disabled=!selected.length;
  }
  search.addEventListener('input',e=>{e.stopPropagation();limit=80;refresh();});
  choices.addEventListener('input',e=>e.stopPropagation());
  clear.onclick=()=>{for(const o of select.options)o.selected=false;refresh();select.dispatchEvent(new Event('input',{bubbles:true}));};
  more.onclick=()=>{limit+=80;refresh();};
  details.addEventListener('toggle',()=>{if(details.open)for(const other of widgets.values())if(other.details!==details)other.details.open=false;});
  details.addEventListener('keydown',e=>{if(e.key==='Escape'){details.open=false;summary.focus();}});
  panel.append(search,clear,choices,more);details.append(summary,panel);select.after(details);select.hidden=true;
  widgets.set(select,{details,refresh,reset:()=>{search.value='';limit=80;details.open=false;refresh();}});refresh();
}
function tagOptions(){options(filters.elements.tag,Object.values(annotations).flatMap(a=>a.tags||[]));}
export function matches(p,f,a=emptyAnnotation()){
  if(!includes(p.title+' '+(p.title_zh||''),f.title)||!includes(p.authors.join(' '),f.author_query))return false;
  for(const k of ['first_author','last_author','venue','type'])if(list(f[k]).length&&!list(f[k]).includes(p[k]))return false;
  for(const [k,values] of [['author',p.authors],['institution',p.institutions],['tag',a.tags]])if(list(f[k]).length&&!list(f[k]).some(v=>values.includes(v)))return false;
  if(f.unrated==='only'&&a.rating!==null)return false;
  if((f.rating_min||f.rating_max)&&(a.rating===null||f.rating_min&&a.rating<Number(f.rating_min)||f.rating_max&&a.rating>Number(f.rating_max)))return false;
  for(const key of ['published','added']){
    const d=(p[key]||'').slice(0,10),lo=f[key+'_from'],hi=f[key+'_to'];
    let start=d,end=d;
    if(/^\d{4}$/.test(d)){start=d+'-01-01';end=d+'-12-31';}
    else if(/^\d{4}-\d{2}$/.test(d)){start=d+'-01';end=d+'-'+new Date(Number(d.slice(0,4)),Number(d.slice(5)),0).getDate();}
    if((lo||hi)&&!d||lo&&end<lo||hi&&start>hi)return false;
  }return true;
}
function render(){
  const f=filterValues(), filtered=sortPapers(papers.filter(p=>matches(p,f,annotations[p.id]||emptyAnnotation())),$('#sort-field').value,$('#sort-direction').value,annotations);
  const pages=Math.max(1,Math.ceil(filtered.length/SIZE));page=Math.min(page,pages);
  $('#result-count').textContent=filtered.length+' / '+papers.length+' 篇';
  const active=Object.entries(f).filter(([k,v])=>list(v).length&&k!=='title'&&k!=='author_query').length;
  $('#active-filters').textContent=active?'· '+active+' 项':'';
  const target=$('#papers');target.replaceChildren();
  for(const p of filtered.slice((page-1)*SIZE,page*SIZE)){
    const a=annotations[p.id]||emptyAnnotation(),card=node('article',undefined,'paper-card card');card.dataset.paperId=p.id;
    const type=node('div',undefined,'type-line');type.append(marked('span',p.type,'type',[],f.type.includes(p.type)),node('span','·'));
    const venue=marked('span',p.venue,'venue',[],f.venue.includes(p.venue));venue.title=p.venue;type.append(venue);card.append(type);
    const h=node('h3'),link=marked('a',p.title,'paper-link',f.title?[f.title]:[]);link.href=p.pdf_url;link.target='_blank';link.rel='noopener noreferrer';link.title='打开论文 PDF';h.append(link);card.append(h);
    if(f.title&&p.title_zh&&includes(p.title_zh,f.title))card.append(marked('p',p.title_zh,'title-zh',[f.title]));
    const authors=node('p',undefined,'authors');authors.title=p.authors.join(', ');
    p.authors.forEach((author,i)=>{if(i)authors.append(document.createTextNode(', '));authors.append(highlighted(author,f.author_query?[f.author_query]:[],f.author.includes(author)||(i===0&&f.first_author.includes(author))||(i===p.authors.length-1&&f.last_author.includes(author))));});
    if(!p.authors.length)authors.textContent='作者未注明';if(authors.querySelector('mark'))authors.classList.add('has-match');card.append(authors);
    if(p.institutions.length){const institutions=node('p',undefined,'institutions');p.institutions.forEach((v,i)=>{if(i)institutions.append(document.createTextNode(' · '));institutions.append(highlighted(v,[],f.institution.includes(v)));});institutions.title=institutions.textContent;if(institutions.querySelector('mark'))institutions.classList.add('has-match');card.append(institutions);}
    if(a.tags.length)card.append(chips(a.tags,'user',f.tag));
    if(a.notes)card.append(node('p',a.notes,'note-preview'));
    const dates=node('div',undefined,'dates');const published=marked('span','发表 '+(p.published?.slice(0,10)||'未注明')+(p.version?' · '+p.version:''),'',[],!!(f.published_from||f.published_to));published.title=p.version_verified?'已核对最新版本':'采用原始收录记录；最新版本日期尚未核实';dates.append(published,marked('span','入库 '+(p.added?.slice(0,10)||'未注明'),'',[],!!(f.added_from||f.added_to)));card.append(dates);
    const bottom=node('div',undefined,'paper-bottom');
    const links=node('div',undefined,'paper-actions');
    for(const [label,url] of [[p.pdf_url?'PDF':'原文',p.pdf_url||p.url],['精读报告',p.reading_url]]){
      if(!url)continue;const a=node('a',label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';links.append(a);
    }
    if(!p.reading_url)links.append(node('span','暂无精读报告','hint'));
    card.append(links);
    bottom.append(marked('span',a.rating?'★'.repeat(a.rating)+'☆'.repeat(5-a.rating):'未评分',a.rating?'stars':'unrated',[],!!(f.rating_min||f.rating_max||f.unrated)));
    const edit=node('button',a.notes?'编辑笔记':'添加笔记','edit-button');edit.type='button';edit.addEventListener('click',()=>openEditor(p));bottom.append(edit);card.append(bottom);target.append(card);
  }
  if(!filtered.length)target.append(node('p','没有符合条件的论文','empty'));
  $('#page-label').textContent=page+' / '+pages;$('#prev').disabled=page<=1;$('#next').disabled=page>=pages;
}
function openEditor(p){
  if(!cloud){notice('云端尚未连接，请稍后重试。');return;}
  editing=p;editBase=structuredClone(cloud.items[p.id]||emptyAnnotation());
  const a=pending[p.id]?.value||annotations[p.id]||emptyAnnotation();
  if(pending[p.id])editBase=pending[p.id].base;
  $('#edit-title').textContent=p.title;$('#edit-tags').value=a.tags.join('，');$('#edit-rating').value=a.rating||'';$('#edit-notes').value=a.notes;
  $('#edit-status').textContent=pending[p.id]?.conflict?'云端有不同版本。当前未同步草稿仍保留；请复制后关闭并刷新云端笔记，再合并。':'';
  $('#editor').showModal();
}
function queueKey(){return 'document-research:pending:'+auth.sub;}
function persist(){localStorage.setItem(queueKey(),JSON.stringify(pending));}
function status(text){$('#sync-status').textContent=text;}
async function sync(){
  if(!cloud||syncing||cloud.busy)return;syncing=true;
  try{
    status('同步中…');await cloud.pull();
    for(const [id,entry] of Object.entries(pending)){
      if(entry.conflict)continue;
      try{await cloud.save(id,entry.value,entry.base);delete pending[id];persist();}
      catch(e){if(e instanceof Conflict){entry.conflict=true;persist();}else throw e;}
    }
    annotations={...cloud.items};
    for(const [id,entry] of Object.entries(pending))annotations[id]=entry.value;
    const conflicts=Object.values(pending).some(e=>e.conflict);
    status(conflicts?'有笔记需要合并':Object.keys(pending).length?'待同步':auth.user+' · 已同步');
    if(conflicts)notice('另一台设备修改了同一篇笔记。打开该篇笔记可查看未同步草稿；请先复制保留，再点击下方“使用云端版本”后合并。');
    tagOptions();render();
  }catch(e){status(navigator.onLine?'同步失败 · 将重试':'离线 · 待同步');notice(e.message);}
  finally{syncing=false;}
}
async function reports(){
  const months=await data('catalog/months.json');
  $('#month').replaceChildren(new Option('最近汇报','recent'));
  for(const m of months)$('#month').add(new Option(m,m));
  let generation=0;
  async function show(){
    const ticket=++generation;$('#reports').textContent='正在载入汇报…';
    try{
      let rows=[];
      if($('#month').value==='recent'){for(const m of months){rows.push(...await data('catalog/'+m+'.json'));if(rows.length>=6)break;}rows=rows.slice(0,6);}
      else rows=await data('catalog/'+$('#month').value+'.json');
      if(ticket!==generation)return;
      $('#reports').replaceChildren();
      for(const r of rows){
        const card=node('a',undefined,'report-card card');card.href=r.url;
        const date=node('div',r.date,'report-date');date.append(node('span','↗'));card.append(date);
        const stats=node('div',undefined,'report-stats');
        for(const [v,t] of [[r.paper_count??'—','篇论文'],[r.deep_count??'—','篇精读']]){const s=node('span');s.append(node('b',v),document.createTextNode(t));stats.append(s);}
        card.append(stats,chips((r.topics||[]).slice(0,4)));$('#reports').append(card);
      }
    }catch(e){$('#reports').textContent=e.message;}
  }$('#month').addEventListener('change',show);await show();
}
async function library(){
  const manifest=await data('library/manifest.json'),queue=[...manifest.shards],rows=[];
  await Promise.all(Array.from({length:4},async()=>{while(queue.length){const shard=queue.shift();rows.push(...await data(shard.url));}}));
  if(rows.length!==manifest.count)throw new Error('目录更新中，请刷新重试。');
  papers=rows;
  $('#total').textContent=papers.length+' 篇';
  for(const key of ['first_author','last_author','venue','type'])options(filters.elements[key],papers.map(p=>p[key]));
  options(filters.elements.institution,papers.flatMap(p=>p.institutions));
  options(filters.elements.author,papers.flatMap(p=>p.authors));
  // Datalists are suggestions, not rendered paper cards. Search always covers the full library.
  for(const [id,values] of [['titles',papers.map(p=>p.title)],['authors',papers.flatMap(p=>p.authors)]]){
    const list=$('#'+id);for(const v of [...new Set(values)])list.append(new Option(v,v));
  }render();
}
for(const select of filters.querySelectorAll('select[multiple]'))multiSelect(select);
document.addEventListener('click',e=>{for(const widget of widgets.values())if(!widget.details.contains(e.target))widget.details.open=false;});
filters.addEventListener('submit',e=>e.preventDefault());
filters.addEventListener('input',()=>{page=1;render();});
filters.addEventListener('reset',()=>{queueMicrotask(()=>{page=1;for(const widget of widgets.values())widget.reset();render();});});
for(const id of ['#sort-field','#sort-direction'])$(id).addEventListener('change',()=>{page=1;sortLabels();render();});
$('#prev').onclick=()=>{page--;render();$('#library').scrollIntoView();};$('#next').onclick=()=>{page++;render();$('#library').scrollIntoView();};
$('#close-editor').onclick=()=>$('#editor').close();
const manage=node('button','笔记管理');manage.hidden=true;$('.account').append(manage);
const manager=node('dialog');const managerTitle=node('h2','笔记管理');const backup=node('button','导出笔记');const compact=node('button','整理历史');const closeManager=node('button','关闭');const managerStatus=node('p',undefined,'hint');manager.append(managerTitle,managerStatus,backup,compact,closeManager);document.body.append(manager);
manage.onclick=()=>{managerStatus.textContent='已同步笔记 '+Object.keys(cloud.items).length+' 篇';manager.showModal();};closeManager.onclick=()=>manager.close();
backup.onclick=()=>{const blob=new Blob([JSON.stringify({schema:1,exported_at:new Date().toISOString(),notes:cloud.items,pending},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='reading-notes-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
compact.onclick=async()=>{if(!confirm('保留所有当前笔记，删除云端旧版本历史。建议先导出备份。是否继续？'))return;compact.disabled=true;try{await cloud.compact();managerStatus.textContent='历史已整理，当前笔记完整保留。';}catch(e){managerStatus.textContent=e.message;}finally{compact.disabled=false;}};
$('#annotation-form').onsubmit=async e=>{
  e.preventDefault();if(!cloud||!editing)return;
  try{
    const value=validate({tags:$('#edit-tags').value.split(/[,，\n]/).map(t=>t.trim()).filter(Boolean),rating:Number($('#edit-rating').value)||null,notes:$('#edit-notes').value});
    pending[editing.id]={value,base:editBase};persist();annotations[editing.id]=value;render();
    $('#edit-status').textContent='正在同步…';$('#save').disabled=true;
    await sync();
    $('#edit-status').textContent=pending[editing.id]?'草稿已保存在此设备，尚未同步。':'已同步';
    if(!pending[editing.id])$('#editor').close();
  }catch(error){$('#edit-status').textContent=error.message;}finally{$('#save').disabled=false;}
};
const remoteButton=node('button','使用云端版本','subtle');remoteButton.type='button';remoteButton.hidden=true;
$('.dialog-actions').prepend(remoteButton);
remoteButton.onclick=()=>{if(editing&&pending[editing.id]?.conflict){delete pending[editing.id];persist();annotations={...cloud.items};$('#editor').close();openEditor(editing);remoteButton.hidden=true;notice('');render();}};
new MutationObserver(()=>{remoteButton.hidden=!editing||!pending[editing.id]?.conflict;}).observe($('#edit-status'),{childList:true});
window.addEventListener('online',sync);window.addEventListener('focus',sync);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
// Saving/focus/online events still synchronize immediately; passive checks are sparse.
setInterval(()=>{if(!document.hidden)sync();},300000);
await Promise.allSettled([reports(),library().catch(e=>{notice(e.message);$('#papers').textContent='图书馆载入失败';})]);
try{
  auth=await session();
  if(auth){
    cloud=new CloudStore(auth);status('连接云端…');
    pending=JSON.parse(localStorage.getItem(queueKey())||'{}');
    manage.hidden=false;await sync();
  }
}catch(e){status('云端未连接');notice(e.message);}
