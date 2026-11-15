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
function safeHref(url){const value=String(url||'');return value.startsWith('https://')||value.startsWith('http://')?value:''}
function keptMarkup(item){
  const title=esc(item.title||item.id), org=esc(item.org||'발주기관 미확인');
  const amount=String(item.amount||'').trim();
  const deadline=String(item.deadline||'').trim();
  const url=safeHref(item.url);
  const own=state.mode==='mine';
  return '<article class="card keep-job-card" data-keep-item="'+esc(item.id)+'">'+
    '<div class="keep-job-main">'+
      '<div class="keep-job-title">'+title+'</div>'+
      '<div class="keep-job-meta">'+org+
      (deadline?' · '+esc(deadline):'')+'</div>'+
      (amount?'<strong class="keep-job-amount">'+esc(amount)+'</strong>':'')+
    '</div>'+
    '<div class="keep-job-actions">'+
      (own?'<button type="button" class="job-keep-button active" data-keep-toggle="'+esc(item.id)+'" aria-label="'+title+' 킵 해제">★ 킵</button>':'')+
      (url?'<a class="keep-job-link" target="_blank" rel="noopener noreferrer" href="'+esc(url)+'">공고 원문 ↗</a>':'')+
    '</div>'+
  '</article>';
}
function render(){
  const active=!!currentUser(),view=byId('jobsView'),toolbar=byId('keepToolbar');
  if(!view||!toolbar)return;
  toolbar.hidden=!active;
  if(!active){view.dataset.keepMode='all';byId('keepListPanel').hidden=true;return}
  view.dataset.keepMode=state.mode;
  byId('keepListPanel').hidden=state.mode==='all';
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
  const content=byId('keepListCards');
  let list=state.mode==='mine'?state.mine:state.mode==='watch'?state.watch:[];
  content.innerHTML=list.length?list.map(keptMarkup).join(''):
    '<div class="keep-empty">'+(state.mode==='mine'?
      (state.ownLoaded?'킵한 일감이 없습니다. 공고 카드의 ☆ 킵을 눌러 추가하세요.':'내 킵 목록을 불러오는 중입니다.'):
      state.watchId?'선택한 회원이 공유한 킵 목록이 비어 있습니다.':
      '관전할 회원을 선택하세요.')+'</div>';
  const heading=byId('keepListHeading');
  heading.textContent=state.mode==='mine'?'내 킵 · '+state.mine.length+'건':
    state.mode==='watch'?'관전 · '+(state.watchMember?.name||'대상 선택')+' · '+list.length+'건':'';
}
function refreshCards(){
  if(typeof window.scheduleJobsRender==='function')window.scheduleJobsRender();
}
async function loadMine(){
  if(!currentUser())return;
  try{
    const data=await call('/worklinks-keep');
    if(!data?.ok||!Array.isArray(data.items))throw Error('keep_invalid_response');
    state.mine=data.items;
    state.ownLoaded=true;
    state.shareEnabled=Boolean(data.shareEnabled);
    state.shareAlias=String(data.shareAlias||'');
    render();refreshCards();
  }catch(err){
    status('내 킵 목록 조회 실패 · '+String(err.message||err).slice(0,80),true);
    throw err;
  }
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
async function loadWatch(id){
  const serial=++state.watchSerial;
  state.watchId=id||'';state.watch=[];state.watchMember=null;render();
  if(!id||!currentUser())return;
  status('선택한 회원의 킵 목록 확인 중');
  try{
    const result=await call('/worklinks-keep-watch?member='+encodeURIComponent(id));
    if(serial!==state.watchSerial||state.watchId!==id||!currentUser())return;
    if(!result?.ok||!result.readOnly||!Array.isArray(result.items))throw Error('watch_invalid_response');
    state.watch=result.items;state.watchMember=result.member;
    status('읽기 전용 관전 · '+state.watch.length+'건');
    render();
  }catch(err){
    if(serial!==state.watchSerial)return;
    state.watch=[];state.watchMember=null;
    status('관전 불가 · 공유가 해제됐거나 조회에 실패했습니다.',true);render();
  }
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
    state.shareEnabled=false;state.shareAlias='';state.watchSerial++;render();return;
  }
  if(next===state.user)return;
  state.user=next;state.mode='all';state.mine=[];state.watch=[];
  state.watchId='';state.members=[];state.watchSerial++;state.ownLoaded=false;
  state.shareEnabled=false;state.shareAlias='';state.memberLoaded=false;
  render();loadMine().catch(()=>{});
}
for(const key of ['all','mine','watch']){
  byId('keepMode'+key[0].toUpperCase()+key.slice(1))?.addEventListener('click',()=>modeChange(key));
}
byId('keepMemberSelect')?.addEventListener('change',e=>loadWatch(e.target.value));
byId('keepSaveShare')?.addEventListener('click',saveSharing);
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-keep-toggle]');
  if(!button)return;
  event.preventDefault();event.stopPropagation();
  toggleKeep(button.dataset.keepToggle);
});
window.worklinksKeeps={has:savedById,keepButton,getMode:()=>state.mode,refresh:loadMine};
window.addEventListener('worklinks:partner-access',accountChanged);
accountChanged();
setInterval(()=>{
  if(!currentUser()||document.hidden||!byId('jobsView')?.classList.contains('on'))return;
  if(state.mode==='watch')loadMembers().then(()=>{
    if(state.watchId)loadWatch(state.watchId);
  }).catch(()=>{});
},45000);
