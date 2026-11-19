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
  document:{},Date,Map,Set,String,Number,Boolean,encodeURIComponent,
  htmlEscape:x=>String(x),jobSearchNormalized:x=>String(x).toLowerCase(),
  jobSearchText:'',jobRenderLimit:40
};
vm.createContext(ctx);
vm.runInContext(src+'\nthis.__filter={swBuildTitle,partnerBidMatchesNewFilters,prebidCache};',ctx);
const {swBuildTitle,partnerBidMatchesNewFilters}=ctx.__filter;
assert.equal(swBuildTitle({kind:'servc',title:'교육정보시스템 구축'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'데이터베이스 고도화'}),true);
assert.equal(swBuildTitle({kind:'cnstwk',title:'정보통신 전기공사'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'CCTV 카메라 단순 구매'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'청사 건축공사'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'AI 서버 공급'}),false);
const bid=code=>({id:'g2b-servc-R26BK-test-000',kind:'servc',title:'정보시스템 구축',
 awardMethodCode:code,awardFieldsVerified:true});
vm.runInContext("partnerSwScope='build';partnerAwardFilter='price';",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030021')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030022')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030029')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),false);
assert.equal(partnerBidMatchesNewFilters(bid('낙030002')),false);
vm.runInContext("partnerSwScope='all';partnerAwardFilter='all';",ctx);
assert.equal(partnerBidMatchesNewFilters({id:'g2b-servc-nonsw',title:'사무실 책상 구매',kind:'servc'}),true,
 '전체 공고는 비SW 공고를 숨기면 안 됨');
vm.runInContext("partnerSwScope='sw';",ctx);
assert.equal(partnerBidMatchesNewFilters({id:'g2b-servc-nonsw',title:'사무실 책상 구매',kind:'servc'}),false,
 'SW 관련 선택에서 비SW 제외');
vm.runInContext("partnerSwScope='build';partnerAwardFilter='price';",ctx);
assert.equal(partnerBidMatchesNewFilters({...bid('낙030021'),awardFieldsVerified:false}),false);
vm.runInContext("partnerAwardFilter='qualification';",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),true);
vm.runInContext("partnerAwardFilter='spec-price';",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030018')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030002')),true);
assert.ok(html.includes('id="partnerNoticeStage"'));
assert.ok(html.includes('id="partnerAwardFilter"'));
assert.ok(html.includes('id="partnerSwScope"'));
assert.ok(html.includes('changcom-prebid.js'));
assert.ok(html.includes('<option value="all">전체 공고</option>'));
assert.ok(html.includes('<option value="sw">SW 관련</option>'));
assert.ok(html.includes('<option value="build">SW 구축·개발</option>'));
assert.ok(html.includes('<option value="price">가격낙찰형</option>'));
assert.ok(html.includes("if(partnerAllBids.state==='loading')")===false,
 'UI scope code must be external, not duplicated in HTML');
assert.ok(src.includes("'/saved?sw=0&limit=200&offset='"),
 '전체 선택은 비SW 포함 서버 저장 DB에서 조회');
assert.ok(src.includes("x.swFlagSource!=='none'"),
 'prebid SW 필터는 신규 비SW 저장 레코드를 제외');

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
vm.runInContext("partnerNoticeStage='bid';partnerSwScope='all';partnerAwardFilter='all';",ctx);
vm.runInContext('loadPartnerAllBids()',ctx).then(async()=>{
 assert.deepEqual(calls,["/saved?sw=0&limit=200&offset=0"]);
 assert.equal(vm.runInContext('partnerAllBids.items.length',ctx),2);
 await vm.runInContext('loadPartnerAllBids(true)',ctx);
 assert.equal(vm.runInContext('partnerAllBids.items.length',ctx),3);
 assert.deepEqual(calls,["/saved?sw=0&limit=200&offset=0","/saved?sw=0&limit=200&offset=2"]);
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
 console.log('CHANGCOM_PREBID_FILTERS=PASS');
}).catch(error=>{console.error(error);process.exitCode=1;});
