/* HF OAuth PKCE + private Dataset. No deployment credential is shipped to browsers. */
const HUB='https://huggingface.co';
const CLIENT='https://seven-7-ding-documentresearch.static.hf.space/oauth-client.json';
const SESSION='document-research:session:v1';
const REPO_NAME='document-research-notes';
const jsonEqual=(a,b)=>JSON.stringify(a??null)===JSON.stringify(b??null);
const base64=bytes=>{let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text);};
const encoded=text=>base64(new TextEncoder().encode(text));
const bucket=id=>{let hash=2166136261;for(const c of id)hash=Math.imul(hash^c.codePointAt(0),16777619);return (hash>>>0).toString(16).slice(-1);};
export const emptyAnnotation=()=>({tags:[],notes:'',rating:null});
export class Conflict extends Error {constructor(remote){super('这篇笔记已在另一台设备修改。请保留当前文字，重新打开笔记后合并。');this.remote=remote;}}
export function validate(value){
  if(!value||!Array.isArray(value.tags)||value.tags.length>20||value.tags.some(t=>typeof t!=='string'||t.length>40)||typeof value.notes!=='string'||value.notes.length>10000||!(value.rating===null||Number.isInteger(value.rating)&&value.rating>=1&&value.rating<=5))throw new Error('标签最多20个、每个40字，笔记最多10000字，评分为1至5。');
  return {tags:[...new Set(value.tags.map(t=>t.trim()).filter(Boolean))],notes:value.notes,rating:value.rating};
}
export function mergeAnnotation(base,local,remote){
  const merged={...remote};
  for(const key of ['tags','notes','rating']){
    if(jsonEqual(local[key],base[key]))continue;
    if(!jsonEqual(remote[key],base[key])&&!jsonEqual(remote[key],local[key]))throw new Conflict(remote);
    merged[key]=local[key];
  }
  return validate(merged);
}
export async function request(url,options={}){
  const response=await fetch(url,{...options,signal:AbortSignal.timeout(25000)});
  if(!response.ok){const error=new Error(response.status===401?'登录已过期，请重新登录。':response.status===403?'云端权限不足，请重新登录并授权。':`云端请求失败（${response.status}），请稍后重试。`);error.status=response.status;throw error;}
  return response.status===204?null:response.json();
}
export async function login(){
  // In HF's embedded viewer, use a top-level window to keep storage/PKCE in one context.
  if(window.top!==window.self){window.open(location.origin+'/?login=1','_blank','noopener');return;}
  const redirect=location.origin+location.pathname;
  const verifier=crypto.randomUUID()+crypto.randomUUID(), state=crypto.randomUUID();
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
  sessionStorage.setItem('document-research:pkce',JSON.stringify({verifier,state,redirect,at:Date.now()}));
  const params=new URLSearchParams({client_id:CLIENT,response_type:'code',scope:'openid profile contribute-repos',redirect_uri:redirect,state,code_challenge:base64(new Uint8Array(digest)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,''),code_challenge_method:'S256'});
  location.assign(HUB+'/oauth/authorize?'+params);
}
export async function session(){
  const params=new URLSearchParams(location.search);
  if(params.has('error')){history.replaceState(null,'',location.pathname);throw new Error('未完成登录，请重试。');}
  if(params.has('code')){
    const saved=JSON.parse(sessionStorage.getItem('document-research:pkce')||'null');
    history.replaceState(null,'',location.pathname);
    if(!saved||saved.state!==params.get('state')||Date.now()-saved.at>600000||saved.redirect!==location.origin+location.pathname)throw new Error('登录验证已失效，请重新登录。');
    sessionStorage.removeItem('document-research:pkce');
    const token=await request(HUB+'/oauth/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:CLIENT,grant_type:'authorization_code',code:params.get('code'),code_verifier:saved.verifier,redirect_uri:saved.redirect})});
    const user=await request(HUB+'/oauth/userinfo',{headers:{Authorization:'Bearer '+token.access_token}});
    const result={token:token.access_token,expires:Date.now()+token.expires_in*1000,user:user.preferred_username,sub:user.sub};
    sessionStorage.setItem(SESSION,JSON.stringify(result));return result;
  }
  const result=JSON.parse(sessionStorage.getItem(SESSION)||'null');
  if(result?.expires>Date.now()+30000)return result;
  sessionStorage.removeItem(SESSION);return null;
}
export function logout(){sessionStorage.removeItem(SESSION);}

export class CloudStore {
  constructor(auth,transport=request){this.auth=auth;this.transport=transport;this.repo=auth.user+'/'+REPO_NAME;this.items={};this.head=null;this.busy=false;}
  call(path,options={}){return this.transport(HUB+path,{...options,headers:{Authorization:'Bearer '+this.auth.token,...options.headers},cache:'no-store'});}
  async connect(){
    let info;
    try{info=await this.call('/api/datasets/'+this.repo);}
    catch(e){if(e.status!==404&&e.status!==401)throw e;
      // The scoped OAuth app creates this private repo, enabling contribute-repos access.
      try{await this.call('/api/repos/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'dataset',name:REPO_NAME,private:true})});}
      catch(createError){if(createError.status!==409)throw createError;}
      info=await this.call('/api/datasets/'+this.repo);
    }
    if(info.private!==true)throw new Error('笔记仓库必须为私有；已停止同步。');
    await this.pull(info);return this.items;
  }
  async pull(info){
    info??=await this.call('/api/datasets/'+this.repo);
    if(info.private!==true)throw new Error('笔记仓库不是私有，已停止同步。');
    if(info.sha===this.head)return this.items;
    let doc={schema:2,buckets:[],writes:0,history_bytes:0};
    // Pin reads to the inspected revision: a concurrent write cannot mix head and data.
    if(info.sha)try{doc=await this.call('/datasets/'+this.repo+'/resolve/'+info.sha+'/annotations.json');}catch(e){if(e.status!==404)throw e;}
    this.legacy=doc.schema===1&&doc.items&&typeof doc.items==='object';
    if(!this.legacy&&(doc.schema!==2||!Array.isArray(doc.buckets)||doc.buckets.length>16||doc.buckets.some(b=>!/^notes\/[0-9a-f]\.json$/.test(b))))throw new Error('云端笔记格式异常，已停止同步。');
    const items=this.legacy?doc.items:{};const queue=[...(doc.buckets||[])];
    await Promise.all(Array.from({length:4},async()=>{while(queue.length){const path=queue.shift();Object.assign(items,await this.call('/datasets/'+this.repo+'/resolve/'+info.sha+'/'+path));}}));
    if(new TextEncoder().encode(JSON.stringify(items)).length>2000000)throw new Error('云端笔记容量异常，已停止同步。');
    for(const [id,value] of Object.entries(items)){if(id.length>180)throw new Error('无效论文标识');validate(value);}
    this.items=items;this.head=info.sha;this.meta=doc;this.writes=doc.writes||0;return this.items;
  }
  async save(id,value,base){
    validate(value);if(typeof id!=='string'||id.length>180)throw new Error('无效论文标识');
    if(this.busy)throw new Error('正在同步，请稍后重试。');
    this.busy=true;
    try{
      for(let attempt=0;attempt<3;attempt++){
        await this.pull();
        const remote=this.items[id]||emptyAnnotation(), merged=mergeAnnotation(base,value,remote);
        if(jsonEqual(validate(remote),merged))return remote;
        const item={...merged,updated_at:new Date().toISOString()};
        const items={...this.items,[id]:item};
        if(new TextEncoder().encode(JSON.stringify(items)).length>2000000)throw new Error('笔记总量已达2MB，请先导出并整理。');
        const parts=this.legacy?[...new Set(Object.keys(items).map(bucket))]:[bucket(id)];
        const files=parts.map(part=>({path:'notes/'+part+'.json',content:JSON.stringify(Object.fromEntries(Object.entries(items).filter(([key])=>bucket(key)===part)))}));
        const doc={schema:2,writes:this.writes+1,buckets:[...new Set([...(this.meta?.buckets||[]),...files.map(f=>f.path)])].sort(),history_bytes:(this.meta?.history_bytes||0)+files.reduce((sum,f)=>sum+new TextEncoder().encode(f.content).length,512)};
        if(doc.history_bytes>100000000)throw new Error('笔记历史达到维护阈值，请先导出备份，并在私有Dataset设置中压缩历史。');
        const lines=[{key:'header',value:{summary:'Update reading notes',...(this.head?{parentCommit:this.head}:{})}},...files.map(f=>({key:'file',value:{path:f.path,content:encoded(f.content),encoding:'base64'}})),{key:'file',value:{path:'annotations.json',content:encoded(JSON.stringify(doc)),encoding:'base64'}}];
        try{
          await this.call('/api/datasets/'+this.repo+'/commit/main',{method:'POST',headers:{'Content-Type':'application/x-ndjson'},body:lines.map(JSON.stringify).join('\n')+'\n'});
          this.head=null;await this.pull();return this.items[id];
        }catch(e){if(e.status!==409&&e.status!==412)throw e;}
      }
      throw new Error('另一台设备正在频繁更新，请稍后重试。');
    }finally{this.busy=false;}
  }
  async compact(){
    if(this.busy)throw new Error('请等待当前同步完成。');
    this.busy=true;
    try{
      await this.pull();
      // Server squashes its current head atomically; never force-push a stale local snapshot.
      const response=await fetch(HUB+'/api/datasets/'+this.repo+'/super-squash/main',{method:'POST',headers:{Authorization:'Bearer '+this.auth.token,'Content-Type':'application/json'},body:JSON.stringify({message:'Compact reading-note history; retain current notes'}),signal:AbortSignal.timeout(25000)});
      if(!response.ok)throw new Error('历史整理失败（'+response.status+'），当前笔记仍保留。');
      for(let attempt=0;attempt<3;attempt++){
        this.head=null;await this.pull();
        const doc={...this.meta,history_bytes:0};
        const lines=[{key:'header',value:{summary:'Reset note history budget',parentCommit:this.head}},{key:'file',value:{path:'annotations.json',content:encoded(JSON.stringify(doc)),encoding:'base64'}}];
        try{await this.call('/api/datasets/'+this.repo+'/commit/main',{method:'POST',headers:{'Content-Type':'application/x-ndjson'},body:lines.map(JSON.stringify).join('\n')+'\n'});this.head=null;await this.pull();return;}
        catch(e){if(e.status!==409&&e.status!==412)throw e;}
      }throw new Error('另一台设备正在更新，整理后请重试。');
    }finally{this.busy=false;}
  }
}
