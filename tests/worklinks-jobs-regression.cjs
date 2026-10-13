// Run: node tests/worklinks-jobs-regression.cjs (no external dependencies).
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
// Compile the complete inline application script; partial-function unit tests cannot
// catch malformed UI code introduced outside the individually tested sections.
const inline=source.match(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/i);
assert.ok(inline&&inline[1],'inline WorkLinks application script exists');
assert.doesNotThrow(()=>new Function(inline[1]),'all WorkLinks frontend JavaScript must parse');
assert.ok(source.includes("const docLinks=docs?.ok?"),'bid detail must show official attachments');
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
assert.equal(time.jobDayCounter(time.jobTimeInfo({closes:'2026-10-12 18:00'})).label,'D-DAY');
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
assert.equal(match.jobQualificationVerdict({kind:'servc',req:{ok:true,complete:true,requirements:[]}},p).type,'no_restriction',
 'zero official industry-restriction rows are NOT a permanent verification failure');
assert.equal(match.jobQualificationVerdict({kind:'servc',req:{ok:false,complete:false,requirements:[]}},p).type,'unverified',
 'API error cannot be interpreted as no restrictions');
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


// Real direct-production comparison: historical evidence must not imply live validity.
const directMod=new Function('kstISO',
 part('const productionNames=','function comparePartnerJob(x,p){')+
 'return {productionRequirementCheck};'
)(()=>'2026-10-12');
const prodP={productionCheckedAt:'2026-10-12T04:41:45Z',productionSnapshotDate:'2026-02-01',
 productionRecords:[{product:'정보시스템개발서비스',validFrom:'2025-01-16',validTo:'2027-01-15'},
  {product:'데이터처리서비스',validFrom:'2025-01-16',validTo:'2027-01-15'}]};
const direct=txt=>directMod.productionRequirementCheck({condition:txt,partnerBidMode:''},prodP);
assert.equal(direct('정보시스템개발서비스 직접생산확인증명서 필요').status,'ok');
assert.equal(direct('직접생산확인증명서 8111159901 제출').status,'ok');
assert.equal(direct('직접생산확인증명서 세부품명번호 8111200201').status,'ok',
 'data processing production certificate must match solely by detailed numeric code');
assert.equal(direct('직접생산확인증명서 세부품명번호 8111179901').status,'pending',
 'unissued infrastructure code cannot be mistaken for existing data processing certificate');
assert.equal(direct('직접생산확인증명서 8111200201 또는 8111159901').status,'unknown',
 'multiple production codes need mandatory-vs-alternative determination');
const rfpDoc=JSON.parse(fs.readFileSync(path.join(__dirname,'../startup-support/rfp-clauses.json'),'utf8'));
const rfpSample=rfpDoc.byNotice['R26BK01756420:000'];
assert.equal(rfpSample.status,'text_extracted_requires_review');
assert.ok(rfpSample.files.some(f=>f.readable&&f.snippets.some(x=>x.text.includes('8111189901'))));
const rfpProductChecker=new Function('kstISO','rfpSnapshotForJob',
 part('const productionNames=','function comparePartnerJob(x,p){')+
 'return productionRequirementCheck;'
)(()=>'2026-10-12',()=>rfpSample);
assert.equal(rfpProductChecker({condition:'',partnerBidMode:''},{
 ...prodP,productionRecords:[...prodP.productionRecords,
  {product:'정보시스템유지관리서비스',validFrom:'2025-01-16',validTo:'2027-01-15'}]
}).status,'ok','official RFP code 8111189901 must match partner production certificate history');
assert.equal(rfpProductChecker({condition:'',partnerBidMode:''},prodP).status,'pending',
 'missing matching product in dated certificate registry remains unverified');

assert.equal(direct('정보시스템유지관리서비스 직접생산확인증명서 필수').status,'pending');
assert.equal(direct('직접생산확인증명서 제출').status,'unknown');
assert.equal(direct('업체 등록 1468').applicable,false);
assert.equal(directMod.productionRequirementCheck({condition:'정보시스템개발서비스 직접생산확인증명서 필요'},{}).status,'pending');
assert.equal(directMod.productionRequirementCheck({condition:'정보시스템개발서비스 직접생산확인증명서 필요'},{
 ...prodP,productionRecords:[{product:'정보시스템개발서비스',validTo:'2025-10-01'}]
}).status,'pending','expired historical certificate must not mean current proof');
assert.equal(direct('정보시스템개발서비스 및 정보시스템유지관리서비스 직접생산확인증명서 필요').status,'unknown','multiple requirements need AND/OR analysis');
assert.ok(source.includes("공개자료 기준일 이후 취소·변경 여부는 SMPP 최신 확인 필요"));
assert.ok(source.includes('productionRequirementCheck(x,p)'));
assert.ok(source.includes('participationStrip(x,comparisonCompanies)'));

assert.ok(source.includes('async function refreshRfpSnapshot()'));
assert.ok(source.includes('const extractHTML=readable.length?'));
assert.ok(source.includes('rfpSnapshotForJob(x)'));
assert.ok(source.includes("files.length+'개 문서 텍스트 추출"));
// Region lookup: one proved region match, and two fail-closed unknown cases.
const regional=new Function('jobEvidenceData',
 part('function normalizedRegion(x){','function partnerRegisteredCode(p,code){')+
 'return regionRequirementCheck;'
)(x=>x.regionEvidence||null);
const seoulCompany={registeredAddress:'서울특별시 양천구',registeredRegionName:'서울특별시',registeredRegionCode:'11'};
const seoulBid={regionEvidence:{region:{ok:true,complete:true,items:[{name:'서울특별시',code:'11'}]}}};
assert.equal(regional(seoulBid,seoulCompany).status,'ok');
assert.equal(regional({regionEvidence:{region:{ok:true,complete:true,items:[]}}},seoulCompany).status,'unknown','zero region rows cannot mean nationwide');
assert.equal(regional(seoulBid,{}).status,'pending','no company address must not be a match');
assert.equal(regional({regionEvidence:{region:{ok:false,error:'upstream_http_403'}}},seoulCompany).status,'unknown');
assert.ok(source.includes('data.company.regionCode'));

// Provenance: only exact G2B bidNo + official winner business number are accepted.
assert.ok(source.includes('awardBidNos:["R25BK00826083","20221204854"]'));
assert.ok(source.includes("String(r.bidwinnrBizno||'').replace(/\\D/g,'')!==bizno"));
assert.ok(source.includes("String(r.bidNtceNo||'')!==bids[i]"));
assert.ok(source.includes("if(id==='experience'&&p.awardEvidence?.length)"));
assert.ok(source.includes("낙찰은 계약이행 실적증명의 대체 자료가 아님"));
assert.ok(source.includes("나라장터 공식 낙찰"));

// Official SMPP SME validity must be compared, not left generically pending.
const smeCmp=new Function('jobSoftwareScope','jobEligibilityData','productionRequirementCheck','jobEvidenceData','regionRequirementCheck','rfpSnapshotForJob','extractedRfpRequirements',
 part('function officialReviewCoverage(rfp,evidence){','function matchRowsHTML(x,p){')+
 'return comparePartnerJob;'
)(()=> 'candidate',()=>({ok:false}),()=>({applicable:false}),()=>null,()=>({status:'unknown',reason:'region not queried'}),()=>null,()=>'' );
const smeBid={condition:'중소기업확인서 소기업만 참여',partnerBidMode:''};
const smePartner={smeRecord:{size:'소기업',issuedAt:'2026-04-01',validState:'valid'},
 smeCheckedAt:'2026-10-12T05:04:00Z'};
const smeRows=smeCmp(smeBid,smePartner).rows;
assert.equal(smeRows.find(q=>q.id==='sme-issuance').status,'ok');
assert.equal(smeRows.find(q=>q.id==='sme-validity').status,'ok');
assert.equal(smeRows.find(q=>q.id==='sme-scale').status,'ok');
assert.equal(smeRows.find(q=>q.id==='sme-expiry').status,'ok','current SMPP valid(Y) is not nullified by unpublished expiry');
assert.equal(smeCmp(smeBid,{smeRecord:{...smePartner.smeRecord,validState:'unknown'},smeCheckedAt:'2026-10-12'}).rows.find(q=>q.id==='sme-validity').status,'pending');
assert.equal(smeCmp(smeBid,{}).rows.find(q=>q.id==='sme-issuance').status,'pending');
assert.ok(source.includes("refreshPartnerSme(p)"));
assert.ok(source.includes("sme-cert-snapshot.json"));


// Verify the actual comparePartnerJob complete flag is evidence dependent.
const completion=new Function('jobSoftwareScope','jobEligibilityData','productionRequirementCheck','jobEvidenceData','regionRequirementCheck','rfpSnapshotForJob','extractedRfpRequirements',
 part('function officialReviewCoverage(rfp,evidence){','function matchRowsHTML(x,p){')+'return comparePartnerJob;'
)(()=> 'candidate',()=>({ok:true,complete:true,requirements:[]}),
 ()=>({applicable:false}),()=>({attachments:{ok:true,complete:true,items:[{name:'공식 공고'}]}}),
 ()=>({status:'unknown'}),
 x=>x.reviewed?{status:'fully_reviewed',reviewComplete:true,requiredConditionsComplete:true,
   files:[{readable:true,reviewComplete:true,topics:{},name:'공식 공고'}]}:
   {status:'text_extracted_requires_review',reviewComplete:false,files:[{readable:true,reviewComplete:false,topics:{},name:'RFP'}]},
 ()=> '');
const noFilesCoverage=new Function(
 part('function officialReviewCoverage(rfp,evidence){','function comparePartnerJob(x,p){')+
 'return officialReviewCoverage;'
)();
const noFiles={reviewComplete:true,requiredConditionsComplete:true,files:[],
 noticeTextReviewed:true,noticeConditionsVerified:true,
 noticeSourceUrl:'https://www.g2b.go.kr/notice',noticeSha256:'verified-sha'};
const noFilesEvidence={attachments:{ok:true,complete:true,items:[]},
 noticeDocuments:{ok:true,complete:true,count:0}};
assert.equal(noFilesCoverage(noFiles,noFilesEvidence),true,'fully checked official notice can qualify without separate attachment');
assert.equal(noFilesCoverage({...noFiles,noticeSha256:''},noFilesEvidence),false);
assert.equal(noFilesCoverage(noFiles,{attachments:{ok:true,complete:true,items:[]}}),false,
 'zero attachment list must never waive notice review');
assert.equal(completion({reviewed:false},{}).complete,false,'snippets cannot certify a bid');
assert.equal(completion({reviewed:true},{}).complete,true,'fully verified and no outstanding requirements is achievable');
assert.equal(completion({reviewed:true},{}).rows.find(q=>q.id==='attachment').status,'ok');
assert.equal(completion({reviewed:false},{}).rows.find(q=>q.id==='attachment').status,'unknown');
assert.ok(source.includes('id="jobInfoFold"'));
assert.ok(source.includes('id="jobMissingInfo"'));
assert.ok(source.includes('id="jobDecisionSummary"'));
assert.ok(source.includes('id="g2bPanel"'));
assert.ok(source.indexOf('id="jobInfoFold"')<source.indexOf('class="jobfilters"'));
assert.ok(source.includes('#jobsView .jobf{font-size:16px'));
assert.ok(source.includes('#jobsView .job-vf{font-size:16px'));
assert.ok(source.includes('#jobCards .job-mini h3{font-size:17px'));
assert.ok(source.includes('원문·첨부 전수검토'));
assert.ok(!source.includes('return {rows,counts,complete:false};'));

// Each thumbnail must show the COMPLETE 4-state result per company, not
// interpret an industry-only match as bid-ready.
const resultsById={
 industry_match:'industry_match', unverified:'unverified', missing:'missing'
};
const verdictMod=new Function('jobTimeInfo','jobSoftwareScope','jobQualificationVerdict','comparePartnerJob','htmlEscape',
 part('function participationVerdict(x,p){','function matchRowsHTML(x,p){')+
 'return {participationVerdict,participationStrip};'
)(x=>({key:x.closed?'closed':'open'}),x=>x.kind==='thng'?'out':'candidate',
 x=>({type:x.industry||'unverified',reason:'면허검증 대기'}),
 (x,p)=>({complete:!!x.full,counts:{ok:x.ok??2,pending:x.pending??1,unknown:x.unknown??1,missing:0},
    rows:x.missing?[{id:'license-1',status:'missing',reason:'등록업종 불일치'}]:[]}),
 x=>String(x));
const bidder={id:'changcom',short:'창컴',name:'창컴정보통신(주)',smeRecord:{size:'소기업',validState:'valid'}};
const verdict=(x,p=bidder)=>verdictMod.participationVerdict({kind:'servc',...x},p);
assert.equal(verdict({industry:'industry_match'}).type,'conditional');
assert.equal(verdict({industry:'unverified'}).type,'checking');
assert.equal(verdict({industry:'no_restriction'}).type,'conditional','official 0 industry restrictions are a positive check but not ready');
assert.equal(verdict({industry:'no_restriction',full:false,ok:2,pending:0,unknown:1}).type,'conditional');
assert.equal(verdict({industry:'no_restriction',full:true,ok:2,pending:0,unknown:0}).type,'ready',
 'zero industry restrictions and independently verified complete notice can qualify');
assert.equal(verdict({industry:'missing'}).type,'blocked');
assert.equal(verdict({industry:'industry_match',missing:true}).type,'blocked');
assert.equal(verdict({industry:'industry_match',closed:true}).type,'blocked');
assert.ok(source.includes("t.key==='upcoming'"));
assert.equal(verdict({industry:'industry_match',full:false,ok:6,pending:0,unknown:0}).type,'conditional','all available API matches alone cannot certify attachments');
assert.equal(verdict({industry:'industry_match',full:true,ok:7,pending:0,unknown:0}).type,'ready','only explicit verified full evidence can be ready');
assert.equal(verdict({industry:'industry_match',condition:'소상공인만 입찰'}).type,'blocked','small enterprise is not necessarily micro enterprise');
assert.equal(verdict({industry:'industry_match',condition:'공동수급 불허'}).type,'conditional','joint-venture prohibition does not prohibit solo bidding');
const html=verdictMod.participationStrip({id:'test-bid',condition:'',industry:'industry_match'},
  [bidder,{id:'other',short:'다른 업체',smeRecord:{size:'소기업',validState:'valid'}}]);
assert.ok(html.includes('data-partner-id="changcom"')&&html.includes('data-partner-id="other"'));
assert.ok(html.includes('조건부 가능'));
assert.ok(source.includes('participationStrip(x,comparisonCompanies)'));
assert.ok(source.includes('function participationVerdict(x,p)'));
assert.ok(source.includes('job-verdict ready')===false,'do not hardcode all notices as ready');

// Status filters must be interactive, cover all currently displayed items, and
// show a reason even when the notice is outside the software candidate scope.
const filterView=new Function('partners','participationVerdict','document','htmlEscape','jobQualificationVerdict',
 part('function partnerVerdictTypes(x,selected){','function jobEntryLabel(v){')+
 'return {partnerVerdictTypes,matchesVerdictFilter,refreshVerdictFilters};'
)([bidder],(x,p)=>({type:x.verdict||'checking'}),{
 querySelectorAll:()=>[],
 getElementById:()=>({hidden:false})
},value=>String(value),(x,p)=>({type:x.industry||'unverified'}));
for(const [verdict,type] of [['ready','ready'],['conditional','conditional'],['blocked','blocked'],['checking','checking']]){
 assert.equal(filterView.matchesVerdictFilter({verdict},null,type),true);
 assert.equal(filterView.matchesVerdictFilter({verdict},null,'all'),true);
 assert.equal(filterView.matchesVerdictFilter({verdict},null,type==='ready'?'blocked':'ready'),false);
}
assert.equal(filterView.matchesVerdictFilter({industry:'industry_match'},null,'registered'),true);
assert.equal(filterView.matchesVerdictFilter({industry:'no_restriction'},null,'no-restriction'),true);
assert.equal(filterView.matchesVerdictFilter({industry:'unverified'},null,'registered'),false);
assert.equal(filterView.matchesVerdictFilter({industry:'unverified'},null,'no-restriction'),false);
assert.ok(source.includes('data-verdict-filter="ready"'));
assert.ok(source.includes('data-verdict-filter="conditional"'));
assert.ok(source.includes('data-verdict-filter="blocked"'));
assert.ok(source.includes('data-verdict-filter="checking"'));
assert.ok(source.includes('data-verdict-filter="registered"'));
assert.ok(source.includes('data-verdict-filter="no-restriction"'));
assert.ok(source.includes("document.querySelectorAll('[data-verdict-filter]')"));
assert.ok(source.includes("scopeRows.filter(o=>matchesVerdictFilter(o.x,selectedCompany,jobVerdictFilter))"));
assert.ok(source.includes('participationStrip(x,comparisonCompanies)'));
assert.ok(!source.includes("if(jobSoftwareScope(x)!=='candidate')return '';"),'cannot leave thumbnail without bidder status');
const unscoped=verdictMod.participationVerdict({kind:'thng'},bidder);
assert.ok(['blocked','checking'].includes(unscoped.type));
assert.ok(unscoped.reason.length>9);

// Readable card and detail copy: no opaque 1468 chip or duplicate "pending" labels.
assert.ok(source.includes("diff===0?'D-DAY':'D-'+diff"));
assert.ok(source.includes('업종 일치 · 추가서류 확인 필요'));
assert.ok(source.includes('입찰자격 확인 중'));
assert.ok(source.includes('필수 업종 불일치'));
assert.ok(!source.includes('조건 검증 대기</span>'));
assert.ok(!source.includes('>검증 대기 </span>'));
assert.ok(!source.includes("matchCode+' 일치 · 증빙 필요"));
assert.ok(source.includes('공고의 면허제한 등록업종 '));
assert.ok(source.includes('바로 입찰 가능 확정은 아닙니다.'));
assert.ok(source.includes("htmlEscape(p.short||p.name)"));

// Partner selector is sourced from the registry and includes *separately labeled* pending candidates.
const filterSection=part('var jobFilter="all",jobRenderLimit=100','function jobEntryLabel(v){');
const filterSelect={
 value:'all',innerHTML:'',closest:()=>({classList:{toggle:()=>{}}})
};
const companies=[{id:'changcom',name:'창컴정보통신(주)'}];
const filterFns=new Function('partners','document','htmlEscape','localStorage','partnerIdsOfJob','partnerCandidateIdsOfJob','jobSoftwareScope',
 filterSection+
 'return {syncPartnerFilterChoices,jobMatchesSelectedPartner,getSelected:()=>selectedPartnerId,setSelected:v=>{selectedPartnerId=v}};'
)(
 companies,{getElementById:id=>id==='partnerFilter'?filterSelect:null},
 value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 {setItem:()=>{}},x=>x.matches||[],x=>x.candidates||[],x=>x.kind==='thng'?'out':'candidate'
);
filterFns.syncPartnerFilterChoices();
assert.ok(filterSelect.innerHTML.includes('value="all">모두'));
assert.ok(filterSelect.innerHTML.includes('value="changcom">창컴정보통신(주)'));
assert.equal(filterFns.jobMatchesSelectedPartner({matches:['changcom']},'all'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({matches:[]},'all'),true,'unverified bids stay visible');
assert.equal(filterFns.jobMatchesSelectedPartner({matches:['changcom']},'changcom'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({matches:['other']},'changcom'),true,'show blocked or unverified partner jobs');
assert.equal(filterFns.jobMatchesSelectedPartner({candidates:['changcom']},'all'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({candidates:['changcom']},'changcom'),true);
assert.equal(filterFns.jobMatchesSelectedPartner({candidates:['another']},'changcom'),true,'filter should not hide bid failures');
assert.equal(filterFns.jobMatchesSelectedPartner({kind:'thng',matches:['changcom']},'changcom'),true,'visible hardware/unknown jobs must show an explicit blocked or checking verdict');
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
