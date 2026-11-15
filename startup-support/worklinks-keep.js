// Account-only kept jobs. The server is the source of truth for all members.
const byId=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
})[c]);
const currentUser=()=>window.worklinksKeepCurrentUser?.()||'';
const call=(path,opts)=>window.worklinksKeepRequest(path,opts);
const jsonPost=(path,data)=>call(path,{method:'POST',body:JSON.stringify(data)});
const state={user:'',mine:[],members:[],watch:[],watchMember:null,
  watchId:'',mode:'all',shareEnabled:false,shareAlias:'',
  ownLoaded:false,memberLoaded:false,busy:new Set(),watchSerial:0,loading:false};
const WATCH_SELECTION_PREFIX='worklinks_keep_watch_target_v1:';
const WATCH_SEEN_PREFIX='worklinks_keep_watch_seen_v1:';
const WATCH_DESKTOP_PREFIX='worklinks_keep_watch_desktop_v1:';
const originalPageTitle=document.title;
let watchRequest=null,watchRequestId='',watchAlertCount=0;
const watchStorageGet=key=>{try{return localStorage.getItem(key)}catch{return null}};
const watchStorageSet=(key,value)=>{try{localStorage.setItem(key,value)}catch{}};
function watchSelectedKey(user){return WATCH_SELECTION_PREFIX+user}
function watchSeenKey(user,member){return WATCH_SEEN_PREFIX+user+':'+member}
function storedWatchTarget(user){
  const target=watchStorageGet(watchSelectedKey(user))||'';
  return /^[a-zA-Z0-9_-]{8,128}$/.test(target)?target:'';
}
function rememberedWatchIds(user,member){
  try{
    const record=JSON.parse(watchStorageGet(watchSeenKey(user,member))||'null');
    return Array.isArray(record?.ids)?new Set(record.ids.filter(x=>typeof x==='string')):null;
  }catch{return null}
}
function rememberWatchIds(user,member,items){
  watchStorageSet(watchSeenKey(user,member),JSON.stringify({
    ids:items.map(x=>x.id),updatedAt:Date.now()
  }));
}
function browserAlertEnabled(){
  return watchStorageGet(WATCH_DESKTOP_PREFIX+state.user)!=='off';
}
function updateNotificationButton(){
  const b=byId('keepNotifyButton');
  if(!b)return;
  b.hidden=!state.user||state.mode!=='watch'||!state.watchId;
  if(b.hidden)return;
  if(!('Notification' in window)){
    b.textContent='알림 미지원';b.disabled=true;return;
  }
  b.disabled=false;
  if(Notification.permission==='denied'){
    b.textContent='🔕 알림 차단됨';
    b.title='브라우저의 사이트 설정에서 알림을 허용하세요. 앱 안의 알림은 계속 표시됩니다.';
  }else if(Notification.permission==='granted'){
    const on=browserAlertEnabled();
    b.textContent=on?'🔔 알림 켜짐':'🔕 알림 꺼짐';
    b.title=on?'클릭하면 데스크톱 알림을 끕니다.':'클릭하면 데스크톱 알림을 켭니다.';
  }else{
    b.textContent='🔔 알림 켜기';
    b.title='다른 브라우저 탭을 보고 있어도 새 킵을 데스크톱 알림으로 받습니다.';
  }
}
async function toggleDesktopAlerts(){
  if(!state.user||!state.watchId||!('Notification' in window))return;
  if(Notification.permission==='denied'){
    status('브라우저 사이트 설정에서 알림을 허용해야 합니다. 앱 내 알림은 계속 표시됩니다.',true);
  }else if(Notification.permission==='granted'){
    const enabled=!browserAlertEnabled();
    watchStorageSet(WATCH_DESKTOP_PREFIX+state.user,enabled?'on':'off');
    status(enabled?'데스크톱 관전 알림을 켰습니다.':'데스크톱 관전 알림을 껐습니다.');
  }else{
    const permission=await Notification.requestPermission();
    if(permission==='granted'){
      watchStorageSet(WATCH_DESKTOP_PREFIX+state.user,'on');
      status('데스크톱 알림을 켰습니다. 다른 탭을 보고 있어도 알려드립니다.');
    }else status('데스크톱 알림은 허용되지 않았습니다. 앱 내 알림은 계속 표시됩니다.',true);
  }
  updateNotificationButton();
}
function openWatchedList(){
  if(!currentUser()||!state.watchId)return;
  state.mode='watch';
  if(typeof window.setWorkspaceView==='function')window.setWorkspaceView('jobs');
  render();
  const toast=byId('worklinksWatchAlert');
  if(toast)toast.remove();
  watchAlertCount=0;
  document.title=originalPageTitle;
  window.focus();
}
function showWatchAdditionAlert(items,member){
  if(!items.length||!state.watchId||!currentUser())return;
  const name=String(member?.name||'관전 대상').slice(0,48);
  watchAlertCount+=items.length;
  let toast=byId('worklinksWatchAlert');
  if(!toast){
    toast=document.createElement('aside');
    toast.id='worklinksWatchAlert';
    toast.className='worklinks-watch-alert';
    toast.setAttribute('role','alert');
    toast.innerHTML='<div class="worklinks-watch-alert-message"></div>'+
      '<div class="worklinks-watch-alert-actions">'+
      '<button type="button" data-watch-open>관전 목록 보기</button>'+
      '<button type="button" data-watch-dismiss aria-label="알림 닫기">닫기</button></div>';
    toast.querySelector('[data-watch-open]').addEventListener('click',openWatchedList);
    toast.querySelector('[data-watch-dismiss]').addEventListener('click',()=>{
      toast.remove();watchAlertCount=0;document.title=originalPageTitle;
    });
    document.body.appendChild(toast);
  }
  const last=items[0]?.title||'새 공고';
  toast.querySelector('.worklinks-watch-alert-message').textContent=
    '🔔 '+name+'님이 킵 '+watchAlertCount+'건을 추가했습니다.\n'+
    String(last).slice(0,100)+(watchAlertCount>1?' 외 '+(watchAlertCount-1)+'건':'');
  document.title='🔔 '+watchAlertCount+'건 · '+originalPageTitle;
  if('Notification' in window&&Notification.permission==='granted'&&
      browserAlertEnabled()&&(document.hidden||!document.hasFocus())){
    try{
      const notice=new Notification(name+'님이 킵 '+items.length+'건 추가',{
        body:String(last).slice(0,120),tag:'worklinks-watch-'+state.watchId
      });
      notice.onclick=()=>{notice.close();openWatchedList()};
    }catch{/* Browser/system notification unavailable; keep in-page alert. */}
  }
}
function status(message,isError=false){
  const el=byId('keepStatus');
  if(el){el.textContent=message||'';el.dataset.error=isError?'true':'false';}
}
function savedById(id){return state.mine.some(x=>x.id===id)}
function keepButton(id){
  if(!currentUser())return '';
  const selected=savedById(id);
  return '<button type="button" class="job-keep-button'+(selected?' active':'')+
    '" data-keep-toggle="'+esc(id)+'" aria-pressed="'+(selected?'true':'false')+
    '" title="'+(selected?'내 킵에서 제외':'내 킵에 추가')+'">'+
    (selected?'★ 킵':'☆ 킵')+'</button>';
}
// Kept and watched notices always use the original #jobCards renderer.

function render(){
  const active=!!currentUser(),view=byId('jobsView'),toolbar=byId('keepToolbar');
  if(!view||!toolbar)return;
  toolbar.hidden=!active;
  if(!active){view.dataset.keepMode='all';refreshCards();return}
  view.dataset.keepMode=state.mode;
  // Only the shared #jobCards grid is rendered in every mode.
  for(const key of ['all','mine','watch']){
    const b=byId('keepMode'+key[0].toUpperCase()+key.slice(1));
    if(!b)continue;
    const on=state.mode===key;
    b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));
  }
  byId('keepMineCount').textContent=String(state.mine.length);
  byId('keepMemberWrap').hidden=state.mode!=='watch';
  const selected=byId('keepMemberSelect');
  const previous=state.watchId||'';
  selected.replaceChildren(new Option('관전 대상 선택',''));
  for(const member of state.members){
    selected.add(new Option(member.name+' · '+member.count+'건',member.id));
  }
  selected.value=state.members.some(x=>x.id===previous)?previous:'';
  const checkbox=byId('keepShareEnabled');
  if(document.activeElement!==checkbox)checkbox.checked=state.shareEnabled;
  const alias=byId('keepShareAlias');
  if(document.activeElement!==alias)alias.value=state.shareAlias;
  updateNotificationButton();
  refreshCards();
}
function refreshCards(){
  if(typeof window.scheduleJobsRender==='function')window.scheduleJobsRender();
  if(state.mode!=='all'&&typeof window.worklinksHydrateKeptJobs==='function')
    window.worklinksHydrateKeptJobs(state.mode==='mine'?state.mine:state.watch).catch(()=>{
      status('일부 공고의 원본 조회를 완료하지 못했습니다. 원문 링크는 계속 이용할 수 있습니다.',true);
    });
}
let mineLoadPromise=null;
function keepFailureReason(error){
  const code=Number(error?.status)||0;
  if(code===401||code===403||String(error?.message)==='auth_required')
    return '인증 연결 오류 (HTTP '+(code||401)+')';
  if(code===404)return '킵 조회 API 연결 오류 (HTTP 404)';
  if(code===408||code===429||code>=500)
    return '서버 응답 오류 (HTTP '+code+')';
  if(error?.name==='TimeoutError'||error?.name==='AbortError')
    return '응답 시간 초과';
  if(error instanceof TypeError)return '네트워크 연결 오류';
  return String(error?.message||'조회 오류').slice(0,90);
}
async function loadMine(){
  const owner=currentUser();
  if(!owner||document.documentElement.dataset.worklinksAuthState!=='granted')return false;
  if(mineLoadPromise)return mineLoadPromise;
  mineLoadPromise=(async()=>{
    let lastError=null,data=null;
    for(let attempt=0;attempt<3;attempt++){
      if(owner!==currentUser()||
         document.documentElement.dataset.worklinksAuthState!=='granted')return false;
      try{
        data=await call('/worklinks-keep');
        if(!data?.ok||!Array.isArray(data.items))throw Error('keep_invalid_response');
        break;
      }catch(error){
        lastError=error;
        const code=Number(error?.status)||0;
        const transient=[408,429,500,502,503,504].includes(code)||
          error?.name==='TimeoutError'||error?.name==='AbortError'||
          error instanceof TypeError;
        if(!transient||attempt===2)break;
        await new Promise(resolve=>setTimeout(resolve,450*(attempt+1)));
      }
    }
    if(owner!==currentUser())return false;
    if(!data){
      status('내 킵 조회 실패 · '+keepFailureReason(lastError),true);
      return false;
    }
    state.mine=data.items;
    state.ownLoaded=true;
    state.shareEnabled=Boolean(data.shareEnabled);
    state.shareAlias=String(data.shareAlias||'');
    // Do not mislabel a card rendering exception as a server fetch failure.
    status('');
    render();refreshCards();
    return true;
  })().finally(()=>{mineLoadPromise=null});
  return mineLoadPromise;
}

async function loadMembers(){
  if(!currentUser())return;
  try{
    const data=await call('/worklinks-keep-members');
    if(!data?.ok||!Array.isArray(data.members))throw Error('members_invalid_response');
    state.members=data.members;
    state.memberLoaded=true;render();
  }catch(err){
    status('관전 대상 조회 실패 · '+String(err.message||err).slice(0,80),true);
  }
}
// Keep the selected target subscribed regardless of which WorkLinks workspace
// is visible. Never notify for the initial snapshot; only newly added IDs.
async function syncWatch(id){
  const user=currentUser(),serial=state.watchSerial;
  if(!id||!user||document.documentElement.dataset.worklinksAuthState!=='granted')return false;
  if(watchRequest&&watchRequestId===id)return watchRequest;
  const request=(async()=>{
    const result=await call('/worklinks-keep-watch?member='+encodeURIComponent(id));
    if(serial!==state.watchSerial||state.watchId!==id||user!==currentUser()||
       document.documentElement.dataset.worklinksAuthState!=='granted')return false;
    if(!result?.ok||!result.readOnly||!Array.isArray(result.items))
      throw Error('watch_invalid_response');
    const seen=rememberedWatchIds(user,id);
    const added=seen?result.items.filter(x=>x&&typeof x.id==='string'&&!seen.has(x.id)):[];
    rememberWatchIds(user,id,result.items);
    const changed=state.watch.length!==result.items.length||
      state.watch.some((x,i)=>x.id!==result.items[i]?.id||x.savedAt!==result.items[i]?.savedAt);
    state.watch=result.items;
    state.watchMember=result.member;
    const member=state.members.find(x=>x.id===id);
    if(member)member.count=result.items.length;
    if(state.mode==='watch'){
      status('읽기 전용 관전 · '+state.watch.length+'건');
      if(changed)render();
    }
    if(added.length)showWatchAdditionAlert(added,result.member);
    return true;
  })();
  watchRequest=request;watchRequestId=id;
  try{return await request}
  catch(err){
    if(serial!==state.watchSerial||user!==currentUser()||state.watchId!==id)return false;
    if(Number(err?.status)===404){
      state.watchId='';state.watch=[];state.watchMember=null;
      watchStorageSet(watchSelectedKey(user),'');
      status('관전 종료 · 대상 회원의 공유가 해제됐습니다.',true);
      render();
    }else if(state.mode==='watch'){
      status('관전 목록 확인 실패 · '+keepFailureReason(err),true);
    }
    return false;
  }finally{
    if(watchRequest===request){watchRequest=null;watchRequestId='';}
  }
}
async function loadWatch(id){
  const user=currentUser();
  ++state.watchSerial;
  state.watchId=id||'';state.watch=[];state.watchMember=null;
  if(user)watchStorageSet(watchSelectedKey(user),state.watchId);
  render();
  if(!id||!user){status('');return}
  status('선택한 회원의 킵 목록 확인 중');
  await syncWatch(id);
}
async function toggleKeep(id){
  if(!currentUser()||state.busy.has(id))return;
  const isSaved=savedById(id);
  let snapshot={};
  if(!isSaved){
    snapshot=window.worklinksKeepSnapshotFor?.(id)||{};
    if(!snapshot.title){status('이 공고 정보를 찾지 못해 킵할 수 없습니다.',true);return}
  }
  state.busy.add(id);
  status('킵 변경 저장 중');
  try{
    const result=await jsonPost('/worklinks-keep',{id,value:!isSaved,snapshot});
    if(!result?.ok)throw Error('keep_write_not_confirmed');
    await loadMine();
    if(state.mode==='watch')await loadMembers();
    status(isSaved?'내 킵에서 제외했습니다.':'내 킵에 저장했습니다.');
  }catch(err){
    status('킵 저장 실패 · '+String(err.message||err).slice(0,80),true);
  }finally{state.busy.delete(id);}
}
async function saveSharing(){
  if(!currentUser())return;
  const enabled=byId('keepShareEnabled').checked;
  const alias=byId('keepShareAlias').value.trim();
  const button=byId('keepSaveShare');
  button.disabled=true;status('공유 설정 저장 중');
  try{
    const result=await jsonPost('/worklinks-keep-share',{enabled,alias});
    if(!result?.ok)throw Error('share_write_not_confirmed');
    state.shareEnabled=result.shareEnabled;state.shareAlias=result.shareAlias;
    status(enabled?'내 킵을 다른 회원이 관전할 수 있습니다.':'내 킵 관전을 비공개로 변경했습니다.');
    await loadMembers();render();
  }catch(err){status('공유 설정 저장 실패 · '+String(err.message||err).slice(0,80),true);}
  finally{button.disabled=false;}
}
function modeChange(mode){
  if(!currentUser())return;
  state.mode=mode;render();
  if(mode==='mine')loadMine().catch(()=>{});
  if(mode==='watch'){
    loadMembers().then(()=>{if(state.watchId)loadWatch(state.watchId)}).catch(()=>{});
  }
}
function accountChanged(){
  const next=currentUser();
  if(!next){
    state.user='';state.mine=[];state.watch=[];state.members=[];
    state.watchId='';state.mode='all';state.ownLoaded=false;
    state.shareEnabled=false;state.shareAlias='';state.watchSerial++;
    byId('worklinksWatchAlert')?.remove();
    watchAlertCount=0;document.title=originalPageTitle;
    render();return;
  }
  if(next===state.user)return;
  state.user=next;state.mode='all';state.mine=[];state.watch=[];
  state.watchId=storedWatchTarget(next);state.members=[];state.watchSerial++;state.ownLoaded=false;
  state.shareEnabled=false;state.shareAlias='';state.memberLoaded=false;
  byId('worklinksWatchAlert')?.remove();
  watchAlertCount=0;document.title=originalPageTitle;
  render();loadMine().catch(()=>{});
  if(state.watchId)syncWatch(state.watchId).catch(()=>{});
}
for(const key of ['all','mine','watch']){
  byId('keepMode'+key[0].toUpperCase()+key.slice(1))?.addEventListener('click',()=>modeChange(key));
}
byId('keepMemberSelect')?.addEventListener('change',e=>loadWatch(e.target.value));
byId('keepNotifyButton')?.addEventListener('click',toggleDesktopAlerts);
byId('keepSaveShare')?.addEventListener('click',saveSharing);
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-keep-toggle]');
  if(!button)return;
  event.preventDefault();event.stopPropagation();
  toggleKeep(button.dataset.keepToggle);
});
window.worklinksKeeps={
  has:savedById,
  keepButton:id=>state.mode==='watch'?'':keepButton(id),
  getMode:()=>state.mode,
  activeItems:()=>state.mode==='mine'?state.mine:state.mode==='watch'?state.watch:[],
  refresh:loadMine,
  pollWatch:()=>state.watchId?syncWatch(state.watchId):Promise.resolve(false)
};
window.addEventListener('worklinks:partner-access',accountChanged);
accountChanged();
// Poll in the background as well as on other WorkLinks workspace tabs.
// Browsers may throttle hidden tabs; focus/visibility immediately catches up.
setInterval(()=>{
  if(!currentUser()||!state.watchId)return;
  syncWatch(state.watchId).catch(()=>{});
},10000);
setInterval(()=>{
  if(!currentUser()||document.hidden||state.mode!=='watch')return;
  loadMembers().catch(()=>{});
},45000);
window.addEventListener('focus',()=>{
  if(state.watchId)syncWatch(state.watchId).catch(()=>{});
});
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden&&state.watchId)syncWatch(state.watchId).catch(()=>{});
});
