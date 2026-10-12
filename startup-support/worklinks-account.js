import { AuthHubClient } from './authhub-client.js';

const API_BASE = 'https://api-suaveforge.suaveforge.com:18458/api/g2b';
const CALLBACK = 'https://worklinks.suaveforge.com/startup-support/auth-callback.html';
const GUEST = {
  applied: 'externaltools_startup_support_status_v1',
  hidden: 'worklinks_startup_support_hidden_v1',
  business: 'worklinks_startup_support_business_v1'
};
const KIND = {applied:'saved',hidden:'hidden',business:'business'};
const state = {client:null,token:'',account:'',project:'',busy:false,records:[]};
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
  if(!state.account||state.busy)return;
  state.busy=true;
  const keys=accountKeys(state.account);
  try{
    const pending=decode(keys.pending);
    for(const key of Object.keys(pending)){
      const entry=pending[key];if(!entry)continue;
      try{
        await api('/worklinks-state',{method:'POST',body:JSON.stringify(entry)});
        const latest=decode(keys.pending);
        if(JSON.stringify(latest[key])===JSON.stringify(entry)){
          delete latest[key];localStorage.setItem(keys.pending,JSON.stringify(latest));
        }
      }catch(error){show('브라우저 저장됨 · 서버 동기화 대기');return}
    }
    show('AuthHub 로그인 · 브라우저+서버 동기화');
  }finally{state.busy=false}
}
window.worklinksStatusChanged=(kind,id,value)=>{
  if(!state.account||!Object.prototype.hasOwnProperty.call(KIND,kind))return;
  const keys=accountKeys(state.account);
  const item=itemDetails(id);
  const pending=decode(keys.pending);
  pending[kind+':'+id]={kind,id,value:!!value,...item};
  localStorage.setItem(keys.pending,JSON.stringify(pending));
  flush().catch(()=>show('브라우저 저장됨 · 서버 동기화 대기'));
};
function guestRestore(){
  state.account='';state.token='';state.records=[];
  window.statusKey=GUEST.applied;window.hiddenKey=GUEST.hidden;window.businessKey=GUEST.business;
  window.saved=decode(GUEST.applied);window.hidden=decode(GUEST.hidden);window.business=decode(GUEST.business);
  window.worklinksArchivedStatuses=[];
  if(typeof window.draw==='function')window.draw();
}
async function importGuest(){
  if(!state.account)return;
  const maps={applied:decode(GUEST.applied),hidden:decode(GUEST.hidden),business:decode(GUEST.business)};
  const keys=accountKeys(state.account);
  let count=0;
  for(const [kind,guestMap] of Object.entries(maps)){
    const current=decode(keys[kind]);
    for(const [id,value] of Object.entries(guestMap)){
      // Only import affirmative choices: old guest defaults may contain 'false'.
      if(value!==true||current[id]===true)continue;
      current[id]=true;count++;
      window.worklinksStatusChanged(kind,id,true);
    }
    localStorage.setItem(keys[kind],JSON.stringify(current));
  }
  applyAccount(state.records);
  show(count+'건 가져옴 · 서버 동기화 중');
  await flush();
  const b=$('worklinks-import');if(b)b.hidden=true;
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
    const importable=Object.values(GUEST).some(key=>Object.values(decode(key)).some(x=>x===true));
    if(importable){
      const merge=document.createElement('button');merge.type='button';merge.id='worklinks-import';
      merge.className='worklinks-auth-button';merge.textContent='이 브라우저 기록 가져오기';
      merge.addEventListener('click',()=>importGuest().catch(()=>show('가져오기 실패 · 브라우저 기록 유지')));
      box.append(merge);
    }
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
    state.account=session.identity;state.token=session.token;
    try{
      const remote=await api('/worklinks-state');
      applyAccount(remote.records||[]);
      show('AuthHub 로그인 · 브라우저+서버 동기화');
      await flush();
    }catch(error){
      applyAccount([]);
      show('로그인됨 · 브라우저 저장, 서버 동기화 대기');
    }
    buttons(session);
  }catch(error){
    guestRestore();buttons(null);show('비회원 · 브라우저 저장 (AuthHub 확인 지연)');
  }
}
bootstrap().catch(error=>{console.warn('WorkLinks AuthHub bootstrap',error);show('브라우저 저장 유지 · 인증 서버 확인 필요')});
