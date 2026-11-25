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
// An exact number uses one saved-DB lookup; never fetch all 10K+ records for one ID.
const prebidExactCache={stage:'',id:'',serial:0,state:'idle',items:[],total:0,error:'',at:''};
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
// A full prebid snapshot is atomic: never throw away the last complete
// records because one of ~20 pages suffers a temporary connection failure.
const PREBID_READ_RETRY_DELAYS=[500,1300,2800];
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
async function loadPrebidExact(stage,id,force=false){
 if(stage!=='prespec'||!/^R\d{2}BD\d{8}$/.test(id)||!worklinksPartnerAccess())return;
 if(!force&&prebidExactCache.stage===stage&&prebidExactCache.id===id&&
    ['loading','ready'].includes(prebidExactCache.state))return;
 const serial=++prebidExactCache.serial;
 Object.assign(prebidExactCache,{stage,id,state:'loading',error:'',items:[],total:0,at:''});
 if(partnerNoticeStage===stage)renderJobs();
 try{
  const result=await g2bFetch('/prebid?stage='+stage+'&q='+encodeURIComponent(id)+'&limit=10&offset=0');
  if(result?.ok!==true||result?.ready!==true)
   throw Error(result?.error||'사전규격 저장 자료 접근 불가');
  if(result.exactLookup!==true)
   throw Error('서버의 공고번호 단건조회 API가 아직 배포되지 않았습니다');
  if(!Array.isArray(result.items)||!Number.isSafeInteger(Number(result.total))||
     result.items.length!==Number(result.total)||result.items.some(x=>x.id!==id))
   throw Error('공고번호 단건조회 응답 불완전');
  if(serial!==prebidExactCache.serial)return;
  Object.assign(prebidExactCache,{state:'ready',items:result.items,total:Number(result.total),at:result.asOf||''});
 }catch(error){
  if(serial!==prebidExactCache.serial)return;
  Object.assign(prebidExactCache,{state:'error',error:String(error?.message||error).slice(0,180)});
 }finally{
  if(serial===prebidExactCache.serial&&partnerNoticeStage===stage)renderJobs();
 }
}
async function prebidReadCompleteStage(stage){
 const first=await prebidReadPageWithRetry(stage,0);
 if(!first||first.ok!==true)throw Error(first?.error||'사전 단계 목록 응답 오류');
 if(!first.ready)throw Error(first.error||'사전 단계 수집 자료 없음');
 const total=Number(first.total);
 if(!Number.isSafeInteger(total)||total<0||total>100000||
    !Array.isArray(first.items)||first.items.length!==Math.min(total,500))
  throw Error('사전 단계 첫 페이지 불완전');
 const results=[first],offsets=[];
 for(let offset=500;offset<total;offset+=500)offsets.push(offset);
 let cursor=0;
 async function worker(){
  while(cursor<offsets.length){
   const index=cursor++,offset=offsets[index];
   const page=await prebidReadPageWithRetry(stage,offset);
   if(!page||page.ok!==true||page.ready!==true||
      Number(page.total)!==total||!Array.isArray(page.items)||
      page.items.length!==Math.min(500,total-offset))
    throw Error('사전 단계 페이지 조회 중 자료 변경 또는 누락');
   results[index+1]=page;
  }
 }
 await Promise.all(Array.from({length:Math.min(4,offsets.length)},()=>worker()));
 const items=results.flatMap(page=>page.items);
 if(items.length!==total)throw Error('사전 단계 전체 목록 일부 누락');
 return {items,total,at:first.asOf||''};
}
async function loadPrebidJobs(stage,force=false){
 if(!['plan','prespec'].includes(stage)||!worklinksPartnerAccess())return;
 const exactId=String(jobSearchText||'').trim().toUpperCase();
 if(stage==='prespec'&&partnerNoticeStage===stage&&/^R\d{2}BD\d{8}$/.test(exactId)){
  void loadPrebidExact(stage,exactId,force);return;
 }
 const state=prebidCache[stage];
 if(state.state==='loading')return;
 if(!force&&state.state==='ready'&&Date.now()-Number(state.cachedAt||0)<60000)return;
 const hadComplete=state.state==='ready'&&Array.isArray(state.items);
 state.state='loading';state.refreshing=hadComplete;state.error='';
 if(!hadComplete)renderJobs();
 try{
  const complete=await prebidReadCompleteStage(stage);
  state.items=complete.items;state.total=complete.total;state.at=complete.at;
  state.state='ready';state.cachedAt=Date.now();state.staleError='';
 }catch(err){
  const error=String(err?.message||err).slice(0,160);
  if(hadComplete){
   state.state='ready';state.staleError=error;
   state.cachedAt=Date.now()-45000;
  }else{
   state.state='error';state.error=error;
  }
 }finally{
  state.refreshing=false;
  if(partnerNoticeStage===stage||partnerNoticeStage==='all')renderJobs();
 }
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
// Keep stage-specific government pages separate from download links.
// The G2B prespec SPA route (PRVA004_02) is a candidate deep-link: live
// browser robots can return only an empty shell. Always expose an independent
// official search path, and never describe a downloaded file as the detail page.
function prebidOfficialDetailUrl(x){
 const id=String(x?.id||'').trim().toUpperCase();
 if(x?.stage==='plan'&&/^R\d{2}DD\d{8}$/.test(id))
  return 'https://www.g2b.go.kr/link/PRPA015_01/single/?oderPlanNo='+encodeURIComponent(id);
 if(x?.stage==='prespec'&&/^R\d{2}BD\d{8}$/.test(id))
  return 'https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo='+encodeURIComponent(id);
 return '';
}
function prebidOfficialSearchUrl(x){
 if(x?.stage!=='prespec')return '';
 const id=String(x?.id||'').trim().toUpperCase();
 if(!/^R\d{2}BD\d{8}$/.test(id))return '';
 return 'https://www.g2b.go.kr/link/PRCA001_04/single/?flag=cnrtSl&srch=0002&bfSpecRegNo='+
   encodeURIComponent(id)+'&srchPreStdRgstNo='+encodeURIComponent(id);
}
// Match the original tender card action exactly. Never substitute a file URL
// for the government notice and never scatter additional lookup actions on cards.
function prebidSourceMarkup(x){
 const direct=prebidOfficialDetailUrl(x);
 const source=direct||prebidOfficialSearchUrl(x);
 if(!source)return '';
 const title=String(x?.title||'공고');
 const label=direct?'공고 원문 ↗':'나라장터 검색 ↗';
 return '<a class="job-source-link" href="'+htmlEscape(source)+
  '" target="_blank" rel="noopener noreferrer" data-external-source="1"'+
  ' aria-label="'+htmlEscape(title)+' '+(direct?'공고 원문':'나라장터 검색')+'을 새 탭에서 열기"'+
  ' title="'+(direct?'공고 원문 새 탭에서 열기':'등록번호로 나라장터 검색')+'">'+label+'</a>';
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
// Same card hierarchy, source-link placement and keep behavior as an
// ordinary bid. Stage-only fields stay explicitly labeled; do not fabricate
// deadlines, eligibility checks, competition or award details.
function prebidUnifiedCardMarkup(x,cardId){
 const stage=x.stage==='plan'?'plan':'prespec';
 const stageLabel=stage==='plan'?'발주계획':'사전규격';
 const kind=x.kind==='thng'?'물품':'용역';
 const budget=Number(x.budget)>0?prebidWon(x.budget):String(x.amount||'예산 미기재');
 const deadline=stage==='plan'?'발주예정 '+String(x.plannedMonth||'시기 미기재'):
  '의견마감 '+String(x.opinionDeadline||'미기재');
 const when=stage==='plan'?(x.plannedMonth?deadline:String(x.period||x.deadline||deadline)):
  (x.opinionDeadline?deadline:String(x.period||x.deadline||deadline));
 const posted=String(x.posted||x.startAt||'').trim();
 const id=String(cardId||prebidKeepId(x));
 const keep=typeof window!=='undefined'?(window.worklinksKeeps?.keepButton(id)||''):'';
 return '<article class="card job-mini prebid-job-card" data-prebid-id="'+htmlEscape(x.id)+
  '" data-job-card="'+htmlEscape(id)+'" tabindex="0" aria-label="'+htmlEscape(x.title||'공고')+' 상세보기">'+
  '<div class="job-day upcoming"><strong>'+stageLabel+'</strong>'+
   '<span class="job-date">'+htmlEscape(when)+'</span></div>'+
  '<div class="job-core">'+
   '<div class="job-headline"><h3><button class="job-card-title" data-job-detail="'+htmlEscape(id)+
    '" type="button">'+htmlEscape(x.title||'(사업명 없음)')+'</button></h3>'+
    '<div class="job-headline-side"><div class="job-headline-badge">'+
    '<span class="tag">'+stageLabel+'</span><span class="tag">'+kind+'</span>'+
    '</div><span class="job-amount">'+htmlEscape(budget)+'</span></div></div>'+
   '<div class="job-meta-row"><span class="job-agency">'+htmlEscape(x.org||'발주기관 미기재')+
    '</span> · '+htmlEscape(posted?'등록 '+posted:'등록일 미기재')+'</div>'+
   '<div class="job-eligibility-row"><div class="job-eligibility-content">'+
    '<span class="job-basic-signal">'+(stage==='plan'?'입찰공고 이전 · 발주예정':'입찰공고 이전 · 의견접수')+
    '</span></div></div>'+
   '<div class="job-highlights"><div class="job-highlight-tags">'+
    (x.bidLinked?'<span class="tag">후속 입찰공고 연결됨</span>':'')+
    '</div>'+keep+prebidSourceMarkup(x)+'</div>'+
  '</div></article>';
}
function prebidKeptCardMarkup(x){
 const match=String(x?.id||'').match(/^g2b-prebid-(plan|prespec)-(servc|thng)-(.+)$/);
 if(!match)return '';
 prebidVisibleKeptRows.set(x.id,x);
 const original=prebidKeepSource(x.id)||{...x,id:match[3],stage:match[1],kind:match[2]};
 return prebidUnifiedCardMarkup(original,x.id);
}
function prebidNoticeCardMarkup(x){
 return prebidUnifiedCardMarkup(x,prebidKeepId(x));
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
 // Reuse the normal jobDetailModal, header, overview, attachment rows
 // and bottom original-action style. A kept row may be present offline.
 const row=prebidKeepSource(key)||{id:match[3],stage:match[1],kind:match[2],
  title:item.title,org:item.org,posted:item.startAt||'',budget:item.amount||'',
  url:item.url||'',files:[],plannedMonth:'',opinionDeadline:''};
 const stage=row.stage==='plan'?'발주계획':'사전규격';
 const external=prebidOfficialDetailUrl(row),search=prebidOfficialSearchUrl(row);
 const fileLinks=prebidOfficialFileEntries(row,8);
 const number=String(row.id||''),org=String(row.org||'발주기관 미기재');
 const subject=String(row.subject||'').trim();
 const share=prebidVerifiedShareUrl(row.stage,number);
 const amount=Number(row.budget)>0?prebidWon(row.budget):String(row.amount||'예산 미기재');
 const when=stage==='발주계획'?'발주예정 '+(row.plannedMonth||'시기 미기재'):
  '의견마감 '+(row.opinionDeadline||'미기재');
 const meta=(label,value)=>'<div class="job-detail-meta-item"><span>'+label+'</span><strong>'+
  htmlEscape(String(value||'미기재'))+'</strong></div>';
 document.getElementById('jobDetailTitle').textContent=String(row.title||'(사업명 없음)');
 document.getElementById('jobDetailSub').textContent=org+' · '+stage+' · 등록번호 '+number;
 const overview='<div class="job-detail-overview"><div class="job-detail-status">'+
  '<span class="jobmatch-chip pending">'+stage+' · 입찰조건 미확정</span></div>'+
  '<div class="job-detail-meta-grid">'+meta('사업예산',amount)+
  meta('공고·모집 기간',when)+meta('등록번호',number)+
  meta('등록일',row.posted||'미기재')+'</div></div>';
 const files=fileLinks.length?'<section class="job-detail-section job-evidence-section">'+
  '<h3>공식 첨부파일</h3><div class="job-source-files">'+
  fileLinks.map(file=>'<a class="job-source-file" href="'+htmlEscape(file.url)+
   '" target="_blank" rel="noopener noreferrer"><span class="job-source-filename">'+
   htmlEscape(file.name||'첨부파일 내려받기')+'</span><span class="job-source-action">파일 열기 ↗</span></a>').join('')+
  '</div></section>':'';
 const lookup=search?'<details class="job-detail-advanced"><summary>나라장터에서 등록번호로 검색</summary>'+
  '<p><a href="'+htmlEscape(search)+'" target="_blank" rel="noopener noreferrer">'+
   htmlEscape(number)+' 검색 ↗</a></p></details>':'';
 const extras=share?'<section class="job-detail-section"><a href="'+htmlEscape(share)+
  '" target="_blank" rel="noopener noreferrer">공유 링크</a></section>':'';
 const link=external||search;
 const actions='<div class="job-detail-actions">'+(link?'<a class="job-external-link" href="'+
  htmlEscape(link)+'" target="_blank" rel="noopener noreferrer">'+
  (external?'원문 공고 열기 ↗':'나라장터에서 검색 ↗')+'</a>':'')+'</div>';
 document.getElementById('jobDetailBody').innerHTML=overview+
  (subject?'<section class="job-detail-section"><h3>사업 개요</h3><p>'+htmlEscape(subject)+'</p></section>':'')+
  files+extras+lookup+actions;
 queuePrebidFileMetadata([row]);
 return true;
}
function combinedBidCardMarkup(x){
 const link=String(jobOriginUrl(x)||'');
 const safe=/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(link)?link:'';
 const time=typeof jobTimeInfo==='function'?jobTimeInfo(x):null;
 const day=time&&typeof jobDayCounter==='function'?jobDayCounter(time):null;
 const dayClass=day?.kind||'unknown';
 const dayLabel=day?.label||'입찰공고';
 const deadline=time&&typeof jobDeadlineStamp==='function'?jobDeadlineStamp(time):String(x.endAt||'마감 확인 필요');
 return '<article class="card job-mini" data-combined-bid="'+htmlEscape(x.id)+
  '" data-job-card="'+htmlEscape(x.id)+'" tabindex="0" aria-label="'+htmlEscape(x.title||'공고')+' 상세보기">'+
  '<div class="job-day '+htmlEscape(dayClass)+'"><strong>'+htmlEscape(dayLabel)+
   '</strong><span class="job-date">'+htmlEscape(deadline)+'</span></div>'+
  '<div class="job-core"><div class="job-headline"><h3><button class="job-card-title"'+
   ' data-job-detail="'+htmlEscape(x.id)+'" type="button">'+htmlEscape(x.title||'(공고명 없음)')+
   '</button></h3><div class="job-headline-side"><div class="job-headline-badge">'+
   '<span class="tag">입찰공고</span><span class="tag">'+
   htmlEscape(x.kind==='thng'?'물품':x.kind==='servc'?'용역':'공사')+'</span></div>'+
   '<span class="job-amount">'+htmlEscape(jobAmountLabel(x.amount))+'</span></div></div>'+
   '<div class="job-meta-row"><span class="job-agency">'+htmlEscape(x.org||'발주기관 미기재')+
   '</span> · '+htmlEscape(x.startAt?'등록 '+x.startAt:'등록일 미기재')+'</div>'+
   '<div class="job-highlights"><div class="job-highlight-tags"></div>'+
    (typeof window!=='undefined'?(window.worklinksKeeps?.keepButton(x.id)||''):'')+
    (safe?'<a class="job-source-link" data-external-source="1" href="'+htmlEscape(safe)+
      '" target="_blank" rel="noopener noreferrer" aria-label="'+htmlEscape(x.title||'공고')+
      ' 공고 원문을 새 탭에서 열기" title="공고 원문 새 탭에서 열기">공고 원문 ↗</a>':'')+
   '</div></div></article>';
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
 const filter=document.getElementById('jobVerdictFilter');if(filter){filter.hidden=false;filter.classList?.add?.('job-sort-only');}
 const closed=document.getElementById('closedJobCount');if(closed)closed.textContent='';
 const visible=Math.max(20,jobRenderLimit||40);
 jobAvailableRows=rows.length;
 el.innerHTML=rows.slice(0,visible).map(item=>item.stage==='bid'?
  combinedBidCardMarkup(item.row):prebidNoticeCardMarkup(item.row)).join('')+
  (!rows.length&&!incomplete?'<div class="emptycard">세 종류의 저장 공고에서 검색 결과가 없습니다.</div>':'')+
  (incomplete?'<div class="emptycard">입찰공고·발주계획·사전규격 통합 조회 일부 미확인'+
    (failures.length?' · '+htmlEscape(failures.join(' / ')):'')+
    (failures.length?' <button type="button" id="combinedRetry" class="job-vf">다시 조회</button>':'')+'</div>':'');
 queuePrebidFileMetadata(rows.slice(0,visible).filter(item=>item.stage==='prespec').map(item=>item.row));
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
 const stage=partnerNoticeStage,name=stage==='plan'?'발주계획':'사전규격';
 let report=prebidCache[stage];
 const query=String(jobSearchText||'').trim().toUpperCase();
 const exactId=stage==='prespec'&&/^R\d{2}BD\d{8}$/.test(query)?query:'';
 if(exactId){
  if(prebidExactCache.stage!==stage||prebidExactCache.id!==exactId)
   void loadPrebidExact(stage,exactId);
  report=prebidExactCache;
 }else if(report.state==='idle'){
  void loadPrebidJobs(stage);
 }
 const summary=document.getElementById('partnerSummary'),decision=document.getElementById('jobDecisionSummary');
 if(summary)summary.textContent='';
 if(decision)decision.textContent='';
 const more=document.getElementById('g2bMore');if(more)more.style.display='none';
 const filt=document.getElementById('jobVerdictFilter');if(filt){filt.hidden=false;filt.classList?.add?.('job-sort-only');}
 const count=document.getElementById('partnerJobCount');
 const message=report.state==='loading'?'불러오는 중':report.state==='error'?'조회 연결 실패':report.state==='idle'?'조회 전':'';
 if(report.state!=='ready'&&!report.refreshing){
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
 const sort=document.getElementById('jobSort')?.value||'recent';
  rows.sort((a,b)=>(sort==='budget'?(Number(b.budget)||0)-(Number(a.budget)||0):0)||
   String(b.posted||'').localeCompare(String(a.posted||''))||String(a.id).localeCompare(String(b.id)));
 if(count)count.textContent=rows.length+'건'+(report.staleError?' · 이전 확인 자료':'');
 if(!rows.length){
  const reason=exactId?(report.items.length?
   '공고는 저장되어 있지만 현재 SW·개발 범위 필터에서 숨겨졌습니다. 범위를 전체 공고로 변경하세요.':
   '해당 번호는 서버 저장 DB에서 아직 조회되지 않습니다. 공식 공고가 없다는 뜻은 아니며 수집 지연·누락을 점검해야 합니다.'):
   name+' · 현재 저장된 자료에 해당 조건의 공고가 없습니다. (저장된 공고 '+
   report.total.toLocaleString('ko-KR')+'건)';
  el.innerHTML='<div class="emptycard">'+htmlEscape(reason)+
   (exactId?' <a href="https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo='+encodeURIComponent(exactId)+
    '" target="_blank" rel="noopener noreferrer">나라장터 원문 ↗</a>':'')+'</div>';
  return;
 }
 const visible=Math.max(20,jobRenderLimit||40);
 el.innerHTML=(report.staleError?'<div class="emptycard" role="status">'+
  '최신 조회 연결 실패 · 이전 전체 확인 자료 표시 ('+htmlEscape(report.staleError)+
  ') <button type="button" id="prebidStaleRetry" class="job-vf">다시 조회</button></div>':'')+
  rows.slice(0,visible).map(prebidNoticeCardMarkup).join('')+
  (rows.length>visible?'<button type="button" id="prebidMore" class="job-vf">목록 '+visible.toLocaleString('ko-KR')+
  ' / '+rows.length.toLocaleString('ko-KR')+'건 · 더 보기</button>':'');
 el.querySelector('#prebidStaleRetry')?.addEventListener('click',()=>void loadPrebidJobs(stage,true));
 queuePrebidFileMetadata(rows.slice(0,visible));
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
