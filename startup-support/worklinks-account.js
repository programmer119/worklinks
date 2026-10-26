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
const INTENT_PREFIX='worklinks_support_intents_v1:';
const intentsFor=key=>decode(INTENT_PREFIX+key);
const timeOf=x=>Number(x?.at)||0;
const remoteTime=x=>Date.parse(x?.updatedAt||'')||0;
const state = {client:null,token:'',account:'',project:'',busy:false,loading:false,serverReady:false,refreshing:null,records:[],imported:0};
const $ = (id)=>document.getElementById(id);
// Partner UI is fail-closed: only an active AuthHub /v1/me membership grants access.
// This event drives the existing (non-module) WorkLinks page; no token is exposed.
function publishPartnerAccess(verified){
  const allowed=Boolean(verified&&state.account&&state.token);
  const status=allowed?'granted':'guest';
  if(window.worklinksMemberAuthenticated===allowed&&document.documentElement.dataset.worklinksPartnerAccess===status)return;
  window.worklinksMemberAuthenticated=allowed;
  document.documentElement.dataset.worklinksPartnerAccess=status;
  window.dispatchEvent(new CustomEvent('worklinks:partner-access',{detail:{authenticated:allowed}}));
}
publishPartnerAccess(false);
const decode = (key)=>{try{const r=JSON.parse(localStorage.getItem(key)||'{}');return r&&typeof r==='object'&&!Array.isArray(r)?r:{}}catch{return {}}};
const accountKeys = (user)=>({
  applied:'worklinks_support_applied_v2:'+user,
  hidden:'worklinks_support_hidden_v2:'+user,
  business:'worklinks_support_business_v2:'+user,
  pending:'worklinks_support_pending_v2:'+user
});
function itemDetails(id){
  // User-added notices are not part of the public static catalog.
  // Keep their original title/URL in the per-account server record,
  // including when a guest's custom submission is migrated on login.
  const memberKey=state.account?'worklinks_support_manual_entries_v1:'+accountKeys(state.account).applied:'';
  const owner=localStorage.getItem(GUEST_OWNER_KEY);
  const guestKey=(!owner||owner===state.account)?'worklinks_support_manual_entries_v1:'+GUEST.applied:'';
  const member=memberKey?decode(memberKey)[id]:null;
  const guest=guestKey?decode(guestKey)[id]:null;
  const entry=(window.items||[]).find(x=>x.id===id)||(window.pendingSupportCandidates||[]).find(x=>x.id===id)||state.records.find(x=>x.id===id)||member||guest||{};
  return {title:String(entry.title||'').slice(0,180),url:String(entry.url||'').slice(0,600)};
}
function show(message){
  const target=$('worklinks-auth-info');
  if(target)target.textContent=message;
}
// Recovery is opt-in: an explicit member-side false can be intentional.
// Only offer evidence from the SAME browser's positive guest history to its owner.
function guestAppliedConflicts(){
  if(!state.account||!state.serverReady)return [];
  const owner=localStorage.getItem(GUEST_OWNER_KEY);
  if(owner&&owner!==state.account)return [];
  const keys=accountKeys(state.account);
  const guest=decode(GUEST.applied),member=decode(keys.applied),pending=decode(keys.pending);
  const confirmed=new Set(state.records.filter(r=>r.kind==='applied'&&r.value===true).map(r=>r.id));
  return Object.keys(guest).filter(id=>
    guest[id]===true&&member[id]!==true&&!confirmed.has(id)&&
    pending['applied:'+id]?.value!==true
  ).map(id=>({id,...itemDetails(id)}));
}
function renderAppliedRecovery(){
  const root=$('worklinks-applied-recovery');
  if(!root||root.hidden)return;
  root.replaceChildren();
  const message=document.createElement('p');
  message.style.cssText='margin:0 0 8px;font-size:12px;line-height:1.6';
  if(!state.serverReady){
    message.textContent='서버 기록 동기화 전입니다. 계정 기록을 확인한 뒤 복구할 수 있습니다.';
    root.append(message);return;
  }
  const owner=localStorage.getItem(GUEST_OWNER_KEY);
  if(owner&&owner!==state.account){
    message.textContent='이 브라우저의 이전 비회원 기록은 다른 계정에 연결되어 있어 자동 복구할 수 없습니다.';
    root.append(message);return;
  }
  const conflicts=guestAppliedConflicts();
  const guestCount=Object.values(decode(GUEST.applied)).filter(v=>v===true).length;
  const memberCount=Object.values(decode(accountKeys(state.account).applied)).filter(v=>v===true).length;
  message.textContent='이 브라우저의 비회원 지원완료 '+guestCount+
    '건 · 현재 계정 지원완료 '+memberCount+'건 · 이전 기록 중 미반영 '+conflicts.length+'건.';
  root.append(message);
  if(!conflicts.length){
    const note=document.createElement('p');
    note.style.cssText='font-size:12px;line-height:1.5;margin:0';
    note.textContent='이 브라우저에서 확인되는 이전 기록과 계정 사이에는 누락이 없습니다. 다른 브라우저·계정의 기록은 여기서 조회할 수 없습니다.';
    root.append(note);return;
  }
  const note=document.createElement('p');
  note.style.cssText='font-size:12px;line-height:1.5;margin:0 0 8px';
  note.textContent='이전에 지원완료로 체크한 증거가 있으나 현재 계정에서 체크되지 않은 기록입니다. 실제 완료한 항목만 복구하세요. 기존 서버의 미지원 선택은 자동으로 덮어쓰지 않습니다.';
  root.append(note);
  for(const entry of conflicts){
    const row=document.createElement('div');
    row.style.cssText='display:flex;align-items:center;gap:8px;justify-content:space-between;padding:6px 0;border-top:1px solid #e2e8f0;flex-wrap:wrap';
    const title=document.createElement('span');
    title.textContent=entry.title||entry.id;
    title.style.cssText='font-size:12px;flex:1 1 200px;overflow-wrap:anywhere';
    const button=document.createElement('button');
    button.type='button';button.className='worklinks-auth-button';
    button.dataset.recoverId=entry.id;
    button.textContent='지원완료 복구';
    button.addEventListener('click',()=>{
      if(!state.serverReady||!state.account)return;
      if(!guestAppliedConflicts().some(x=>x.id===entry.id))return;
      const keys=accountKeys(state.account),map=decode(keys.applied);
      map[entry.id]=true;
      localStorage.setItem(keys.applied,JSON.stringify(map));
      window.saved=map;
      const migratedKey='worklinks_support_guest_migrated_v1:'+state.account;
      const migrated=decode(migratedKey);
      migrated['applied:'+entry.id]=true;
      localStorage.setItem(migratedKey,JSON.stringify(migrated));
      window.worklinksStatusChanged('applied',entry.id,true);
      if(typeof window.draw==='function')window.draw();
      renderAppliedRecovery();
    });
    row.append(title,button);root.append(row);
  }
}
async function renewApiSession(account,oldToken){
  if(state.account!==account||!state.client)throw Error('account_changed');
  if(state.token!==oldToken)return; // Another concurrent request already renewed it.
  if(!state.refreshing){
    state.refreshing=(async()=>{
      const refreshed=await state.client.refresh();
      if(!refreshed?.accessToken)throw Error('refresh_without_token');
      const me=await state.client.me();
      if(String(me?.user?.id||'')!==account||me?.membership?.status!=='active'||state.account!==account)
        throw Error('authhub_identity_changed');
      state.token=refreshed.accessToken;
    })().finally(()=>{state.refreshing=null});
  }
  await state.refreshing;
}
async function api(path,options={},retryAuth=true){
  const account=state.account, token=state.token;
  const response=await fetch(API_BASE+path,{
    ...options,headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...(token?{Authorization:'Bearer '+token}:{}),...(options.headers||{})},
    cache:'no-store',signal:AbortSignal.timeout(12000)
  });
  const data=await response.json().catch(()=>({}));
  if(response.status===401&&retryAuth&&account&&state.client&&path==='/worklinks-state'){
    await renewApiSession(account,token);
    if(state.account!==account)throw Error('account_changed');
    return api(path,options,false);
  }
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
  const memberIntents=intentsFor(keys.applied);
  for(const record of records){
    if(!record||!Object.prototype.hasOwnProperty.call(KIND,record.kind)||typeof record.id!=='string')continue;
    maps[record.kind][record.id]=record.value===true;
  }
  if(state.serverReady){
    for(const choice of Object.values(memberIntents)){
      if(choice?.kind!=='applied'||typeof choice.id!=='string'||typeof choice.value!=='boolean')continue;
      const key='applied:'+choice.id,remote=records.find(r=>r.kind==='applied'&&r.id===choice.id);
      if(!timeOf(choice)||(remote&&remoteTime(remote)>=timeOf(choice)))continue;
      if(pending[key]&&timeOf(pending[key])>=timeOf(choice))continue;
      if(remote?.value===choice.value)continue;
      pending[key]={kind:'applied',id:choice.id,value:choice.value,at:timeOf(choice),...itemDetails(choice.id)};
    }
  }
  for(const entry of Object.values(pending)){
    if(entry&&maps[entry.kind])maps[entry.kind][entry.id]=entry.value===true;
  }
  localStorage.setItem(keys.pending,JSON.stringify(pending));
  Object.entries(maps).forEach(([kind,map])=>localStorage.setItem(keys[kind],JSON.stringify(map)));
  window.statusKey=keys.applied;window.hiddenKey=keys.hidden;window.businessKey=keys.business;
  window.saved=maps.applied;window.hidden=maps.hidden;window.business=maps.business;
  state.records=records;
  window.worklinksArchivedStatuses=records.filter(r=>r.kind==='applied'&&r.value===true);
  if(typeof window.draw==='function')window.draw();
  renderAppliedRecovery();
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
  const guestChoices=Object.values(intentsFor(GUEST.applied));
  if(!entries.length&&!guestChoices.length)return 0;
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
    // A conflicting false stays visible for explicit restoration. Do NOT mark
    // it migrated when no import happened, even if an older build did so.
    if(maps[entry.kind][entry.id]===true)migrated[key]=true;
  }
  const memberChoices=intentsFor(keys.applied);
  for(const choice of guestChoices){
    if(choice?.kind!=='applied'||typeof choice.id!=='string'||typeof choice.value!=='boolean'||!(/^[A-Za-z0-9_.:-]{1,160}$/.test(choice.id)))continue;
    const key='applied:'+choice.id,at=timeOf(choice),remoteRecord=state.records.find(r=>r.kind==='applied'&&r.id===choice.id);
    if(!at||(remoteRecord&&remoteTime(remoteRecord)>=at)||timeOf(memberChoices[key])>=at)continue;
    if(pending[key]&&timeOf(pending[key])>=at)continue;
    if(remoteRecord?.value===choice.value)continue;
    pending[key]={kind:'applied',id:choice.id,value:choice.value,at,...itemDetails(choice.id)};
    maps.applied[choice.id]=choice.value;
    imported++;
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
  pending[kind+':'+id]={kind,id,value:!!value,at:Date.now(),...item};
  localStorage.setItem(keys.pending,JSON.stringify(pending));
  if(!state.serverReady)show('브라우저 기록 보존됨 · 서버 기록 확인 후 자동 동기화');
  flush().catch(()=>show('브라우저 저장됨 · 서버 동기화 대기'));
};
function guestRestore(){
  state.account='';state.token='';state.records=[];state.imported=0;state.serverReady=false;
  publishPartnerAccess(false);
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
    const recover=document.createElement('button');
    recover.type='button';recover.className='worklinks-auth-button';
    recover.textContent='지원기록 점검';
    recover.addEventListener('click',()=>{
      let panel=$('worklinks-applied-recovery');
      if(!panel){
        panel=document.createElement('section');
        panel.id='worklinks-applied-recovery';
        panel.style.cssText='flex:1 0 100%;min-width:0;padding:10px;border:1px solid #d7e2ee;background:#fff;border-radius:9px';
        document.querySelector('.worklinks-auth-panel')?.append(panel);
      }else panel.hidden=!panel.hidden;
      renderAppliedRecovery();
    });box.append(recover);
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
    if(!session){guestRestore();buttons(null);show('비회원 · 이 브라우저에만 저장');return}
    state.account=session.identity;state.token=session.token;state.serverReady=false;
    publishPartnerAccess(true);
    // Show preserved account-local data while waiting, but do not overwrite server truth.
    applyAccount([]);
    await reconcileServer();
    buttons(session);
  }catch(error){
    guestRestore();buttons(null);show('비회원 · 브라우저 저장 (AuthHub 확인 지연)');
  }
}
window.addEventListener('online',()=>{if(state.account){if(!state.serverReady)reconcileServer().catch(()=>{});else flush().catch(()=>{})}});
window.addEventListener('focus',()=>{
  if(!state.account)return;
  if(!state.serverReady)reconcileServer().catch(()=>{});
  else if(!state.busy&&Object.keys(decode(accountKeys(state.account).pending)).length)flush().catch(()=>{});
  const identity=state.account;
  // Revalidate on returning to the tab; expired/revoked access must not keep Partners open.
  validSession(state.client).then(session=>{
    if(identity!==state.account)return;
    if(!session||session.identity!==identity){
      guestRestore();buttons(null);show('인증 만료 · 다시 로그인하세요');
    }else{
      state.token=session.token;
      publishPartnerAccess(true);
    }
  }).catch(()=>{if(identity===state.account)publishPartnerAccess(false)});
});
window.addEventListener('storage',event=>{
  // A logout in another tab immediately revokes this tab's partner access.
  if(state.client&&event.key===state.client.key&&!event.newValue&&state.account){
    guestRestore();buttons(null);show('다른 탭에서 로그아웃됨');
  }
});
bootstrap().catch(error=>{console.warn('WorkLinks AuthHub bootstrap',error);show('브라우저 저장 유지 · 인증 서버 확인 필요')});
