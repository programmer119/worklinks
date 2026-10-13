import { AuthHubClient } from './authhub-client.js';

const API_BASE = 'https://api-suaveforge.suaveforge.com:18458/api/g2b';
const CALLBACK = 'https://worklinks.suaveforge.com/startup-support/auth-callback.html';
const GUEST = {
  applied: 'externaltools_startup_support_status_v1',
  hidden: 'worklinks_startup_support_hidden_v1',
  business: 'worklinks_startup_support_business_v1'
};
const KIND = {applied:true,hidden:true,business:true};
const GUEST_OWNER_KEY = 'worklinks_support_guest_migration_owner_v1';
const state = {client:null,token:'',account:'',project:'',busy:false,loading:false,serverReady:false,records:[],imported:0};
const $ = (id)=>document.getElementById(id);
const decode = (key)=>{try{const r=JSON.parse(localStorage.getItem(key)||'{}');return r&&typeof r==='object'&&!Array.isArray(r)?r:{}}catch{return {}}};
const accountKeys = (user)=>({
  applied:'worklinks_support_applied_v2:'+user,
  hidden:'worklinks_support_hidden_v2:'+user,
  business:'worklinks_support_business_v2:'+user,
  pending:'worklinks_support_pending_v2:'+user
});
function itemDetails(id){
  const entry=(window.items||[]).find(x=>x.id===id)||state.records.find(x=>x.id===id)||{};
  return {title:String(entry.title||'').slice(0,180),url:String(entry.url||'').slice(0,600)};
}
function show(message){
  const target=$('worklinks-auth-info');
  if(target)target.textContent=message;
}
async function api(path,options={}){
  const response=await fetch(API_BASE+path,{
    ...options,headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...(state.token?{Authorization:'Bearer '+state.token}:{}),...(options.headers||{})},
    cache:'no-store',signal:AbortSignal.timeout(12000)
  });
  const data=await response.json().catch(()=>({}));
  if(!response.ok||!data.ok)throw Error(data.error||'HTTP '+response.status);
  return data;
}
async function validSession(client){
  let session=client.session();
  if(!session?.accessToken)return null;
  try{
    let me;
    try{me=await client.me()}
    catch(error){
      if(error.status!==401)throw error;
      session=await client.refresh();
      me=await client.me();
    }
    if(me?.membership?.status!=='active'||!me?.user?.id)return null;
    return {token:session.accessToken,identity:String(me.user.id),email:String(me.user.email||'')};
  }catch(error){
    if(error.status===401){try{await client.logout()}catch{};return null}
    throw error;
  }
}
function applyAccount(records){
  const keys=accountKeys(state.account);
  const maps={applied:decode(keys.applied),hidden:decode(keys.hidden),business:decode(keys.business)};
  const pending=decode(keys.pending);
  for(const record of records){
    if(!record||!Object.prototype.hasOwnProperty.call(KIND,record.kind)||typeof record.id!=='string')continue;
    maps[record.kind][record.id]=record.value===true;
  }
  for(const entry of Object.values(pending)){
    if(entry&&maps[entry.kind])maps[entry.kind][entry.id]=entry.value===true;
  }
  Object.entries(maps).forEach(([kind,map])=>localStorage.setItem(keys[kind],JSON.stringify(map)));
  window.statusKey=keys.applied;window.hiddenKey=keys.hidden;window.businessKey=keys.business;
  window.saved=maps.applied;window.hidden=maps.hidden;window.business=maps.business;
  state.records=records;
  window.worklinksArchivedStatuses=records.filter(r=>r.kind==='applied'&&r.value===true);
  if(typeof window.draw==='function')window.draw();
}
async function flush(){
  // Never upload a guest import or claim sync before existing server data is read.
  if(!state.account||!state.serverReady||state.busy)return;
  const account=state.account, keys=accountKeys(account);
  state.busy=true;
  try{
    // Preserve every pending change until the API has acknowledged that exact value.
    // Bounded batches avoid a large legacy history requiring serial network calls.
    while(state.account===account){
      const batch=Object.entries(decode(keys.pending)).slice(0,4);
      if(!batch.length){
        show(state.imported
          ? 'AuthHub 로그인 · 비회원 기록 '+state.imported+'건 자동 이전 및 서버 저장 완료'
          : 'AuthHub 로그인 · 브라우저+서버 동기화');
        return;
      }
      const results=await Promise.all(batch.map(async ([key,entry])=>{
        try{
          await api('/worklinks-state',{method:'POST',body:JSON.stringify(entry)});
          return {key,entry,ok:true};
        }catch{return {key,entry,ok:false}}
      }));
      if(state.account!==account)return;
      let failed=false;
      const latest=decode(keys.pending);
      for(const r of results){
        if(!r.ok){failed=true;continue}
        // Never discard newer changes made while the request was in flight.
        if(JSON.stringify(latest[r.key])===JSON.stringify(r.entry))delete latest[r.key];
      }
      localStorage.setItem(keys.pending,JSON.stringify(latest));
      if(failed){
        show('비회원 기록·변경사항 브라우저에 보존됨 · 서버 동기화 재시도 대기');
        return;
      }
    }
  }finally{
    state.busy=false;
  }
}
function importGuestAutomatically(){
  if(!state.account)return 0;
  const guest={applied:decode(GUEST.applied),hidden:decode(GUEST.hidden),business:decode(GUEST.business)};
  const entries=Object.entries(guest).flatMap(([kind,map])=>
    Object.entries(map).filter(([,v])=>v===true).map(([id])=>({kind,id,value:true})));
  if(!entries.length)return 0;
  const owner=localStorage.getItem(GUEST_OWNER_KEY);
  // A guest history must never be silently copied into someone else's account.
  if(owner&&owner!==state.account){
    show('다른 계정에 귀속된 이전 비회원 기록은 자동으로 가져오지 않음');
    return 0;
  }
  if(!owner)localStorage.setItem(GUEST_OWNER_KEY,state.account);
  if(!state.serverReady)return 0;
  const keys=accountKeys(state.account);
  const maps={applied:decode(keys.applied),hidden:decode(keys.hidden),business:decode(keys.business)};
  const pending=decode(keys.pending);
  const migratedKey='worklinks_support_guest_migrated_v1:'+state.account;
  const migrated=decode(migratedKey);
  // False is an explicit member decision, not an empty value. Never resurrect it.
  const remote=new Set(state.records.map(r=>r.kind+':'+r.id));
  let imported=0;
  for(const entry of entries){
    if(!(/^[A-Za-z0-9_.:-]{1,160}$/.test(entry.id)))continue;
    const key=entry.kind+':'+entry.id;
    if(migrated[key])continue;
    const memberAlreadyHasValue=Object.prototype.hasOwnProperty.call(maps[entry.kind],entry.id);
    if(!remote.has(key)&&!Object.prototype.hasOwnProperty.call(pending,key)&&!memberAlreadyHasValue){
      pending[key]={...entry,...itemDetails(entry.id)};
      maps[entry.kind][entry.id]=true;
      imported++;
    }
    // An existing server value (including false) takes precedence; guest original remains intact.
    migrated[key]=true;
  }
  Object.entries(maps).forEach(([kind,map])=>localStorage.setItem(keys[kind],JSON.stringify(map)));
  localStorage.setItem(keys.pending,JSON.stringify(pending));
  localStorage.setItem(migratedKey,JSON.stringify(migrated));
  state.imported=imported;
  // Account-side maps + pending must be re-rendered before background upload.
  applyAccount(state.records);
  if(imported)show('비회원 기록 '+imported+'건 계정으로 자동 이전 중 · 서버 저장 진행');
  return imported;
}
window.worklinksStatusChanged=(kind,id,value)=>{
  if(!state.account||!Object.prototype.hasOwnProperty.call(KIND,kind))return;
  const keys=accountKeys(state.account);
  const item=itemDetails(id);
  const pending=decode(keys.pending);
  pending[kind+':'+id]={kind,id,value:!!value,...item};
  localStorage.setItem(keys.pending,JSON.stringify(pending));
  if(!state.serverReady)show('브라우저 기록 보존됨 · 서버 기록 확인 후 자동 동기화');
  flush().catch(()=>show('브라우저 저장됨 · 서버 동기화 대기'));
};
function guestRestore(){
  state.account='';state.token='';state.records=[];state.imported=0;state.serverReady=false;
  window.statusKey=GUEST.applied;window.hiddenKey=GUEST.hidden;window.businessKey=GUEST.business;
  window.saved=decode(GUEST.applied);window.hidden=decode(GUEST.hidden);window.business=decode(GUEST.business);
  window.worklinksArchivedStatuses=[];
  if(typeof window.draw==='function')window.draw();
}

async function reconcileServer(){
  if(!state.account||state.loading)return;
  const account=state.account;
  state.loading=true;
  try{
    const remote=await api('/worklinks-state');
    if(account!==state.account)return;
    if(!Array.isArray(remote.records))throw Error('invalid_server_records');
    state.serverReady=true;
    applyAccount(remote.records);
    importGuestAutomatically();
    await flush();
  }catch(error){
    if(account===state.account){
      state.serverReady=false;
      show('로그인됨 · 서버 기록 조회 실패, 브라우저 기록 보존 · 연결 복구 시 재시도');
    }
  }finally{state.loading=false;}
}
function hosted(mode){
  const u=new URL('https://authhub.suaveforge.com/login/');
  u.searchParams.set('project',state.project);
  u.searchParams.set('environment','production');
  u.searchParams.set('redirect_uri',CALLBACK);
  u.searchParams.set('state','/startup-support/');
  u.searchParams.set('mode',mode);
  return u.toString();
}
function buttons(session){
  const box=$('worklinks-auth-controls');if(!box)return;
  box.replaceChildren();
  if(session){
    const label=document.createElement('span');label.textContent=session.email||'AuthHub 회원';
    label.className='worklinks-auth-user';box.append(label);

    const logout=document.createElement('button');logout.type='button';logout.className='worklinks-auth-button';
    logout.textContent='로그아웃';logout.addEventListener('click',async()=>{
      try{await state.client.logout()}catch{}
      guestRestore();buttons(null);show('비회원 · 이 브라우저에만 저장');
    });box.append(logout);
  }else{
    for(const mode of ['login','signup']){
      const button=document.createElement('button');button.type='button';
      button.className='worklinks-auth-button';
      button.textContent=mode==='login'?'로그인':'회원가입';
      button.addEventListener('click',()=>location.assign(hosted(mode)));
      box.append(button);
    }
  }
}
async function bootstrap(){
  let config;
  try{config=await api('/worklinks-auth-config')}
  catch{show('비회원 · 브라우저 저장 (인증 서버 연결 대기)');return}
  state.project=config.project||'';
  if(!config.enabled){show('비회원 · 브라우저 저장 (AuthHub 프로젝트 등록 대기)');return}
  state.client=new AuthHubClient({apiBase:config.authApi,project:state.project,environment:'production'});
  if(document.body?.dataset.worklinksAuthCallback==='true'){
    try{
      const result=await state.client.consumeOAuthCallback(location.href);
      if(result?.pendingApproval)throw Error('가입 승인 대기');
      if(!result)throw Error('인증 코드 없음');
      location.replace('/startup-support/');
    }catch(error){
      const target=$('worklinks-callback-status');if(target)target.textContent='인증 완료 실패: '+String(error.message||error);
    }
    return;
  }
  try{
    const session=await validSession(state.client);
    if(!session){buttons(null);show('비회원 · 이 브라우저에만 저장');return}
    state.account=session.identity;state.token=session.token;state.serverReady=false;
    // Show preserved account-local data while waiting, but do not overwrite server truth.
    applyAccount([]);
    await reconcileServer();
    buttons(session);
  }catch(error){
    guestRestore();buttons(null);show('비회원 · 브라우저 저장 (AuthHub 확인 지연)');
  }
}
window.addEventListener('online',()=>{if(state.account){if(!state.serverReady)reconcileServer().catch(()=>{});else flush().catch(()=>{})}});
window.addEventListener('focus',()=>{if(!state.account)return;if(!state.serverReady)reconcileServer().catch(()=>{});else if(!state.busy&&Object.keys(decode(accountKeys(state.account).pending)).length)flush().catch(()=>{})});
bootstrap().catch(error=>{console.warn('WorkLinks AuthHub bootstrap',error);show('브라우저 저장 유지 · 인증 서버 확인 필요')});
