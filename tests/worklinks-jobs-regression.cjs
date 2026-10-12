// Run: node tests/worklinks-jobs-regression.cjs (no external dependencies).
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const part=(from,to)=>{
 const a=source.indexOf(from),b=source.indexOf(to,a+from.length);
 assert.ok(a>=0&&b>a,'missing source section '+from);
 return source.slice(a,b);
};
const time=new Function(
 'function kstNow(){return new Date(Date.UTC(2026,9,12,10,0))};'+
 "function kstISO(){return '2026-10-12'};"+
 part('function dayValue(value,asEnd){','function jobAmountLabel(raw){')+
 'return {dayValue,jobTimeInfo,jobDayCounter,jobDeadlineStamp};'
)();
assert.equal(new Date(time.dayValue('2026-10-14T18:00:00+09:00')).toISOString().slice(0,16),'2026-10-14T18:00');
assert.equal(time.jobDayCounter(time.jobTimeInfo({closes:'202610141500'})).label,'D-2');
assert.equal(time.jobDayCounter(time.jobTimeInfo({closes:'2026-10-12 18:00'})).label,'D-0');
assert.equal(time.jobDayCounter(time.jobTimeInfo({closes:''})).label,'일정 미확인');
assert.equal(time.jobTimeInfo({closes:'2026.10.10 18:00'}).key,'closed');
assert.equal(time.jobDayCounter(time.jobTimeInfo({closes:'2026-10-15 18:00'})).label,'D-3');
assert.equal(time.jobDeadlineStamp(time.jobTimeInfo({closes:'2026-10-15 18:00'})),'10.15 18:00');
assert.equal(time.jobDeadlineStamp(time.jobTimeInfo({closes:''})),'');
assert.equal(time.jobDeadlineStamp(time.jobTimeInfo({closes:'2026-10-12 13:00'})),'10.12 13:00');
const scope=new Function(part('const hardwarePurchasePattern=','function noticeGroupKey(x){')+'return jobSoftwareScope;')();
assert.equal(scope({kind:'thng',title:'GPU 컴퓨터 서버 구매'}),'out');
assert.equal(scope({kind:'cnstwk',title:'CCTV 통신 공사'}),'out');
const match=new Function(
 'function partnerRegisteredCode(p,c){return Object.hasOwn(p,c)?p[c]:null};'+
 "function jobSoftwareScope(x){return x.kind==='thng'?'out':'candidate'};"+
 'function jobEligibilityData(x){return x.req};'+
 part('function licenseLogic(line){','function jobPartnerMatches(x){')+
 'return {jobQualificationVerdict};'
)();
const p={registryCheckedAt:'2026-10-12',registryComplete:true,1468:true,1426:false};
const req=name=>({ok:true,complete:true,requirements:[{name,codes:['1468','1426'],group:'1'}]});
assert.equal(match.jobQualificationVerdict({kind:'servc',req:req('1468 또는 1426')},p).type,'industry_match');
assert.equal(match.jobQualificationVerdict({kind:'servc',req:req('1468 / 1426')},p).type,'unverified');
assert.equal(match.jobQualificationVerdict({kind:'servc',req:req('1468 및 1426 모두')},p).type,'missing');
assert.equal(match.jobQualificationVerdict({kind:'thng',req:req('1468 또는 1426')},p).type,'not_applicable');
const dedupe=new Function(
 'function jobBidIdentity(x){return x.noticeNumber?{bidNo:x.noticeNumber}:null};'+
 'function jobOriginUrl(x){return x.url||"https://www.g2b.go.kr/"};'+
 'function jobTimeInfo(x){return {start:Date.parse(x.startAt||x.posted)||null,key:x.state||"open"}};'+
 part('function noticeGroupKey(x){','function licenseLogic(line){')+
 'return collapseSimilarNotices;'
)();
const base={kind:'servc',title:'공공정보시스템 유지관리',org:'시청',amount:'100000000'};
const versions=dedupe([
 {...base,id:'old',noticeNumber:'R26BK00000001',noticeOrder:'000',posted:'2026-10-01',state:'open'},
 {...base,id:'new',noticeNumber:'R26BK00000001',noticeOrder:'001',posted:'2026-10-02',state:'closed'}
]);
assert.equal(versions.length,1);
assert.equal(versions[0].id,'new','correction must supersede the old open order');
assert.equal(versions[0].variants.length,2);
assert.equal(dedupe([
 {...base,id:'annual-1',noticeNumber:'R25BK00000001',posted:'2025-10-01'},
 {...base,id:'annual-2',noticeNumber:'R26BK00000002',posted:'2026-10-01'}
]).length,2,'annual reprocurement must remain separate');

// Verified matches and pending candidates are distinct. Never count hardware or known failures.
const companyMatching=new Function('partners','jobQualificationVerdict','jobSoftwareScope',
 part('function jobPartnerMatches(x){','var partnerFetchStarted=false')+
 'return {jobPartnerMatches,jobPartnerCandidates,partnerIdsOfJob,partnerCandidateIdsOfJob};'
)([{id:'changcom',name:'창컴정보통신(주)'}],
 (x,p)=>({type:x.verdict}),
 x=>x.kind==='thng'?'out':'candidate'
);
assert.deepEqual(companyMatching.partnerIdsOfJob({kind:'servc',verdict:'industry_match'}),['changcom']);
assert.deepEqual(companyMatching.partnerCandidateIdsOfJob({kind:'servc',verdict:'unverified'}),['changcom']);
assert.deepEqual(companyMatching.partnerIdsOfJob({kind:'servc',verdict:'unverified'}),[]);
assert.deepEqual(companyMatching.partnerCandidateIdsOfJob({kind:'servc',verdict:'missing'}),[]);
assert.deepEqual(companyMatching.partnerCandidateIdsOfJob({kind:'thng',verdict:'unverified'}),[]);

// Exercise the ACTUAL registration-status regex, not a stubbed helper.
const realCompany={id:'changcom',registryCheckedAt:'2026-10-12T11:00:00+09:00',
 registryComplete:true,industryRecords:[
  {code:'1468',status:'정상',expiresAt:'2099-12-31 00:00:00'},
  {code:'1426',status:'정상',expiresAt:'2099-12-31 00:00:00'},
  {code:'1169',status:'',expiresAt:''}
 ]};
const official={ok:true,complete:true,requirements:[
 {name:'소프트웨어사업자(컴퓨터관련서비스사업)',codes:['1468'],logic:'UNKNOWN',group:'',sequence:'1'}
]};
const real=new Function('partners','jobEligibilityData','kstISO','jobBidIdentity','jobTimeInfo','jobOriginUrl',
 part('const partnerIndustryKnownCodes=','var partnerFetchStarted=false')+
 part('function partnerRegisteredCode(p,code){','function comparePartnerJob(x,p){')+
 'return {partnerRegisteredCode,jobQualificationVerdict,jobPartnerMatches};'
)([realCompany],x=>x.req,()=>'2026-10-12',()=>null,()=>({start:null}),()=>'' );
const realJob={kind:'servc',title:'2026년 광해정보통합관리시스템 유지관리 용역',req:official};
assert.equal(real.partnerRegisteredCode(realCompany,'1468'),true);
assert.equal(real.partnerRegisteredCode(realCompany,'1426'),true);
assert.equal(real.partnerRegisteredCode(realCompany,'1169'),null,'unknown status must not be treated as confirmed');
assert.equal(real.jobQualificationVerdict(realJob,realCompany).type,'industry_match');
assert.equal(real.jobPartnerMatches(realJob).length,1,'official 1468 bid must be listed under Changcom');
const expiredCompany={...realCompany,industryRecords:[{code:'1468',status:'정상',expiresAt:'2025-01-01'}]};
assert.equal(real.partnerRegisteredCode(expiredCompany,'1468'),false,'expired registration is not valid');


// Partner selector is sourced from the registry and includes *separately labeled* pending candidates.
const filterSection=part('var jobFilter="all",jobRenderLimit=100','function jobEntryLabel(v){');
const filterSelect={
 value:'all',innerHTML:'',closest:()=>({classList:{toggle:()=>{}}})
};
const companies=[{id:'changcom',name:'창컴정보통신(주)'}];
const filterFns=new Function('partners','document','htmlEscape','localStorage','partnerIdsOfJob','partnerCandidateIdsOfJob',
 filterSection+
 'return {syncPartnerFilterChoices,jobMatchesSelectedPartner,getSelected:()=>selectedPartnerId,setSelected:v=>{selectedPartnerId=v}};'
)(
 companies,{getElementById:id=>id==='partnerFilter'?filterSelect:null},
 value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 {setItem:()=>{}},x=>x.matches||[],x=>x.candidates||[]
);
filterFns.syncPartnerFilterChoices();
assert.ok(filterSelect.innerHTML.includes('value="all">모두'));
assert.ok(filterSelect.innerHTML.includes('value="changcom">창컴정보통신(주)'));
assert.equal(filterFns.jobMatchesSelectedPartner({matches:['changcom']},'all'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({matches:[]},'all'),false);
assert.equal(filterFns.jobMatchesSelectedPartner({matches:['changcom']},'changcom'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({matches:['other']},'changcom'),false);
assert.equal(filterFns.jobMatchesSelectedPartner({candidates:['changcom']},'all'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({candidates:['changcom']},'changcom'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({candidates:['another']},'changcom'),false);
companies.push({id:'newpartner',name:'신규 파트너'});
filterFns.syncPartnerFilterChoices();
assert.ok(filterSelect.innerHTML.includes('value="newpartner">신규 파트너'));
assert.equal(filterFns.jobMatchesSelectedPartner({matches:['newpartner']},'newpartner'),true);
filterFns.setSelected('newpartner');
filterFns.syncPartnerFilterChoices();
assert.equal(filterSelect.value,'newpartner');
companies.pop();
filterFns.syncPartnerFilterChoices();
assert.equal(filterSelect.value,'all','removed partner safely resets to all');

console.log('Worklinks job regression: deadlines, scope, AND/OR, corrections, verified/pending partner filters PASS');
