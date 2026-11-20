/* Changcom: source-backed procurement stage and SW award filters.
 * Existing bid records require no new G2B requests; prebid reads local server DB.
 */
// A temporary AuthHub lock once changed a shared R26BD/R26BK URL from
// changcom into jobs, dropping its stage and query. Recover only verified
// procurement-number deep links, never a general jobs navigation.
if(typeof window!=='undefined'&&typeof URLSearchParams!=='undefined'&&
   typeof history!=='undefined'){
 const original=new URLSearchParams(window.location?.search||'');
 const bidNo=String(original.get('open')||'').trim().toUpperCase();
 const stage=/^R\d{2}BD\d{8}$/.test(bidNo)?'prespec':
   /^R\d{2}BK\d{8}$/.test(bidNo)?'bid':'';
 if(stage&&original.get('view')!=='changcom'){
  const url=new URL(window.location.href);
  url.searchParams.set('view','changcom');
  url.searchParams.set('stage',stage);
  url.searchParams.set('q',bidNo);
  history.replaceState(history.state,'',url.pathname+url.search+url.hash);
 }
}
// Preserve explicit links to individual stages; ordinary search opens ALL.
const partnerDeepLinkParams=typeof URLSearchParams!=='undefined'?
 new URLSearchParams(typeof window!=='undefined'?(window.location?.search||''):''):{get:()=>null};
const partnerDeepLinkId=String(partnerDeepLinkParams.get('notice')||partnerDeepLinkParams.get('q')||'').trim().toUpperCase();
const explicitPartnerStage=partnerDeepLinkParams.get('stage');
// Keep previously issued links working even if navigation stripped stage=.
const inferredPartnerStage=/^R\d{2}BD\d{8}$/.test(partnerDeepLinkId)?'prespec':
 /^R\d{2}BK\d{8}$/.test(partnerDeepLinkId)?'bid':null;
let partnerSwScope='all', partnerNoticeStage=['all','bid','plan','prespec'].includes(explicitPartnerStage)?
 explicitPartnerStage:(inferredPartnerStage||'all');
const initialPartnerStageSelect=typeof document!=='undefined'?document.getElementById?.('partnerNoticeStage'):null;
if(initialPartnerStageSelect)initialPartnerStageSelect.value=partnerNoticeStage;
// Empty selection means all award methods. Multiple checks are combined with OR.
const partnerAwardFilters=new Set();
const prebidCache={plan:{state:'idle',items:[],total:0,error:'',at:''},
                   prespec:{state:'idle',items:[],total:0,error:'',at:''}};
const PRICE_METHODS=new Set(['낙030021','낙030022','낙030029']);
const SPEC_PRICE_METHODS=new Set(['낙030002','낙030003','낙030018']);
// Prefer recall: uncertain software work stays visible for manual review.
function partnerSoftwareSignals(x){
 const title=String(x?.title||x?.name||'').normalize('NFKC');
 const text=(title+' '+String(x?.subject||x?.specContents||x?.purchsObjPrdctList||'')+' '+String(x?.productName||'')).normalize('NFKC');
 const official=x?.swFlagSource==='official'||String(x?.swBizObjYn||'').toUpperCase()==='Y';
 const productCode=String(x?.productCode||x?.dtilPrdctClsfcNo||'');
 const dev=/(개발|구축|고도화|재구축|전면.?개편|리뉴얼|커스터마이징|기능.?개선|기능.?추가|시스템.?전환|디지털.?전환|시스템화|연동.?개발|웹.?제작|앱.?제작)/i.test(text);
 const sw=/(소프트웨어|정보.?시스템|전산.?시스템|통합.?시스템|업무.?시스템|행정.?시스템|관리.?시스템|플랫폼|웹사이트|웹서비스|홈페이지|모바일.?앱|애플리케이션|데이터베이스|클라우드|인공지능|전자결재|전자문서|전자정부|행정서비스|전자서비스|온라인.?서비스|erp|crm|\bsw\b|s\/w)/i.test(text);
 const possible=/(시스템|전산|정보화|디지털|데이터|인터넷|웹|앱|자동화|ai\b|ict\b)/i.test(text);
 const noSw=/(전산.?소모품|토너|프린터.?소모품|사무용.?품|사무.?가구|청소.?용역|정보화.?교육|컴퓨터.?교육|전산.?교육|교육.?운영)/i.test(title);
 const equipment=/(서버|컴퓨터|프린터|복합기|스캐너|모니터|전산.?장비|기자재|cctv).{0,15}(구매|구입|납품|교체)/i.test(title);
 const onlyOperate=/(유지.?관리|유지.?보수|운영.?지원|정기.?점검|기술.?지원)/i.test(title)&&!dev;
 const onlyPurchase=/(라이선스|라이센스|솔루션.?구매|소프트웨어.?구매|구독.?서비스)/i.test(title)&&!dev;
 const onlyPlan=/(마스터.?플랜|isp\b|ismp\b|타당성.?조사|구축.?방안.?연구)/i.test(title)&&!dev;
 const code=productCode==='8111159901'||/8111159901/.test(String(x?.subject||''));
 const software=(official||code||sw||(possible&&dev))&&!(noSw&&!dev)&&!(equipment&&!dev&&!official&&!code);
 // 8111159901 can describe maintenance too: the code is a candidate, not proof.
 const build=software&&!(noSw&&!dev)&&!onlyOperate&&!onlyPurchase&&!onlyPlan&&
   (dev||official||code||sw);
 return {software,build,review:build&&!dev};
}
function swBuildTitle(x){return partnerSoftwareSignals(x).build}
function partnerSwRelated(x){return partnerSoftwareSignals(x).software}
const PARTNER_AWARD_LABELS={
 price:'가격낙찰형',qualification:'적격심사','spec-price':'규격·가격',
 negotiation:'협상',other:'기타·미확인'
};
function partnerAwardMethodGroup(x){
 if(!/^g2b-/.test(String(x?.id||'')))return 'other';
 const m=g2bCardAwardMetadata(x);
 if(!m?.sourceVerified)return 'other'; // Missing official data is not a confirmed award method.
 const code=String(m.awardMethodCode||'');
 if(PRICE_METHODS.has(code))return 'price';
 if(code==='낙030001')return 'qualification';
 if(SPEC_PRICE_METHODS.has(code))return 'spec-price';
 if(code==='낙030005')return 'negotiation';
 return 'other'; // Unmapped official code stays discoverable, not silently dropped.
}
function partnerAwardSummaryText(){
 const keys=Object.keys(PARTNER_AWARD_LABELS).filter(k=>partnerAwardFilters.has(k));
 if(!keys.length)return '낙찰 전체';
 if(keys.length===1)return PARTNER_AWARD_LABELS[keys[0]];
 if(keys.length===2)return keys.map(k=>PARTNER_AWARD_LABELS[k]).join(' + ');
 return keys.length+'개 방식 선택';
}
function syncPartnerAwardControl(){
 const panel=document.getElementById('partnerAwardFilter');
 if(!panel)return;
 const disabled=partnerNoticeStage!=='bid';
 panel.classList.toggle('disabled',disabled);
 if(disabled)panel.open=false;
 const trigger=panel.querySelector('summary');
 if(trigger){
  trigger.setAttribute('aria-disabled',disabled?'true':'false');
  trigger.title=disabled?'발주계획·사전규격은 낙찰방식 미확정 · 입찰공고에서만 사용':
   (partnerAwardFilters.size?Object.keys(PARTNER_AWARD_LABELS).filter(k=>partnerAwardFilters.has(k)).map(k=>PARTNER_AWARD_LABELS[k]).join(', '):
    '모든 낙찰방식 표시 · 여러 항목 동시 선택 가능');
 }
 const display=document.getElementById('partnerAwardSummary');
 if(display)display.textContent=partnerAwardSummaryText();
 panel.querySelectorAll('input[data-award-filter]').forEach(input=>{
  input.disabled=disabled;
  input.checked=input.dataset.awardFilter==='all'?partnerAwardFilters.size===0:
   partnerAwardFilters.has(input.dataset.awardFilter);
 });
}
function partnerBidMatchesNewFilters(x){
 if(partnerSwScope==='build'&&!swBuildTitle(x))return false;
 if(partnerSwScope==='sw'&&!partnerSwRelated(x))return false;
 return partnerAwardFilters.size===0||partnerAwardFilters.has(partnerAwardMethodGroup(x));
}
// The full tender corpus is read from existing saved SQLite only. It must not
// replace the SW-only dataset used by the unrelated general jobs workspace.
const partnerAllBids={items:[],total:0,loaded:0,state:'idle',error:''};
async function loadPartnerAllBids(more=false){
 if(!worklinksPartnerAccess()||!worklinksIsChangcomView()||
    !['bid','all'].includes(partnerNoticeStage))return;
 // An exact/search query must use the server's indexed q= endpoint. Never
 // download 73,000+ unrelated bid records just to find one prebid record.
 if((partnerNoticeStage==='all'&&String(jobSearchText||'').trim().length>=2)||
    /^R\d{2}BK\d{8}$/i.test(String(jobSearchText||'').trim()))return;
 if(partnerAllBids.state==='loading')return;
 if(!more&&partnerAllBids.state==='ready'){
  if(partnerNoticeStage==='all'||partnerSwScope==='all'||partnerAllBids.loaded>=partnerAllBids.total)return;
  more=true;
 }
 const offset=more?partnerAllBids.loaded:0;
 partnerAllBids.state='loading';partnerAllBids.error='';
 renderJobs();
 try{
  const result=await g2bFetch('/saved?sw=0&limit=200&offset='+offset);
  if(!Array.isArray(result.items)||!result.persisted||
     !Number.isSafeInteger(Number(result.totalCount))||
     Number(result.totalCount)<offset+result.items.length)
   throw Error('전체 저장 공고 페이지 응답 불완전');
  if(offset<Number(result.totalCount)&&!result.items.length)
   throw Error('전체 저장 공고 페이지 누락');
  if(more&&partnerAllBids.total&&partnerAllBids.total!==Number(result.totalCount))
   throw Error('조회 도중 전체 건수 변경 · 새로고침 필요');
  const cards=[];
  for(const row of result.items){
   const card=g2bCardFromServer(row);
   if(!card)throw Error('전체 공고의 공고번호 누락');
   cards.push(card);
   if(row.bidEligibility?.ok&&row.bidNo)
    bidEligibilityCache.set(String(row.bidNo)+':'+String(row.order||'000').padStart(3,'0'),row.bidEligibility);
  }
  partnerAllBids.items=more?partnerAllBids.items.concat(cards):cards;
  partnerAllBids.loaded=offset+cards.length;
  partnerAllBids.total=Number(result.totalCount);
  partnerAllBids.state='ready';
 }catch(error){
  partnerAllBids.error=String(error?.message||error).slice(0,140);
  partnerAllBids.state='error';
 }finally{
  if(worklinksIsChangcomView()&&['bid','all'].includes(partnerNoticeStage)){
   renderJobs();
   // Only the explicitly selected bid SW/build view performs a continuing
   // full-corpus scan; the unified view pages on demand to avoid saturation.
   if(partnerNoticeStage==='bid'&&partnerSwScope!=='all'&&
      partnerAllBids.state==='ready'&&partnerAllBids.loaded<partnerAllBids.total)
    void loadPartnerAllBids(true);
  }
 }
}
// Read-only SQLite page requests may fail transiently while the API port recovers.
// Retry only network/timeouts/5xx; never retry an official 403 or mutate the DB.
const PREBID_READ_RETRY_DELAYS=[350,1100];
function prebidTransientReadFailure(error){
 const message=String(error?.message||error||'');
 return ['AbortError','TimeoutError','TypeError'].includes(error?.name)||
  /(?:Failed to fetch|fetch failed|NetworkError|network connection|Load failed|HTTP (?:429|50[0-9]))/i.test(message);
}
async function prebidReadPageWithRetry(stage,offset){
 for(let attempt=0;;attempt++){
  try{return await g2bFetch('/prebid?stage='+stage+'&limit=500&offset='+offset)}
  catch(error){
   if(attempt>=PREBID_READ_RETRY_DELAYS.length||!prebidTransientReadFailure(error))throw error;
   await new Promise(resolve=>setTimeout(resolve,PREBID_READ_RETRY_DELAYS[attempt]));
  }
 }
}
async function loadPrebidJobs(stage,force=false){
 if(!['plan','prespec'].includes(stage)||!worklinksPartnerAccess())return;
 const state=prebidCache[stage];
 if(state.state==='loading')return;
 if(!force&&state.state==='ready'&&Date.now()-Number(state.cachedAt||0)<60000)return;
 state.state='loading';state.error='';
 renderJobs();
 try{
  let data=[],offset=0,total=null,at='',ready=false,complete=false;
  for(let page=0;page<40;page++){
   const res=await prebidReadPageWithRetry(stage,offset);
   if(!res||res.ok!==true)throw Error(res?.error||'사전 단계 목록 응답 오류');
   if(!res.ready)throw Error(res.error||'사전 단계 수집 자료 없음');
   ready=true;at=res.asOf||at;total=Number(res.total||0);
   if(!Number.isSafeInteger(total)||total<0||!Array.isArray(res.items))throw Error('사전 단계 DB 집계 오류');
   data.push(...res.items);offset=data.length;
   if(offset>=total){complete=true;break}
   if(!res.items.length)throw Error('사전 단계 목록 페이지 불완전');
  }
  if(!ready||!complete)throw Error('사전 단계 목록 일부만 수신, 전체 판정 보류');
  state.items=data;state.total=data.length;state.at=at;state.state='ready';state.cachedAt=Date.now();
 }catch(err){
  state.state='error';state.error=String(err?.message||err).slice(0,160);
 }finally{if(partnerNoticeStage===stage||partnerNoticeStage==='all')renderJobs()}
}
function prebidWon(value){
 const n=Number(value);
 if(!Number.isFinite(n)||n<=0)return '예산 미기재';
 return n>=1e8?Number((n/1e8).toFixed(2)).toLocaleString('ko-KR')+'억 원':
  Math.round(n/10000).toLocaleString('ko-KR')+'만원';
}
// Stable, stage-scoped IDs prevent plan/prespec/ordinary-bid keep collisions.
// The official API supplies attachment download URLs but no display names.
// Never fabricate "규격서 1/2/3"; exact names are fetched from G2B GET headers
// by the server and persisted separately from the government API snapshot.
const prebidObservedFileNames={
 'R26BD00302593':['붙임 제안요청서.hwpx','붙임 제출서식.hwpx','붙임 긴급입찰사유서.hwpx']
}; // Verified GET Content-Disposition, Actions #44762273373.
function prebidOfficialFileEntries(x,limit=8){
 const names=Array.isArray(x?.fileNames)?x.fileNames:[];
 const files=Array.isArray(x?.files)?x.files:[];
 return files.map((url,i)=>{
  if(!/^https:\/\/(?:www\.)?g2b\.go\.kr\/pn\/pnz\/pnza\/UntyAtchFile\/downloadFile\.do\?/i.test(url))return null;
  let name=String(names[i]||'').trim();
  if(!name&&x.id==='R26BD00302593'&&x.stage==='prespec'){
   try{
    const u=new URL(url);
    if(u.searchParams.get('bfSpecRegNo')===x.id &&
       u.searchParams.get('fileType')==='BFDTL'){
      const n=Number(u.searchParams.get('fileSeq'));
      if(n>=1&&n<=3)name=prebidObservedFileNames[x.id][n-1];
    }
   }catch(_){}
  }
  return {url,name};
 }).filter(Boolean).slice(0,limit);
}
function prebidSourceMarkup(x,safe,fileEntries){
 const id=String(x.id||'');
 const source=safe||(fileEntries.length?fileEntries[0].url:'https://www.g2b.go.kr/');
 const label=safe?'원문 보기':fileEntries.length?'원본문서 보기':'나라장터에서 조회';
 const title=safe?'나라장터 원문 열기':fileEntries.length?
  '나라장터에 등록된 첫 번째 원본문서 열기':
  '나라장터에서 등록번호 '+id+' 검색 · 상세 직링크 미확인';
 return '<a class="prebid-source-action" data-external-source="1" href="'+htmlEscape(source)+
  '" target="_blank" rel="noopener noreferrer" title="'+htmlEscape(title)+'">'+label+'</a>';
}
const prebidMetaRetryAfter=new Map(),prebidMetaQueue=[],prebidMetaPending=new Set();
let prebidMetaActive=0;
function queuePrebidFileMetadata(rows){
 for(const x of rows||[]){
  if(!x||x.stage!=='prespec'||!Array.isArray(x.files)||!x.files.length)continue;
  const id=prebidKeepId(x);
  if(!id||prebidMetaPending.has(id)||Date.now()<(prebidMetaRetryAfter.get(id)||0))continue;
  const entries=prebidOfficialFileEntries(x,5);
  if(entries.length&&entries.every(entry=>entry.name))continue;
  prebidMetaPending.add(id);
  prebidMetaQueue.push({x,id});
 }
 pumpPrebidFileMetadata();
}
function pumpPrebidFileMetadata(){
 while(prebidMetaActive<2&&prebidMetaQueue.length){
  const {x,id}=prebidMetaQueue.shift();
  prebidMetaActive++;
  const path='/prebid-file-names?stage=prespec&kind='+encodeURIComponent(x.kind)+
   '&id='+encodeURIComponent(x.id);
  Promise.resolve().then(()=>g2bFetch(path)).then(result=>{
   const received=result?.fileNames;
   if(!Array.isArray(received))throw Error('prebid_filename_response_invalid');
   const names=received.map(v=>String(v||'').trim());
   x.fileNames=names;
   // A visible record may have been replaced by a later saved-DB refresh.
   const current=prebidCache.prespec.items.find(row=>row.id===x.id&&row.kind===x.kind);
   if(current&&current!==x)current.fileNames=names;
   prebidMetaRetryAfter.set(id,Date.now()+(names.every(Boolean)?172800000:1200000));
   if(typeof renderJobs==='function')renderJobs();
   if(typeof activeDetailJobId!=='undefined'&&activeDetailJobId===id)
    renderPrebidSourceDetail({id});
  }).catch(()=>{
   prebidMetaRetryAfter.set(id,Date.now()+120000);
  }).finally(()=>{
   prebidMetaPending.delete(id);prebidMetaActive--;pumpPrebidFileMetadata();
  });
 }
}
function prebidKeepId(x){
 const stage=String(x?.stage||''),kind=String(x?.kind||''),id=String(x?.id||'').trim();
 if(!['plan','prespec'].includes(stage)||!['servc','thng'].includes(kind)||
    !/^[A-Za-z0-9_.:-]{1,120}$/.test(id))return '';
 return 'g2b-prebid-'+stage+'-'+kind+'-'+id;
}
function prebidKeepSource(id){
 const match=String(id||'').match(/^g2b-prebid-(plan|prespec)-(servc|thng)-(.+)$/);
 if(!match)return null;
 return prebidCache[match[1]].items.find(x=>x.kind===match[2]&&prebidKeepId(x)===id)||null;
}
const prebidVisibleKeptRows=new Map();
function prebidKeepSnapshotFor(id){
 const x=prebidKeepSource(id);
 if(!x)return prebidVisibleKeptRows.get(id)||null;
 const name=x.stage==='plan'?'발주계획':'사전규격';
 const url=String(x.url||'');
 return {
  title:String(x.title||'(사업명 없음)'),
  url:/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(url)?url:'',
  org:String(x.org||'발주기관 미기재'),
  amount:prebidWon(x.budget),
  deadline:x.stage==='plan'?'발주예정 '+(x.plannedMonth||'시기 미기재'):
   '의견마감 '+(x.opinionDeadline||'미기재'),
  entry:'business',type:name,noticeNumber:String(x.id)
 };
}
function prebidKeepJobFromId(id){
 const snapshot=prebidKeepSnapshotFor(id);
 if(!snapshot)return null;
 const match=id.match(/^g2b-prebid-(plan|prespec)-(servc|thng)-/);
 return {...snapshot,id,kind:match[2],period:snapshot.deadline};
}
// Kept prebid rows remain prebid cards. Never invent an electronic bid close.
function prebidKeptCardMarkup(x){
 const match=String(x?.id||'').match(/^g2b-prebid-(plan|prespec)-(servc|thng)-(.+)$/);
 if(!match)return '';
 prebidVisibleKeptRows.set(x.id,x);
 const name=match[1]==='plan'?'발주계획':'사전규격';
 const url=String(x.url||'');
 const safe=/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(url)?url:'';
 const keep=typeof window!=='undefined'?(window.worklinksKeeps?.keepButton(x.id)||''):'';
 return '<article class="card" data-prebid-id="'+htmlEscape(match[3])+
  '" data-job-card="'+htmlEscape(x.id)+'" tabindex="0" aria-label="'+htmlEscape(x.title||'공고 상세보기')+'"><div class="cardtop">'+
  '<span class="tag">'+name+'</span><span class="tag">'+(match[2]==='servc'?'용역':'물품')+'</span></div>'+
  '<h3><button class="job-card-title" type="button" data-job-detail="'+htmlEscape(x.id)+'">'+
   htmlEscape(x.title||'(사업명 없음)')+'</button></h3>'+
  '<p>'+htmlEscape(x.org||'발주기관 미기재')+'</p>'+
  '<p><strong>'+htmlEscape(x.amount||'예산 미기재')+'</strong> · '+
  htmlEscape(x.period||x.deadline||(match[1]==='plan'?'발주 예정':'의견마감 미기재'))+'</p>'+
  '<div class="prebid-keep-actions">'+keep+
  (safe?'<a data-external-source="1" href="'+htmlEscape(safe)+'" target="_blank" rel="noopener noreferrer">원문 보기</a>':
   '<span class="tag">등록번호 '+htmlEscape(x.noticeNumber||match[3])+'</span>')+
  '</div></article>';
}
// Shared cards keep their exact stage label in unified and per-stage results.
function prebidNoticeCardMarkup(x){
 const stage=x.stage,name=stage==='plan'?'발주계획':'사전규격';
 const url=String(x.url||'');
 const safe=/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(url)?url:'';
 const fileLinks=(x.files||[]).filter(y=>/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(y)).slice(0,4);
 const cardId=prebidKeepId(x);
 return '<article class="card prebid-job-card" data-prebid-id="'+htmlEscape(x.id)+
  '" data-job-card="'+htmlEscape(cardId)+'" tabindex="0" aria-label="'+htmlEscape(x.title||'공고 상세보기')+'"><div class="cardtop">'+
   '<span class="tag">'+htmlEscape(name)+'</span><span class="tag">'+htmlEscape(x.kind==='servc'?'용역':'물품')+'</span></div>'+
   '<h3><button class="job-card-title" type="button" data-job-detail="'+htmlEscape(cardId)+'">'+
    htmlEscape(x.title||'(사업명 없음)')+'</button></h3>'+
   '<p>'+htmlEscape(x.org||'발주기관 미기재')+' · '+htmlEscape(x.posted||'등록일 미기재')+'</p>'+
   '<p><strong>'+htmlEscape(prebidWon(x.budget))+'</strong> · '+
   htmlEscape(stage==='plan'?'예정 '+(x.plannedMonth||'시기 미기재'):'의견마감 '+(x.opinionDeadline||'미기재'))+'</p>'+
   '<div class="prebid-keep-actions">'+
   (typeof window!=='undefined'?(window.worklinksKeeps?.keepButton(prebidKeepId(x))||''):'')+
   (safe?'<a data-external-source="1" href="'+htmlEscape(safe)+'" target="_blank" rel="noopener noreferrer">원문 보기</a>':
   '<span class="tag">등록번호 '+htmlEscape(x.id||'미기재')+'</span>')+
   (fileLinks.length?' · '+fileLinks.map((url,i)=>'<a data-external-source="1" href="'+htmlEscape(url)+'" target="_blank" rel="noopener noreferrer">규격서 '+(i+1)+'</a>').join(' · '):'')+
   (x.bidLinked?' <span class="tag">입찰공고 연결됨</span>':'')+'</div></article>';
}
function prebidVerifiedShareUrl(stage,id){
 // Preserve the existing published KakaoTalk/OG pages, without placing
 // misleading duplicate share controls on every thumbnail.
 const featured=new Set(['R26BD00301798','R26BD00303409','R26BD00302593','R26BD00301029']);
 return stage==='prespec'&&featured.has(String(id))?'./share/'+encodeURIComponent(id)+'/':'';
}
function renderPrebidSourceDetail(item){
 const key=String(item?.id||'');
 const match=key.match(/^g2b-prebid-(plan|prespec)-(servc|thng)-([A-Za-z0-9_.:-]{1,120})$/);
 if(!match)return false;
 // Keep snapshots may open before the saved stage list finishes loading.
 // Even without that list, never fall through into the ordinary bid renderer.
 const row=prebidKeepSource(key)||{id:match[3],stage:match[1],kind:match[2],
  title:item.title,org:item.org,posted:item.startAt||'',budget:item.amount||'',
  url:item.url||'',files:[],plannedMonth:'',opinionDeadline:''};
 const stage=row.stage==='plan'?'발주계획':'사전규격';
 const safeUrl=url=>/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(String(url||''));
 const external=safeUrl(row.url)?row.url:'';
 const fileLinks=(Array.isArray(row.files)?row.files:[]).filter(safeUrl).slice(0,8);
 const number=String(row.id||''),org=String(row.org||'발주기관 미기재');
 const subject=String(row.subject||'').trim();
 const share=prebidVerifiedShareUrl(row.stage,number);
 const meta=(label,value)=>'<div class="job-detail-meta-item"><span>'+label+'</span><strong>'+
  htmlEscape(String(value||'미기재'))+'</strong></div>';
 document.getElementById('jobDetailTitle').textContent=String(row.title||'(사업명 없음)');
 document.getElementById('jobDetailSub').textContent=org+' · '+stage+' · 등록번호 '+number;
 const when=stage==='발주계획'?'발주예정 '+(row.plannedMonth||'시기 미기재'):
  '의견마감 '+(row.opinionDeadline||'미기재');
 const files=fileLinks.length?'<section class="job-detail-section"><h3>공식 규격서 링크</h3>'+
  '<div class="job-source-files">'+fileLinks.map((url,i)=>
   '<a class="job-source-file" href="'+htmlEscape(url)+'" target="_blank" rel="noopener noreferrer">'+
   '규격서 '+(i+1)+' 열기 ↗</a>').join('')+'</div></section>':'';
 const source=external?'<a class="job-external-link" href="'+htmlEscape(external)+
  '" target="_blank" rel="noopener noreferrer">나라장터 원문 열기 ↗</a>':
  '<span class="job-detail-secondary">나라장터 원문 직접 주소 미확인 · 등록번호 '+htmlEscape(number)+'</span>';
 document.getElementById('jobDetailBody').innerHTML=
  '<div class="job-detail-overview"><div class="job-detail-status">'+
   '<span class="jobmatch-chip pending">'+stage+' · 입찰조건 미확정</span></div>'+
   '<div class="job-detail-meta-grid">'+meta('사업예산',prebidWon(row.budget))+
    meta('발주기관',org)+meta('등록일',row.posted)+meta('등록번호',number)+
    meta(stage==='발주계획'?'발주시기':'의견등록',when)+'</div></div>'+
  '<section class="job-detail-section"><h3>공고 확인</h3><p>'+
   '나라장터 저장 DB 기준 '+stage+' 자료입니다. 입찰공고 마감일·낙찰방식·최종 참가자격을 의미하지 않습니다.'+
   '</p></section>'+
  (subject?'<section class="job-detail-section"><h3>사업 개요</h3><p>'+htmlEscape(subject)+'</p></section>':'')+files+
  '<div class="job-detail-actions">'+
  (share?'<a class="job-detail-secondary" href="'+htmlEscape(share)+'" target="_blank" rel="noopener noreferrer">공유</a>':'')+
  source+'</div>';
 return true;
}
function combinedBidCardMarkup(x){
 const link=String(jobOriginUrl(x)||'');
 const safe=/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(link)?link:'';
 const when=String(x.endAt||'');
 return '<article class="card" data-combined-bid="'+htmlEscape(x.id)+
  '" data-job-card="'+htmlEscape(x.id)+'" tabindex="0" aria-label="'+htmlEscape(x.title||'공고 상세보기')+'">'+
  '<div class="cardtop"><span class="tag">입찰공고</span>'+
  '<span class="tag">'+htmlEscape(x.kind==='thng'?'물품':x.kind==='servc'?'용역':'공사')+'</span></div>'+
  '<h3><button class="job-card-title" data-job-detail="'+htmlEscape(x.id)+'" type="button">'+
   htmlEscape(x.title||'(공고명 없음)')+'</button></h3>'+
  '<p>'+htmlEscape(x.org||'발주기관 미기재')+' · '+htmlEscape(x.startAt||'등록일 미기재')+'</p>'+
  '<p><strong>'+htmlEscape(jobAmountLabel(x.amount))+'</strong> · '+
   htmlEscape(when?'입찰마감 '+when:'입찰마감 원문 확인 필요')+'</p>'+
  '<div class="prebid-keep-actions">'+
  (typeof window!=='undefined'?(window.worklinksKeeps?.keepButton(x.id)||''):'')+
  (safe?'<a data-external-source="1" href="'+htmlEscape(safe)+'" target="_blank" rel="noopener noreferrer">원문 보기</a>':'')+
  (String(x.noticeNumber||'')==='R26BK01843011'?
   ' · <a data-external-source="1" href="./share/R26BK01843011/" title="WORKLINK 공고 공유">공유 링크</a>':'')+
  '</div></article>';
}
// The unified view is a real union, never a selected-stage search in disguise.
// A source still loading or errored is marked partial rather than showing "0".
function combinedProcurementRows(){
 const normalized=jobSearchNormalized(String(jobSearchText||''));
 const keep= x=>partnerSwScope==='all'||(partnerSwScope==='sw'?partnerSwRelated(x):swBuildTitle(x));
 const bidMap=new Map();
 // The server's complete keyword result is authoritative for bid matches.
 // When that search is unavailable, partially loaded local rows are fallback.
 const fromKeyword=normalized.length>=2&&jobSearchServerTotal!==null&&!jobSearchRemoteLoading;
 const candidates=fromKeyword?jobSearchRemote:partnerAllBids.items;
 for(const x of candidates){
  if(x?.id&&/^g2b-(servc|thng|cnstwk|frgcpt)-/.test(x.id))bidMap.set(x.id,x);
 }
 const result=[],counts={bid:0,plan:0,prespec:0};
 for(const x of bidMap.values()){
  if(!keep(x)||normalized&&!jobSearchNormalized([x.title,x.org,x.id,x.noticeNumber,x.subject,x.type].join(' ')).includes(normalized))continue;
  if(!normalized&&typeof jobPartnerShowClosed==='boolean'&&
     (jobTimeInfo(x).key==='closed')!==jobPartnerShowClosed)continue;
  result.push({stage:'bid',row:x,posted:String(x.startAt||'')});counts.bid++;
 }
 for(const stage of ['plan','prespec']){
  if(!normalized&&typeof jobPartnerShowClosed==='boolean'&&jobPartnerShowClosed)continue;
  if(prebidCache[stage].state!=='ready')continue;
  for(const x of prebidCache[stage].items){
   if(!keep(x)||normalized&&!jobSearchNormalized([x.title,x.org,x.id,x.subject,x.productName].join(' ')).includes(normalized))continue;
   result.push({stage,row:x,posted:String(x.posted||'')});counts[stage]++;
  }
 }
 const sort=document.getElementById('jobSort')?.value||'recent';
 const budget=item=>Number(item.stage==='bid'?item.row.amount:item.row.budget)||0;
 result.sort((a,b)=>(sort==='budget'?budget(b)-budget(a):0)||
  b.posted.localeCompare(a.posted)||String(a.row.id).localeCompare(String(b.row.id)));
 return {result,counts};
}
function renderCombinedProcurementJobs(el){
 const info=combinedProcurementRows(),rows=info.result,counts=info.counts;
 const term=String(jobSearchText||'').trim();
 const searchingBid=term.length>=2;
 const fullBid=searchingBid?(jobSearchServerTotal!==null&&!jobSearchRemoteLoading):
  partnerAllBids.state==='ready'&&partnerAllBids.loaded>=partnerAllBids.total;
 const incomplete=!fullBid||
  ['plan','prespec'].some(stage=>prebidCache[stage].state!=='ready');
 const names={plan:'발주계획',prespec:'사전규격'};
 const failures=['plan','prespec'].filter(stage=>prebidCache[stage].state==='error')
  .map(stage=>names[stage]+' 조회 실패 · '+String(prebidCache[stage].error||''));
 if(partnerAllBids.state==='error')failures.unshift('입찰공고 조회 실패 · '+String(partnerAllBids.error||''));
 if(jobSearchRemoteError)failures.unshift('입찰공고 키워드 검색 실패 · '+jobSearchRemoteError);
 const types='입찰공고 '+counts.bid+' · 발주계획 '+counts.plan+' · 사전규격 '+counts.prespec;
 const count=document.getElementById('partnerJobCount');
 if(count)count.textContent=rows.length+'건'+(incomplete?' · 일부':'');
 const summary=document.getElementById('partnerSummary');
 if(summary)summary.textContent=types+(incomplete?' · 수집된 목록 일부만 표시 중':'')+
  (term?' · 세 단계 통합 키워드 검색':' · 등록 최신순');
 const detail=document.getElementById('jobDecisionSummary');
 if(detail)detail.textContent=incomplete?
  '입찰공고 '+(searchingBid?(jobSearchServerTotal===null?'검색 결과 미확인':jobSearchRemote.length+' / '+jobSearchServerTotal+'건 검색'):
   partnerAllBids.loaded+' / '+partnerAllBids.total+'건 저장 DB 확인 (필요 시 더 보기)')+' · '+
  ['plan','prespec'].map(stage=>names[stage]+' '+(prebidCache[stage].state==='ready'?prebidCache[stage].total+'건 확인':'조회 '+prebidCache[stage].state)).join(' · '):
  '입찰공고·발주계획·사전규격 통합 목록 확인 완료 · '+types;
 for(const id of ['jobMissingInfo'])document.getElementById(id)?.replaceChildren();
 const filter=document.getElementById('jobVerdictFilter');if(filter)filter.hidden=true;
 const closed=document.getElementById('closedJobCount');if(closed)closed.textContent='';
 const visible=Math.max(20,jobRenderLimit||40);
 jobAvailableRows=rows.length;
 el.innerHTML=rows.slice(0,visible).map(item=>item.stage==='bid'?
  combinedBidCardMarkup(item.row):prebidNoticeCardMarkup(item.row)).join('')+
  (!rows.length&&!incomplete?'<div class="emptycard">세 종류의 저장 공고에서 검색 결과가 없습니다.</div>':'')+
  (incomplete?'<div class="emptycard">입찰공고·발주계획·사전규격 통합 조회 일부 미확인'+
    (failures.length?' · '+htmlEscape(failures.join(' / ')):'')+
    (failures.length?' <button type="button" id="combinedRetry" class="job-vf">다시 조회</button>':'')+'</div>':'');
 const more=document.getElementById('g2bMore');
 if(more){
  more.style.display=rows.length>visible||(!searchingBid&&partnerAllBids.loaded<partnerAllBids.total)?'inline-block':'none';
  more.textContent=rows.length>visible?'공고 '+visible+' / '+rows.length+'건 · 더 보기':
   '입찰공고 저장 DB '+partnerAllBids.loaded+' / '+partnerAllBids.total+'건 · 다음 조회';
 }
 if(typeof scheduleWorklinksShareOpen==='function')scheduleWorklinksShareOpen();
 el.querySelector('#combinedRetry')?.addEventListener('click',()=>{
  for(const stage of ['plan','prespec'])if(prebidCache[stage].state==='error')void loadPrebidJobs(stage,true);
  if(partnerAllBids.state==='error')void loadPartnerAllBids(partnerAllBids.loaded>0);
 });
}
function renderPrebidJobs(el){
 const stage=partnerNoticeStage,report=prebidCache[stage],name=stage==='plan'?'발주계획':'사전규격';
 const summary=document.getElementById('partnerSummary'),decision=document.getElementById('jobDecisionSummary');
 if(summary)summary.textContent='';
 if(decision)decision.textContent='';
 const more=document.getElementById('g2bMore');if(more)more.style.display='none';
 const filt=document.getElementById('jobVerdictFilter');if(filt)filt.hidden=true;
 const count=document.getElementById('partnerJobCount');
 const message=report.state==='loading'?'불러오는 중':report.state==='error'?'수집 확인 필요':report.state==='idle'?'조회 전':'';
 if(report.state!=='ready'){
  if(count)count.textContent='확인 중';
  const detail=/prebid_official_http_403/.test(report.error)?'공식 API 접근 거부(403) · 해당 서비스 활용승인 확인 필요':
   /prebid_official_http_429/.test(report.error)?'공식 API 요청 제한(429)':
   /prebid_daily_request_budget_exhausted/.test(report.error)?'오늘의 수집 한도 도달':
   report.error;
  el.innerHTML='<div class="emptycard">'+htmlEscape(name)+' · '+htmlEscape(message)+
   (report.state==='error'?' ('+htmlEscape(detail)+')':'')+
   ' <button type="button" id="prebidRetry" class="job-vf">다시 조회</button></div>';
  el.querySelector('#prebidRetry')?.addEventListener('click',()=>void loadPrebidJobs(stage,true));
  return;
 }
 const word=jobSearchNormalized(jobSearchText);
 let rows=report.items.filter(x=>partnerSwScope==='all'||
  (partnerSwScope==='sw'?partnerSwRelated(x):swBuildTitle(x)));
 if(word)rows=rows.filter(x=>jobSearchNormalized([x.title,x.org,x.id].join(' ')).includes(word));
 rows.sort((a,b)=>String(b.posted||'').localeCompare(String(a.posted||'')));
 if(count)count.textContent=rows.length+'건';
 if(!rows.length){el.innerHTML='<div class="emptycard">'+htmlEscape(name)+' · 현재 저장된 자료에 해당 조건의 공고가 없습니다. ('+
  '저장된 공고 '+report.total.toLocaleString('ko-KR')+'건)</div>';return}
 const visible=Math.max(20,jobRenderLimit||40);
 el.innerHTML=rows.slice(0,visible).map(prebidNoticeCardMarkup).join('')+
  (rows.length>visible?'<button type="button" id="prebidMore" class="job-vf">목록 '+visible.toLocaleString('ko-KR')+
  ' / '+rows.length.toLocaleString('ko-KR')+'건 · 더 보기</button>':'');
 if(typeof scheduleWorklinksShareOpen==='function')scheduleWorklinksShareOpen();
 el.querySelector('#prebidMore')?.addEventListener('click',()=>{
  jobRenderLimit+=jobPageStep();renderJobs();
 });
}

// The initial failed page is retried automatically after connectivity returns.
// Keep existing failed-state banner until real DB pages have been read fully.
function recoverVisiblePrebidAfterFailure(){
 if(typeof document==='undefined'||document.hidden||!worklinksPartnerAccess()||!worklinksIsChangcomView())return;
 for(const stage of ['plan','prespec']){
  if(prebidCache[stage].state==='error'&&(partnerNoticeStage===stage||partnerNoticeStage==='all'))
   void loadPrebidJobs(stage,true);
 }
}
if(typeof window!=='undefined'){
 window.addEventListener?.('online',recoverVisiblePrebidAfterFailure);
 window.addEventListener?.('focus',recoverVisiblePrebidAfterFailure);
 window.setInterval?.(recoverVisiblePrebidAfterFailure,45000);
}
