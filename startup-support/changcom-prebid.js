/* Changcom: source-backed procurement stage and SW award filters.
 * Existing bid records require no new G2B requests; prebid reads local server DB.
 */
let partnerSwScope='all', partnerAwardFilter='all', partnerNoticeStage='bid';
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
 const sw=/(소프트웨어|정보.?시스템|전산.?시스템|통합.?시스템|업무.?시스템|행정.?시스템|관리.?시스템|플랫폼|웹사이트|웹서비스|홈페이지|모바일.?앱|애플리케이션|데이터베이스|클라우드|인공지능|전자결재|전자문서|전자정부|erp|crm|\bsw\b|s\/w)/i.test(text);
 const possible=/(시스템|전산|정보화|디지털|데이터|인터넷|웹|앱|자동화|ai\b|ict\b)/i.test(text);
 const noSw=/(전산.?소모품|토너|프린터.?소모품|사무용.?품|사무.?가구|청소.?용역|정보화.?교육|컴퓨터.?교육|전산.?교육|교육.?운영)/i.test(title);
 const equipment=/(서버|컴퓨터|프린터|복합기|스캐너|모니터|전산.?장비|기자재|cctv).{0,15}(구매|구입|납품|교체)/i.test(title);
 const onlyOperate=/(유지.?관리|유지.?보수|운영.?지원|정기.?점검|기술.?지원)/i.test(title)&&!dev;
 const onlyPurchase=/(라이선스|라이센스|솔루션.?구매|소프트웨어.?구매|구독.?서비스)/i.test(title)&&!dev;
 const onlyPlan=/(마스터.?플랜|isp\b|ismp\b|타당성.?조사|구축.?방안.?연구)/i.test(title)&&!dev;
 const code=productCode==='8111159901'||/8111159901/.test(String(x?.subject||''));
 const software=(official||code||sw||(possible&&dev))&&!(noSw&&!dev)&&!(equipment&&!dev&&!official&&!code);
 // 8111159901 can describe maintenance too: the code is a candidate, not proof.
 const build=software&&!noSw&&!onlyOperate&&!onlyPurchase&&!onlyPlan&&
   (dev||official||code||sw);
 return {software,build,review:build&&!dev};
}
function swBuildTitle(x){return partnerSoftwareSignals(x).build}
function partnerSwRelated(x){return partnerSoftwareSignals(x).software}
function partnerBidMatchesNewFilters(x){
 if(partnerSwScope==='build'&&!swBuildTitle(x))return false;
 if(partnerSwScope==='sw'&&!partnerSwRelated(x))return false;
 if(partnerAwardFilter==='all')return true;
 if(!/^g2b-/.test(String(x?.id||'')))return false;
 const m=g2bCardAwardMetadata(x);
 if(!m.sourceVerified)return false; // never infer an award method from title
 const code=String(m.awardMethodCode||'');
 switch(partnerAwardFilter){
 case 'price':return PRICE_METHODS.has(code);
 case 'qualification':return code==='낙030001';
 case 'spec-price':return SPEC_PRICE_METHODS.has(code);
 case 'negotiation':return code==='낙030005';
 default:return true;
 }
}
// The full tender corpus is read from existing saved SQLite only. It must not
// replace the SW-only dataset used by the unrelated general jobs workspace.
const partnerAllBids={items:[],total:0,loaded:0,state:'idle',error:''};
async function loadPartnerAllBids(more=false){
 if(!worklinksPartnerAccess()||!worklinksIsChangcomView()||
    partnerNoticeStage!=='bid')return;
 if(partnerAllBids.state==='loading')return;
 if(!more&&partnerAllBids.state==='ready'){
  if(partnerSwScope==='all'||partnerAllBids.loaded>=partnerAllBids.total)return;
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
  if(worklinksIsChangcomView()&&partnerNoticeStage==='bid'){
   renderJobs();
   if(partnerSwScope!=='all'&&partnerAllBids.state==='ready'&&partnerAllBids.loaded<partnerAllBids.total)
    void loadPartnerAllBids(true);
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
   const res=await g2bFetch('/prebid?stage='+stage+'&limit=500&offset='+offset);
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
 }finally{if(partnerNoticeStage===stage)renderJobs()}
}
function prebidWon(value){
 const n=Number(value);
 if(!Number.isFinite(n)||n<=0)return '예산 미기재';
 return n>=1e8?Number((n/1e8).toFixed(2)).toLocaleString('ko-KR')+'억 원':
  Math.round(n/10000).toLocaleString('ko-KR')+'만원';
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
 el.innerHTML=rows.slice(0,visible).map(x=>{
  const url=String(x.url||'');
  const safe=/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(url)?url:'';
  const fileLinks=(x.files||[]).filter(y=>/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(y)).slice(0,4);
  return '<article class="card" data-prebid-id="'+htmlEscape(x.id)+'"><div class="cardtop">'+
   '<span class="tag">'+htmlEscape(name)+'</span><span class="tag">'+htmlEscape(x.kind==='servc'?'용역':'물품')+'</span></div>'+
   '<h3>'+htmlEscape(x.title||'(사업명 없음)')+'</h3>'+
   '<p>'+htmlEscape(x.org||'발주기관 미기재')+' · '+htmlEscape(x.posted||'등록일 미기재')+'</p>'+
   '<p><strong>'+htmlEscape(prebidWon(x.budget))+'</strong> · '+
   htmlEscape(stage==='plan'?'예정 '+(x.plannedMonth||'시기 미기재'):'의견마감 '+(x.opinionDeadline||'미기재'))+'</p>'+
   (safe?'<a href="'+htmlEscape(safe)+'" target="_blank" rel="noopener noreferrer">원문 보기</a>':
   '<span class="tag">등록번호 '+htmlEscape(x.id||'미기재')+'</span>')+
   (fileLinks.length?' · '+fileLinks.map((url,i)=>'<a href="'+htmlEscape(url)+'" target="_blank" rel="noopener noreferrer">규격서 '+(i+1)+'</a>').join(' · '):'')+
   (x.bidLinked?' <span class="tag">입찰공고 연결됨</span>':'')+'</article>';
 }).join('')+
  (rows.length>visible?'<button type="button" id="prebidMore" class="job-vf">목록 '+visible.toLocaleString('ko-KR')+
  ' / '+rows.length.toLocaleString('ko-KR')+'건 · 더 보기</button>':'');
 el.querySelector('#prebidMore')?.addEventListener('click',()=>{
  jobRenderLimit+=jobPageStep();renderJobs();
 });
}
