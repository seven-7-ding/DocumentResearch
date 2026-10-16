/* The private HF Space authenticates access. Secrets stay on the backend. */
export const emptyAnnotation=()=>({tags:[],notes:'',rating:null});
export class Conflict extends Error {constructor(remote){super('这篇笔记已在另一台设备修改，请保留草稿并合并。');this.remote=remote;}}
export function validate(value){
  if(!value||!Array.isArray(value.tags)||value.tags.length>20||value.tags.some(t=>typeof t!=='string'||t.length>40)||typeof value.notes!=='string'||value.notes.length>10000||!(value.rating===null||Number.isInteger(value.rating)&&value.rating>=1&&value.rating<=5))throw new Error('标签最多20个、每个40字，笔记最多10000字，评分为1至5。');
  return {tags:[...new Set(value.tags.map(t=>t.trim()).filter(Boolean))],notes:value.notes,rating:value.rating};
}
export async function request(url,options={}){
  const response=await fetch(url,{...options,cache:'no-store',signal:AbortSignal.timeout(90000)});
  let body;try{body=await response.json();}catch{throw new Error('云端无法连接，请从 Hugging Face Space 入口重新打开。');}
  if(response.status===409&&body.remote)throw new Conflict(body.remote);
  if(!response.ok)throw new Error(body.error||'云端暂时无法连接，请稍后重试。');
  return body;
}
export const session=()=>request('/api/session');
export class CloudStore {
  constructor(auth,transport=request){this.auth=auth;this.transport=transport;this.items={};this.busy=false;this.meta={};}
  accept(result){this.items=result.items;this.meta=result.meta;this.head=result.head;return this.items;}
  async connect(){return this.pull();}
  async pull(){return this.accept(await this.transport('/api/annotations'));}
  async post(path,body){
    if(this.busy)throw new Error('正在同步，请稍后重试。');
    this.busy=true;
    try{return this.accept(await this.transport(path,{method:'POST',headers:{'Content-Type':'application/json','X-DocumentResearch':'1'},body:JSON.stringify(body)}));}
    finally{this.busy=false;}
  }
  async save(id,value,base){validate(value);validate(base);await this.post('/api/annotations',{id,value,base});return this.items[id];}
  async compact(){return this.post('/api/compact',{confirm:true});}
}
