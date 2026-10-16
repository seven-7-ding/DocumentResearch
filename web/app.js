import {CloudStore,session,emptyAnnotation,validate,Conflict} from './sync.js';
const $=s=>document.querySelector(s);
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const SIZE=12;
let papers=[],page=1,cloud=null,auth=null,annotations={},editing=null,editBase=null,pending={},syncing=false;
const filters=$('#filters');
function notice(text){$('#notice').textContent=text;$('#notice').hidden=!text;}
async function data(url){const r=await fetch(url,{cache:'no-cache',signal:AbortSignal.timeout(25000)});if(!r.ok)throw new Error('目录暂时无法载入，请刷新重试。');return r.json();}
function chips(values,kind=''){const e=node('div',undefined,'chips');for(const v of values)e.append(node('span',v,'chip '+kind));return e;}
function options(select,values){const current=select.value;select.replaceChildren(new Option('全部',''));for(const v of [...new Set(values.filter(Boolean))].sort((a,b)=>a.localeCompare(b)))select.add(new Option(v,v));select.value=current;}
function tagOptions(){options(filters.elements.tag,Object.values(annotations).flatMap(a=>a.tags||[]));}
export function matches(p,f,a=emptyAnnotation()){
  const contains=(v,q)=>!q||String(v).toLocaleLowerCase().includes(q.trim().toLocaleLowerCase());
  if(!contains(p.title+' '+p.title_zh,f.title)||!contains(p.authors.join(' '),f.author))return false;
  for(const k of ['first_author','last_author','venue','type'])if(f[k]&&p[k]!==f[k])return false;
  if(f.institution&&!p.institutions.includes(f.institution))return false;
  if(f.tag&&!a.tags.includes(f.tag))return false;
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
  const f=Object.fromEntries(new FormData(filters)), filtered=papers.filter(p=>matches(p,f,annotations[p.id]||emptyAnnotation()));
  const pages=Math.max(1,Math.ceil(filtered.length/SIZE));page=Math.min(page,pages);
  $('#result-count').textContent=filtered.length+' / '+papers.length+' 篇';
  const active=Object.entries(f).filter(([k,v])=>v&&k!=='title'&&k!=='author').length;
  $('#active-filters').textContent=active?'· '+active+' 项':'';
  const target=$('#papers');target.replaceChildren();
  for(const p of filtered.slice((page-1)*SIZE,page*SIZE)){
    const a=annotations[p.id]||emptyAnnotation(),card=node('article',undefined,'paper-card card');
    const type=node('div',undefined,'type-line');type.append(node('span',p.type,'type'),node('span','·'));
    const venue=node('span',p.venue,'venue');venue.title=p.venue;type.append(venue);card.append(type);
    const h=node('h3'),link=node('a',p.title,'paper-link');link.href=p.pdf_url;link.target='_blank';link.rel='noopener noreferrer';link.title='打开论文 PDF';h.append(link);card.append(h);
    const authors=node('p',p.authors.join(', ')||'作者未注明','authors');authors.title=p.authors.join(', ');card.append(authors);
    if(p.institutions.length){const institutions=node('p',p.institutions.join(' · '),'institutions');institutions.title=institutions.textContent;card.append(institutions);}
    if(a.tags.length)card.append(chips(a.tags,'user'));
    if(a.notes)card.append(node('p',a.notes,'note-preview'));
    const dates=node('div',undefined,'dates');const published=node('span','发表 '+(p.published?.slice(0,10)||'未注明')+(p.version?' · '+p.version:''));published.title=p.version_verified?'已核对最新版本':'采用原始收录记录；最新版本日期尚未核实';dates.append(published,node('span','入库 '+(p.added?.slice(0,10)||'未注明')));card.append(dates);
    const bottom=node('div',undefined,'paper-bottom');
    const links=node('div',undefined,'paper-actions');
    for(const [label,url] of [[p.pdf_url?'PDF':'原文',p.pdf_url||p.url],['精读报告',p.reading_url]]){
      if(!url)continue;const a=node('a',label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';links.append(a);
    }
    if(!p.reading_url)links.append(node('span','暂无精读报告','hint'));
    card.append(links);
    bottom.append(node('span',a.rating?'★'.repeat(a.rating)+'☆'.repeat(5-a.rating):'未评分',a.rating?'stars':'unrated'));
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
  papers=rows.sort((a,b)=>b.added.localeCompare(a.added)||a.title.localeCompare(b.title));
  $('#total').textContent=papers.length+' 篇';
  for(const key of ['first_author','last_author','venue','type'])options(filters.elements[key],papers.map(p=>p[key]));
  options(filters.elements.institution,papers.flatMap(p=>p.institutions));
  // Datalists are suggestions, not rendered paper cards. Search always covers the full library.
  for(const [id,values] of [['titles',papers.map(p=>p.title)],['authors',papers.flatMap(p=>p.authors)]]){
    const list=$('#'+id);for(const v of [...new Set(values)])list.append(new Option(v,v));
  }render();
}
filters.addEventListener('submit',e=>e.preventDefault());
filters.addEventListener('input',()=>{page=1;render();});
filters.addEventListener('reset',()=>{queueMicrotask(()=>{page=1;render();});});
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
setInterval(()=>{if(!document.hidden)sync();},60000);
await Promise.allSettled([reports(),library().catch(e=>{notice(e.message);$('#papers').textContent='图书馆载入失败';})]);
try{
  auth=await session();
  if(auth){
    cloud=new CloudStore(auth);status('连接云端…');
    pending=JSON.parse(localStorage.getItem(queueKey())||'{}');
    await cloud.connect();manage.hidden=false;await sync();
  }
}catch(e){status('云端未连接');notice(e.message);}
