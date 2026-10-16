// Browser-only failure-path fixture. Never included in the publication allowlist.
(() => {
  const original=window.fetch.bind(window);
  sessionStorage.setItem('document-research:session:v1',JSON.stringify({token:'not-a-real-token',user:'portal-qa',sub:'portal-qa',expires:Date.now()+3600000}));
  window.__testOffline=false;
  window.fetch=async (url,options={})=>{
    if(!String(url).startsWith('https://huggingface.co/'))return original(url,options);
    if(window.__testOffline)throw new TypeError('Synthetic network outage');
    const db=JSON.parse(localStorage.getItem('mock-hf-db')||'{"head":"initial","files":{}}');
    const answer=(body,status=200)=>Promise.resolve(new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}}));
    if(String(url).includes('/commit/main')){
      const lines=options.body.trim().split('\n').map(JSON.parse);
      if(lines[0].value.parentCommit!==db.head)return answer({},409);
      for(const line of lines.slice(1)){const bytes=Uint8Array.from(atob(line.value.content),c=>c.charCodeAt(0));db.files[line.value.path]=JSON.parse(new TextDecoder().decode(bytes));}
      db.head=crypto.randomUUID();localStorage.setItem('mock-hf-db',JSON.stringify(db));return answer({commitOid:db.head});
    }
    if(String(url).includes('/resolve/')){const path=String(url).split('/resolve/')[1].split('/').slice(1).join('/');return path in db.files?answer(db.files[path]):answer({},404);}
    if(String(url).includes('/api/datasets/'))return answer({private:true,sha:db.head});
    throw new Error('Unexpected mocked HF request');
  };
})();
