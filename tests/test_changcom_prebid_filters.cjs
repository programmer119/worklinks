const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../startup-support/changcom-prebid.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const ctx={
  g2bCardAwardMetadata:x=>({awardMethodCode:x.awardMethodCode,sourceVerified:x.awardFieldsVerified===true}),
  worklinksPartnerAccess:()=>true,renderJobs:()=>{},
  jobSoftwareScope:x=>(/정보시스템|플랫폼/.test(String(x.title||''))?'candidate':'unknown'),
  document:{getElementById:()=>null},window:{location:{search:''},worklinksKeeps:{keepButton:id=>'<button data-keep-toggle="'+id+'">☆ 킵</button>'}},
  Date,Map,Set,String,Number,Boolean,encodeURIComponent,URLSearchParams,
  htmlEscape:x=>String(x),jobSearchNormalized:x=>String(x).toLowerCase(),
  jobSearchText:'',jobRenderLimit:40
};
vm.createContext(ctx);
vm.runInContext(src+'\nthis.__filter={swBuildTitle,partnerBidMatchesNewFilters,partnerAwardMethodGroup,partnerAwardSummaryText,prebidCache};',ctx);
const {swBuildTitle,partnerBidMatchesNewFilters}=ctx.__filter;
assert.equal(swBuildTitle({kind:'servc',title:'교육정보시스템 구축'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'데이터베이스 고도화'}),true);
assert.equal(swBuildTitle({kind:'cnstwk',title:'정보통신 전기공사'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'CCTV 카메라 단순 구매'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'청사 건축공사'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'AI 서버 공급'}),false);
// Recall-first: build opportunities cannot vanish because of stage, terms or generic coding.
assert.equal(swBuildTitle({kind:'servc',title:'차세대 행정서비스 전면 개편'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'전자결재 연동 개발'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'홈페이지 유지관리 및 기능 개선'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'정보화전략계획 수립(ISMP)'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'2027년 전산소모품(토너 등) 구매'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'2027년도 구민정보화교육 운영 용역'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'정보시스템 유지관리 용역'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'정보시스템 유지관리 및 기능 개발 용역'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'미분류 신행정 서비스',swBizObjYn:'Y'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'개인정보 처리 서비스',productCode:'8111159901'}),true);

const bid=code=>({id:'g2b-servc-R26BK-test-000',kind:'servc',title:'정보시스템 구축',
 awardMethodCode:code,awardFieldsVerified:true});
// Default means every award category, including missing official data.
vm.runInContext("partnerSwScope='all';partnerAwardFilters.clear();",ctx);
const nonsw={id:'g2b-servc-nonsw',title:'사무실 책상 구매',kind:'servc'};
assert.equal(partnerBidMatchesNewFilters(nonsw),true,'전체 공고에서 비SW도 표시');
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),true);
assert.equal(partnerBidMatchesNewFilters({...bid('낙030021'),awardFieldsVerified:false}),true);
assert.equal(ctx.__filter.partnerAwardSummaryText(),'낙찰 전체');
vm.runInContext("partnerSwScope='sw';",ctx);
assert.equal(partnerBidMatchesNewFilters(nonsw),false,'SW 필터에서 비SW 제외');
// Multiple selections OR: price and suitability are shown together.
vm.runInContext("partnerSwScope='build';partnerAwardFilters.add('price');partnerAwardFilters.add('qualification');",ctx);
for(const code of ['낙030021','낙030022','낙030029','낙030001'])
 assert.equal(partnerBidMatchesNewFilters(bid(code)),true,'selected method '+code);
for(const code of ['낙030002','낙030005','낙999999'])
 assert.equal(partnerBidMatchesNewFilters(bid(code)),false,'unselected method '+code);
assert.equal(ctx.__filter.partnerAwardSummaryText(),'가격낙찰형 + 적격심사');
// Unknown official codes and unverified codes are selectable, not misclassified.
vm.runInContext("partnerAwardFilters.clear();partnerAwardFilters.add('other');",ctx);
assert.equal(partnerBidMatchesNewFilters({...bid('낙030021'),awardFieldsVerified:false}),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙999999')),true);
assert.equal(partnerBidMatchesNewFilters(bid('')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),false);
vm.runInContext("partnerAwardFilters.clear();partnerAwardFilters.add('spec-price');partnerAwardFilters.add('negotiation');",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030018')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030002')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030005')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),false);
// Removing all checks means reset to ALL.
vm.runInContext("partnerAwardFilters.clear();",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),true);
assert.equal(ctx.__filter.partnerAwardSummaryText(),'낙찰 전체');
assert.ok(html.includes('id="partnerNoticeStage"'));
assert.ok(html.includes('id="partnerAwardFilter"'));
assert.ok(html.includes('id="partnerAwardSummary"'));
for(const category of ['all','price','qualification','spec-price','negotiation','other'])
 assert.ok(html.includes('data-award-filter="'+category+'"'),'missing checkbox '+category);
assert.ok(html.includes("partnerAwardFilters.add(choice)"),'checkbox should modify shared OR-set');
assert.ok(html.includes("partnerAwardFilters.delete(choice)"),'checkbox should remove from OR-set');
assert.ok(html.includes("partnerAwardFilters.clear()"),'all checkbox must clear selections');
assert.ok(html.includes('syncPartnerAwardControl()'),'stage changes must sync award control');
assert.ok(!html.includes('<select id="partnerAwardFilter"'),'single-select should be removed');
assert.ok(html.includes('id="partnerSwScope"'));
assert.ok(html.includes('changcom-prebid.js'));
assert.ok(html.includes('<option value="all">전체 공고</option>'));
assert.ok(html.includes('<option value="sw">SW 관련</option>'));
assert.ok(html.includes('<option value="build">SW 구축·개발</option>'));
assert.ok(html.includes('data-award-filter="price">가격낙찰형</label>'));
assert.ok(html.includes("if(partnerAllBids.state==='loading')")===false,
 'UI scope code must be external, not duplicated in HTML');
assert.ok(src.includes("'/saved?sw=0&limit=200&offset='"),
 '전체 선택은 비SW 포함 서버 저장 DB에서 조회');
assert.ok(src.includes('partnerSwRelated(x):swBuildTitle(x)'),
 'prebid scope uses shared conservative classification');

assert.ok(html.includes('partnerBidMatchesNewFilters(o.x)'));
// Exercise the actual isolated full-corpus query and the early-stage view.
ctx.worklinksIsChangcomView=()=>true;
ctx.bidEligibilityCache=new Map();
ctx.g2bCardFromServer=row=>({id:row.bidNo,title:row.title,kind:row.kind});
const calls=[];
ctx.g2bFetch=async path=>{
 calls.push(path);
 if(path.endsWith('offset=0'))return {persisted:true,totalCount:3,items:[
   {bidNo:'A',title:'사무실 의자 구매',kind:'thng'},
   {bidNo:'B',title:'정보시스템 구축',kind:'servc'}]};
 if(path.endsWith('offset=2'))return {persisted:true,totalCount:3,items:[
   {bidNo:'C',title:'회의실 청소 용역',kind:'servc'}]};
 throw Error('unexpected page '+path);
};
vm.runInContext("partnerNoticeStage='bid';partnerSwScope='all';partnerAwardFilters.clear();",ctx);
vm.runInContext('loadPartnerAllBids()',ctx).then(async()=>{
 assert.deepEqual(calls,["/saved?sw=0&limit=200&offset=0"]);
 assert.equal(vm.runInContext('partnerAllBids.items.length',ctx),2);
 await vm.runInContext('loadPartnerAllBids(true)',ctx);
 assert.equal(vm.runInContext('partnerAllBids.items.length',ctx),3);
 assert.deepEqual(calls,["/saved?sw=0&limit=200&offset=0","/saved?sw=0&limit=200&offset=2"]);
 vm.runInContext("partnerSwScope='build';",ctx);
 assert.equal(vm.runInContext('partnerAllBids.items.length',ctx),3);
 const elements=Object.fromEntries(['partnerSummary','jobDecisionSummary','g2bMore','jobVerdictFilter','partnerJobCount']
  .map(k=>[k,{textContent:'',style:{},hidden:false}]));
 ctx.document.getElementById=id=>elements[id]||null;
 const el={innerHTML:'',querySelector:()=>null};
 const rows=[{id:'P1',kind:'servc',stage:'plan',title:'정보시스템 구축',swFlagSource:'title'},
             {id:'P2',kind:'thng',stage:'plan',title:'사무실 책상 구매',swFlagSource:'none'}];
 vm.runInContext("prebidCache.plan.state='ready'",ctx);
 ctx.__filter.prebidCache.plan.items=rows;
 ctx.__filter.prebidCache.plan.total=2;
 vm.runInContext("partnerNoticeStage='plan';partnerSwScope='all';",ctx);
 vm.runInContext('renderPrebidJobs',ctx)(el);
 assert.equal(elements.partnerJobCount.textContent,'2건');
 assert.ok(el.innerHTML.includes('사무실 책상 구매'));
 vm.runInContext("partnerSwScope='sw';",ctx);
 vm.runInContext('renderPrebidJobs',ctx)(el);
 assert.equal(elements.partnerJobCount.textContent,'1건');
 assert.ok(!el.innerHTML.includes('사무실 책상 구매'));
 // The two prebid stages share the same persistent keep API but never share IDs.
 vm.runInContext("partnerSwScope='all';",ctx);
 vm.runInContext('renderPrebidJobs',ctx)(el);
 assert.ok(el.innerHTML.includes('data-keep-toggle="g2b-prebid-plan-servc-P1"'));
 assert.ok(el.innerHTML.includes('data-keep-toggle="g2b-prebid-plan-thng-P2"'));
 const planSnapshot=vm.runInContext("prebidKeepSnapshotFor('g2b-prebid-plan-servc-P1')",ctx);
 assert.equal(planSnapshot.type,'발주계획');
 assert.equal(planSnapshot.noticeNumber,'P1');
 assert.equal(planSnapshot.entry,'business');
 const prespec=[{id:'P1',stage:'prespec',kind:'servc',title:'새 전자정부 플랫폼 구축',
                  org:'교육기관',opinionDeadline:'202611271800',budget:123000000,
                  url:'https://www.g2b.go.kr/pn/spec'}];
 ctx.__filter.prebidCache.prespec.items=prespec;
 vm.runInContext("prebidCache.prespec.state='ready'; partnerNoticeStage='prespec';",ctx);
 vm.runInContext('renderPrebidJobs',ctx)(el);
 assert.ok(el.innerHTML.includes('data-keep-toggle="g2b-prebid-prespec-servc-P1"'));
 assert.ok(!el.innerHTML.includes('data-keep-toggle="g2b-prebid-plan-servc-P1"'));
 const specSnapshot=vm.runInContext("prebidKeepSnapshotFor('g2b-prebid-prespec-servc-P1')",ctx);
 assert.equal(specSnapshot.type,'사전규격');
 assert.equal(specSnapshot.deadline,'의견마감 202611271800');
 assert.equal(specSnapshot.url,'https://www.g2b.go.kr/pn/spec');
 const kept=vm.runInContext("prebidKeptCardMarkup({id:'g2b-prebid-prespec-servc-P1',title:'새 전자정부 플랫폼 구축',org:'교육기관',amount:'1.23억 원',period:'의견마감 202611271800',url:'https://www.g2b.go.kr/pn/spec'})",ctx);
 assert.ok(kept.includes('사전규격'));
 assert.ok(kept.includes('data-keep-toggle="g2b-prebid-prespec-servc-P1"'));
 assert.ok(!kept.includes('입찰마감'));
 assert.equal(vm.runInContext("prebidKeepSnapshotFor('g2b-prebid-plan-servc-P1')",ctx).type,'발주계획');
 assert.ok(html.includes("const early=typeof prebidKeepSnapshotFor==='function'?prebidKeepSnapshotFor(id):null;"));
 assert.ok(html.includes("return prebidKeptCardMarkup(o.x);"));
 assert.ok(html.includes("(window.worklinksKeeps?.getMode?.()||'all')==='all'"));

 // Unified selection must actually combine all three sources, not just label a bid search.
 assert.ok(html.includes('<option value="all" selected>전체</option>'));
 assert.ok(html.includes("partnerNoticeStage==='all'"));
 assert.ok(html.includes("renderCombinedProcurementJobs(el)"));
 ctx.jobSearchMatches=(x,q)=>[x.title,x.org,x.id].join(' ').toLowerCase().includes(q);
 ctx.jobOriginUrl=x=>x.url||'https://www.g2b.go.kr/link/PNPE027_01/single/';
 ctx.jobAmountLabel=x=>String(x);
 ctx.jobSearchRemote=[];
 ctx.jobSearchServerTotal=1;
 ctx.jobSearchRemoteLoading=false;
 ctx.jobSearchRemoteError='';
 ctx.jobSearchText='구축';
 vm.runInContext("partnerNoticeStage='all';partnerSwScope='all';",ctx);
 vm.runInContext("partnerAllBids.items=[{id:'g2b-servc-R26BK01830000-000',kind:'servc',title:'공공 플랫폼 구축',startAt:'2026-11-20',amount:'100000000',org:'기획기관',endAt:'2026-11-25'}];partnerAllBids.loaded=1;partnerAllBids.total=1;partnerAllBids.state='ready';",ctx);
 vm.runInContext("prebidCache.plan.state='ready';prebidCache.prespec.state='ready';",ctx);
 const united=vm.runInContext('combinedProcurementRows()',ctx);
 assert.equal(united.result.length,3,'one matching notice in each stage');
 assert.equal(united.counts.bid,1);
 assert.equal(united.counts.plan,1);
 assert.equal(united.counts.prespec,1);
 vm.runInContext('renderCombinedProcurementJobs',ctx)(el);
 assert.ok(el.innerHTML.includes('입찰공고'));
 assert.ok(el.innerHTML.includes('발주계획'));
 assert.ok(el.innerHTML.includes('사전규격'));
 assert.ok(el.innerHTML.includes('g2b-prebid-plan-servc-P1'));
 assert.ok(el.innerHTML.includes('g2b-prebid-prespec-servc-P1'));
 assert.equal(elements.partnerJobCount.textContent,'3건');
 ctx.jobSearchText='존재하지않는공고';
 assert.equal(vm.runInContext('combinedProcurementRows().result.length',ctx),0);
 ctx.jobSearchText='구축';ctx.jobSearchServerTotal=null;ctx.jobSearchRemoteLoading=true;
 vm.runInContext('renderCombinedProcurementJobs',ctx)(el);
 assert.ok(elements.partnerJobCount.textContent.includes('일부'),'unverified search cannot claim completeness');
 // The saved-bid search must page beyond 250 matching results, not truncate.
 const start=html.indexOf('var jobSearchRemoteLoading=false,jobSearchRemoteError');
 const stop=html.indexOf('function updateJobSearchInput(){',start);
 assert.ok(start>0&&stop>start,'paged saved search implementation must exist');
 const searchCalls=[];
 const searchCtx={
  jobSearchSerial:0,jobSearchText:'시스템',partnerNoticeStage:'all',
  worklinksIsChangcomView:()=>true,
  document:{getElementById:()=>({textContent:''})},
  g2bFetch:async url=>{
   searchCalls.push(url);
   const offset=Number(new URL('https://example.test'+url).searchParams.get('offset'));
   const count=offset===0?250:50;
   return {searchMode:'saved_only',totalCount:300,
    items:Array.from({length:count},(_,i)=>({bidNo:'N'+(offset+i),order:'000',title:'시스템 구축'}))};
  },
  g2bCardFromServer:row=>({id:row.bidNo,title:row.title}),
  bidEligibilityCache:new Map(),g2bSupplementalCache:new Map(),jobSearchRfpState:new Map(),
  jobSearchRemote:[],jobSearchServerTotal:null,
  scheduleJobsRender:()=>{},encodeURIComponent,Number,String,Map,Set,Date
 };
 vm.createContext(searchCtx);
 vm.runInContext(html.slice(start,stop),searchCtx);
 await vm.runInContext("jobRunRemoteSearch('시스템')",searchCtx);
 assert.equal(searchCalls.length,2,'full query pages fetched');
 assert.equal(searchCtx.jobSearchRemote.length,300,'all 300 matches returned');
 assert.equal(searchCtx.jobSearchServerTotal,300);
 assert.equal(html.includes("const partnerAllMode=member&&partnerMode&&partnerNoticeStage==='bid';"),true);
 assert.ok(html.includes("const searchSw=worklinksIsChangcomView()?'0':'1';"));
 console.log('CHANGCOM_PREBID_FILTERS=PASS');
}).catch(error=>{console.error(error);process.exitCode=1;});
