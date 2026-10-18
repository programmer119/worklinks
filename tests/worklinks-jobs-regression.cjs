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
assert.equal(scope({kind:'servc',title:'AI타워 지하주차장 폐목재 및 폐합성수지 처리 용역'}),'out',
 'a construction complex named AI tower is not SW work');
assert.equal(scope({kind:'thng',title:'상용SW 제3자단가 제품 라이선스 도입'}),'out',
 'third-party off-the-shelf licenses without development are not standalone SW deliverables');
assert.equal(scope({kind:'thng',title:'보안 SW 개발 및 시스템 구축'}),'candidate');
assert.equal(scope({kind:'servc',title:'상용SW 제3자단가(CertBear V2.0_위베어소프트)'}),'out');
assert.equal(scope({kind:'servc',title:'3D 모델링용 SW'}),'out');
assert.equal(scope({kind:'servc',title:'EDR 솔루션 도입'}),'out');
assert.equal(scope({kind:'servc',title:'SW 솔루션 개발 및 구축'}),'candidate');
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
const directMod=new Function('kstISO','rfpSnapshotForJob',
 part('const productionNames=','function comparePartnerJob(x,p){')+
 'return {productionRequirementCheck};'
)(()=>'2026-10-12',()=>null);
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
const retained=Object.values(rfpDoc.byNotice||{});
assert(retained.some(r=>r.status==='text_extracted_requires_review'&&
 (r.files||[]).some(f=>f.readable)),'latest snapshot must retain source evidence');
// Stable isolated fixture: production snapshots rotate and old bid IDs are evicted.
const rfpSample={status:'text_extracted_requires_review',files:[{readable:true,
 name:'입찰공고문.hwp',clauseCandidates:[{type:'direct_production',
 codes:['8111189901'],sourceText:'직접생산확인증명서 8111189901 소지한 자',explicitMust:true}],
 snippets:[{text:'직접생산확인증명서 8111189901 소지한 자'}]}]};
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

assert.equal(direct('직접생산확인증명서 공간정보 DB 구축 서비스(8115169901)를 소지한 업체').status,'pending',
 'unverified GIS direct-production product is NOT held in dated nine-product snapshot');
assert.equal(direct('직접생산확인증명서 공간정보 DB 구축 서비스를 소지한 업체').status,'pending',
 'whitespace inside product name must not hide an unsupported GIS certificate');
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
assert.ok(source.includes("'joint','공동수급 금지','ok'"),
 'standalone applicants must not be blocked by no-consortium rules');
assert.ok(source.includes("나라장터 공식 낙찰"));

// Verify the ACTUAL direct-source comparator, independent of AI snapshots.
assert.ok(!source.includes('rfpAiForJob'),'removed AI must not re-enter verdict path');
assert.ok(!source.includes('ai-qualification.json'),'web UI must not load old model data');
const cmpMod=new Function('jobSoftwareScope','jobEligibilityData','productionRequirementCheck',
 'jobEvidenceData','regionRequirementCheck','rfpSnapshotForJob','partnerRegisteredCode',
 part('const directRfpCache=new WeakMap();','function productionRequirementCheck(x,p){')+
 part('function officialSourceCoverage(rfp,evidence){','function matchRowsHTML(x,p){')+
 'return {comparePartnerJob,officialReviewCoverage,officialSourceCoverage,directRfpRequirements};'
)(()=> 'candidate',()=>({ok:true,complete:true,requirements:[]}),
 ()=>({applicable:false}),
 x=>x.evidence||null,()=>({status:'unknown',reason:'region not queried'}),
 x=>x.rfp||null,(p,code)=>(p.registeredCodes||[]).includes(code)?true:null);
const smeBid={condition:'중소기업확인서 소기업만 참여',partnerBidMode:''};
const smePartner={smeRecord:{size:'소기업',issuedAt:'2026-04-01',validState:'valid'},
 smeCheckedAt:'2026-10-12T05:04:00Z'};
const smeRows=cmpMod.comparePartnerJob(smeBid,smePartner).rows;
assert.equal(smeRows.find(q=>q.id==='sme-issuance').status,'ok');
assert.equal(smeRows.find(q=>q.id==='sme-validity').status,'ok');
assert.equal(smeRows.find(q=>q.id==='sme-scale').status,'ok');
assert.equal(smeRows.find(q=>q.id==='sme-expiry').status,'ok');
assert.equal(cmpMod.comparePartnerJob(smeBid,{}).rows.find(q=>q.id==='sme-issuance').status,'pending');
assert.ok(source.includes("refreshPartnerSme(p)"));
assert.ok(source.includes("sme-cert-snapshot.json"));

// Historical competition: only the exact past notice's positive official
// prtcptCnum counts; unknown/zero must never imply a one-bidder award.
const past=new Function('kstISO','localStorage','document','g2bFetch','renderJobs','jobAmountLabel',
 'collapseSimilarNotices','jobs','g2bLiveJobs','jobSoftwareScope','jobTimeInfo','htmlEscape',
 part('const COMPETITION_STORE=','function repeatYears(x){')+
 'return {officialAwardCount,officialAwardDetails,previousOfficialBids,pastCompetitionSummary,winnerTrendLabel,bidAdvantageFromHistory,bidAdvantageOrder,bidAdvantageMarkup,mergeOfficialAwardSnapshot,competitionByNotice,contractByBid,contractEvidenceText};'
)(()=> '2026-10-17',{getItem:()=>null,setItem:()=>{}},
 {querySelectorAll:()=>[],getElementById:()=>null},
 async()=>({ok:true,items:[]}),()=>{},v=>String(v)+'원',()=>[],[],[],()=> 'candidate',()=>({key:'open'}),value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'));
const pBid='R25BK00820928';
assert.equal(past.officialAwardCount({items:[
 {bidNtceNo:pBid,bidNtceOrd:'000',prtcptCnum:'2'}]},pBid),2,
 'a real, positive participant field may be shown as historical count');
assert.equal(past.officialAwardCount({items:[
 {bidNtceNo:'R25BK00000001',prtcptCnum:'1'}]},pBid),null,
 'counts from unrelated awards cannot be assigned to this notice');
assert.equal(past.officialAwardCount({items:[
 {bidNtceNo:pBid,prtcptCnum:''}]},pBid),null);
assert.equal(past.officialAwardCount({items:[
 {bidNtceNo:pBid,prtcptCnum:'0'}]},pBid),null,
 'zero is not a confirmed one-bidder tender');
const pastBid={repeatHistory:[
 {year:2026,verified:true},
 {year:2025,bidNo:pBid,verified:true},
 {year:2024,bidNo:'20241237450',verified:true},
 {year:2023,bidNo:'20231245028',verified:false}]};
assert.equal(past.previousOfficialBids(pastBid).length,2);
assert.equal(past.pastCompetitionSummary(pastBid).low,false);
past.competitionByNotice.set(pBid,{count:2,checkedAt:Date.now()});
assert.equal(past.pastCompetitionSummary(pastBid).latest.count,2);
assert.equal(past.pastCompetitionSummary(pastBid).low,true);
assert.equal(past.bidAdvantageFromHistory(past.pastCompetitionSummary(pastBid)).level,2,
 'one verified low-bid year without a confirmed incumbent merits two research chips');
assert.equal((past.bidAdvantageMarkup(past.pastCompetitionSummary(pastBid),true).match(/class="advantage-pill"/g)||[]).length,2);
past.competitionByNotice.set('20241237450',{count:9,checkedAt:Date.now()});
assert.equal(past.pastCompetitionSummary(pastBid).low,false,
 'past 9-bidder year cannot be labeled uniformly low competition');
assert.equal(past.bidAdvantageFromHistory(past.pastCompetitionSummary(pastBid)).level,null);
assert.equal(past.bidAdvantageFromHistory({samples:[],low:false}).kind,'unknown');
assert.ok(past.bidAdvantageMarkup({samples:[],low:false},true).includes('data-advantage-tier="unrated"'));
assert.ok(past.bidAdvantageMarkup({samples:[],low:false},false).includes('유리도 평가 제외'));

// An official award record includes the winner, paid amount and bid rate.
// These are historic facts, NOT forecasts for the present notice.
const awardInfo=past.officialAwardDetails({items:[
 {bidNtceNo:pBid,bidNtceOrd:'000',prtcptCnum:'2',sucsfbidRate:'88.37',
  sucsfbidAmt:'165000000',bidwinnrNm:'직전 낙찰사',bidwinnrBizno:'123-45-67890',
  fnlSucsfDate:'2025-09-02'},
 {bidNtceNo:'R25BK00000009',prtcptCnum:'1',bidwinnrNm:'엉뚱한 낙찰사'}
]},pBid);
assert.deepEqual({count:awardInfo.count,rate:awardInfo.rate,amount:awardInfo.amount,
 winner:awardInfo.winner,winnerBizno:awardInfo.winnerBizno},
 {count:2,rate:88.37,amount:165000000,winner:'직전 낙찰사',winnerBizno:'1234567890'});
assert.equal(past.officialAwardDetails({items:[
 {bidNtceNo:pBid,prtcptCnum:'',sucsfbidRate:'',sucsfbidAmt:''}]},pBid).rate,null);
assert.equal(past.officialAwardDetails({items:[
 {bidNtceNo:pBid,prtcptCnum:'1',sucsfbidRate:'250.0'}]},pBid).rate,null);
assert.equal(past.officialAwardDetails({items:[
 {bidNtceNo:pBid,prtcptCnum:'0',bidwinnrBizno:'123'}]},pBid).winnerBizno,'');
past.competitionByNotice.set(pBid,{...awardInfo,checkedAt:Date.now()});
past.competitionByNotice.set('20241237450',{count:2,winnerBizno:'1234567890',winner:'직전 낙찰사',checkedAt:Date.now()});
assert.equal(past.pastCompetitionSummary(pastBid).sameWinner,true,
 'same verified contractor business ID across years is incumbent evidence');
assert.equal(past.bidAdvantageFromHistory(past.pastCompetitionSummary(pastBid)).level,1);
assert.equal((past.bidAdvantageMarkup(past.pastCompetitionSummary(pastBid),true).match(/class="advantage-pill"/g)||[]).length,1);
past.competitionByNotice.set('20241237450',{count:2,winnerBizno:'9999999999',winner:'다른 업체',checkedAt:Date.now()});
assert.equal(past.pastCompetitionSummary(pastBid).sameWinner,false,
 'different winner across years must not be called an incumbent');
assert.equal(past.pastCompetitionSummary(pastBid).changedWinner,true);
assert.equal(past.pastCompetitionSummary(pastBid).lowRecentPair,true);
assert.equal(past.bidAdvantageFromHistory(past.pastCompetitionSummary(pastBid)).level,3);
assert.equal((past.bidAdvantageMarkup(past.pastCompetitionSummary(pastBid),true).match(/class="advantage-pill"/g)||[]).length,3);
assert.equal(past.bidAdvantageOrder({level:3}),0);
assert.ok(past.bidAdvantageOrder({level:2})<past.bidAdvantageOrder({level:1}));
assert.ok(past.bidAdvantageOrder({level:1})<past.bidAdvantageOrder({level:null,kind:'unknown'}));
assert.ok(past.winnerTrendLabel(past.pastCompetitionSummary(pastBid)).includes('낙찰업체 변경'));
past.competitionByNotice.set('20241237450',{count:2,winnerBizno:'',winner:'직전 낙찰사',checkedAt:Date.now()});
assert.equal(past.pastCompetitionSummary(pastBid).changedWinner,false,
 'names cannot prove a winner change without valid business IDs');
assert.equal(past.pastCompetitionSummary(pastBid).lowRecentPair,false);
past.competitionByNotice.set('20241237450',{count:3,winnerBizno:'9999999999',checkedAt:Date.now()});
assert.equal(past.pastCompetitionSummary(pastBid).changedWinner,true);
assert.equal(past.pastCompetitionSummary(pastBid).lowRecentPair,false,
 'a 3-participant year is not low competition');
past.contractByBid.set(pBid,{confirmed:true,count:1,source:'계약정보서비스',
 amount:200000000,date:'2025-10-01'});
assert.ok(past.contractEvidenceText(pBid).includes('공고·업체번호 일치'));
assert.ok(!past.contractEvidenceText(pBid).includes('이행 완료'));
past.contractByBid.set(pBid,{confirmed:true,count:3,source:'계약정보서비스',
 contractNumbers:['R25TA0057644400','R25TA0057644401','R25TA0057644402'],
 amount:247500000,date:'2025-05-27'});
const contractSummary=past.contractEvidenceText(pBid);
assert.ok(contractSummary.includes('고유 계약번호 3건'));
assert.ok(contractSummary.includes('R25TA0057644402'));
assert.ok(contractSummary.includes('첫 조회 계약 금액'));
assert.ok(contractSummary.includes('전체 합산금액 아님'));
assert.ok(source.includes('const exactContracts=arr=>'),
 'contract UI must deduplicate exact signed contract references');
assert.ok(source.includes('/contract-notice?bidNo='),
 'missing-contract-process rows must trigger the official contract-register check');
assert.ok(source.includes('data-incumbent-id'));
assert.ok(source.includes('data-verdict-filter="low-changed"'));
assert.ok(source.includes('data-verdict-filter="low-incumbent"'));
assert.ok(source.includes("bidAdvantageFromHistory(pastCompetitionSummary(a.x))"),
 'historic opportunity is integrated into the actual sorting comparator');
assert.ok(source.includes('opportunityMarkup'),
 'visible card must carry the historical opportunity indicator');
assert.ok(!source.includes('const competitionRetryAfter=new Map()'),
 'browser must not maintain a parallel official-award retry queue');
const cacheOnly=source.slice(source.indexOf('async function loadPastCompetitionForJobs('),
 source.indexOf('function activeRecurringForResearch('));
assert.ok(cacheOnly.includes('await loadOfficialAwardCacheFromServer()'),
 'historical browser actions must use persisted server cache');
assert.ok(!cacheOnly.includes("g2bFetch('/awards?"),
 'sorting and filtering must not spend the official award API quota');
assert.ok(source.includes('loadOfficialAwardSnapshot()'));
assert.ok(source.includes('loadOfficialAwardCacheFromServer()'),
 'persistent worker DB award cache must be loaded on real page initialization');
assert.ok(source.includes("/award-cache?limit=200&offset="),
 'one paged read of cached historic awards must replace repeat browser upstream lookups');

const verifiedSnapshot=JSON.parse(require('node:fs').readFileSync(
 require('node:path').join(__dirname,'../startup-support/official-awards-snapshot.json'),'utf8'));
assert.equal(verifiedSnapshot.source,'나라장터 낙찰정보서비스');
assert.ok(verifiedSnapshot.records.length>=25);
const verifiedAt=Date.parse(verifiedSnapshot.verifiedAt);
// Prior synthetic test overwrote this exact notice with a newer fake winner:
// remove the fixture before verifying that real snapshot evidence imports.
past.competitionByNotice.delete('20241237450');
const sampleExtra=past.mergeOfficialAwardSnapshot(verifiedSnapshot,verifiedAt+86400000);
assert.ok(sampleExtra>=9,'historical winners from exact official results must be reusable without live API calls');
assert.equal(past.competitionByNotice.get('R25BK01238764').winnerBizno,'1018654725');
assert.equal(past.competitionByNotice.get('20241237450').winnerBizno,'1018654725');
assert.equal(past.competitionByNotice.get('20241122476').count,1);
assert.equal(past.competitionByNotice.get('R25BK01241784').winnerBizno,'3058195207');
assert.equal(past.competitionByNotice.get('20241217271').winnerBizno,'3148187981');
const statsBid={repeatHistory:[{year:2026,verified:true},
 {year:2025,bidNo:'R25BK01241784',verified:true},
 {year:2024,bidNo:'20241217271',verified:true}]};
assert.equal(past.bidAdvantageFromHistory(past.pastCompetitionSummary(statsBid)).level,3);

assert.equal(past.mergeOfficialAwardSnapshot({...verifiedSnapshot,records:[
 {bidNo:'R25BK00000099',count:0,winnerBizno:'1018654725',amount:1,winner:'fake',rate:99}
]},verifiedAt+86400000),0,'an unknown or zero-participant award is not confirmed');
assert.equal(past.mergeOfficialAwardSnapshot(verifiedSnapshot,verifiedAt+46*86400000),0,
 'stale award snapshots must not persist as fresh verification');
assert.equal(past.mergeOfficialAwardSnapshot(verifiedSnapshot,verifiedAt-1),0,
 'future-dated snapshots must not masquerade as verified results');
assert.ok(source.includes("if(row.source==='조회 실패')continue"));


assert.ok(source.includes('sucsfbidRate'));

const changeMod=new Function('jobBidIdentity','jobEvidenceData','htmlEscape','jobAmountLabel',
 'activeDetailJobId','getJobById','g2bFetch','renderJobDetail',
 part('var bidChangePriceCache=','function normalizedRegion(x){')+
 'return {bidChangePriceMarkup,bidChangePriceCache};'
)(x=>({bidNo:'R26BK01756420',order:'000'}),
 ()=>({noticeDocuments:{preSpecificationNo:'20260001234'}}),
 v=>String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'),
 v=>v+'원',null,()=>null,async()=>({}),()=>{});
const extraBid={id:'g2b-servc-R26BK01756420-000'};
assert.ok(changeMod.bidChangePriceMarkup(extraBid).includes('20260001234'));
assert.ok(changeMod.bidChangePriceMarkup(extraBid).includes('조회 전'));
changeMod.bidChangePriceCache.set('R26BK01756420:000',{
 changeHistory:{ok:true,complete:true,totalCount:1,records:[
  {order:'001',changedAt:'2026-10-12',reason:'제출기한 조정 <script>'}]},
 baseAmount:{ok:true,complete:true,records:[
  {order:'001',baseAmount:'150000000'}]}
});
const extraHtml=changeMod.bidChangePriceMarkup(extraBid);
assert.ok(extraHtml.includes('기초금액'));
assert.ok(extraHtml.includes('150000000원'));
assert.ok(extraHtml.includes('&lt;script&gt;')&&!extraHtml.includes('<script>'));
assert.ok(source.includes("'/bid-change-price?bidNo=")||
 source.includes("g2bFetch('/bid-change-price?bidNo="));

// Same-type, same-code clauses are independent until quotation actually repeats.
const quote='입찰참가자격으로 직접생산확인증명서 8111189901 소지';
const bidSource={status:'text_extracted_requires_review',manifestComplete:true,
 attachmentManifestCount:1,reviewComplete:false,requiredConditionsComplete:false,
 files:[{name:'입찰공고문.hwp',readable:true,sourceSha256:'a'.repeat(64),
  sourceTextScanComplete:true,unmatchedQualificationAnchorCount:0,topics:{},
  clauseCandidates:[
   {type:'direct_production',codes:['8111189901'],sourceText:quote,explicitMust:true},
   {type:'region_restriction',codes:[],sourceText:'입찰참가자격 서울 소재 필수',explicitMust:true},
   {type:'region_restriction',codes:[],sourceText:'입찰참가자격 양천구 소재 필수',explicitMust:true},
   {type:'direct_production',codes:['8111189901'],sourceText:quote,explicitMust:true},
   {type:'staff_proof',codes:[],sourceText:'제안서 평가점수',explicitMust:false}
  ]}]};
const items=cmpMod.directRfpRequirements({rfp:bidSource});
assert.equal(items.length,3,'exact duplicates collapse; independent mandatory conditions remain');
assert.equal(items.filter(x=>x.type==='region_restriction').length,2);
const bidEvidence={attachments:{ok:true,complete:true,items:[{name:'입찰공고문.hwp'}]}};
const bidRows=cmpMod.comparePartnerJob({rfp:bidSource,evidence:bidEvidence,condition:''},smePartner).rows;
assert.equal(bidRows.filter(x=>x.id.startsWith('source-')).length,2,
 'display one pending group per type, not one row per snippet');
assert.match(bidRows.find(x=>x.id==='source-region_restriction').label,/2구절/);
assert.equal(bidRows.find(x=>x.id==='source-direct_production').status,'pending',
 'source citation without a current SMPP certificate must stay pending');
assert.equal(cmpMod.officialSourceCoverage(bidSource,bidEvidence),true);
assert.equal(cmpMod.officialReviewCoverage(bidSource,bidEvidence),false,
 'all text scanned is not a confirmed qualification review');

const fullyChecked={...bidSource,reviewComplete:true,requiredConditionsComplete:true,
 files:[{...bidSource.files[0],clauseCandidates:[]}]};
const completion=cmpMod.comparePartnerJob({rfp:fullyChecked,evidence:bidEvidence,condition:''},{});
assert.equal(completion.complete,true,'only fully reviewed complete conditions allow eligibility proof');
assert.equal(completion.rows.find(x=>x.id==='attachment').status,'ok');
assert.equal(cmpMod.comparePartnerJob({rfp:bidSource,evidence:bidEvidence,condition:''},{}).complete,false);
// Actual full pipeline: complete, simple, source-cited conditions must
// be able to reach ready WITHOUT impossible hard-coded review flags.
const eligibleSource={...bidSource,files:[{...bidSource.files[0],
 qualificationAnchorCount:1,clauseCandidates:[{
 type:'industry_code',codes:['1468'],
 sourceText:'입찰참가자격 업종코드 1468 등록한 자',explicitMust:true}]}]};
const eligibleBid={rfp:eligibleSource,evidence:bidEvidence,condition:''};
const eligiblePartner={...smePartner,registryCheckedAt:'2026-10-16',
 registryComplete:true,registeredCodes:['1468']};
const eligibleProof=cmpMod.comparePartnerJob(eligibleBid,eligiblePartner);
assert.equal(eligibleProof.complete,true,
 'complete one-code public notice must no longer be structurally forced to 0');
const realVerdict=new Function('jobTimeInfo','jobSoftwareScope','jobQualificationVerdict',
 'comparePartnerJob','rfpSnapshotForJob',
 part('function participationVerdict(x,p){','function participationStrip(x,companies){')+
 'return participationVerdict;'
)(()=>({key:'open'}),()=> 'candidate',
 ()=>({type:'industry_match'}),cmpMod.comparePartnerJob,x=>x.rfp);
assert.equal(realVerdict(eligibleBid,eligiblePartner).type,'ready',
 'actual UI verdict must be reachable for completely proven simple conditions');
const disqualified={...eligibleSource,files:[{...eligibleSource.files[0],
 clauseCandidates:[...eligibleSource.files[0].clauseCandidates,
 {type:'staff_proof',sourceText:'기술인력 필수 자격증 증빙 요구',explicitMust:true}]}]};
assert.equal(realVerdict({...eligibleBid,rfp:disqualified},eligiblePartner).type,'ready',
 'unverified staff evidence stays a candidate rather than being excluded');
assert.equal(realVerdict({...eligibleBid,rfp:disqualified},eligiblePartner).verified,false,
 'unverified staff evidence must never be called fully confirmed');
assert.equal(realVerdict(eligibleBid,eligiblePartner).verified,true,
 'independently checked complete source conditions can be marked confirmed');

const noFiles={reviewComplete:true,requiredConditionsComplete:true,files:[],
 noticeTextReviewed:true,noticeSourceUrl:'https://www.g2b.go.kr/notice',noticeSha256:'verified-sha'};
const noFilesEvidence={attachments:{ok:true,complete:true,items:[]},
 noticeDocuments:{ok:true,complete:true,count:0}};
assert.equal(cmpMod.officialReviewCoverage(noFiles,noFilesEvidence),true,
 'complete official notice can qualify without an attachment');
assert.equal(cmpMod.officialReviewCoverage({...noFiles,noticeSha256:''},noFilesEvidence),false);
assert.equal(cmpMod.officialReviewCoverage(noFiles,{attachments:{ok:true,complete:true,items:[]}}),false);
assert.equal(cmpMod.officialSourceCoverage({...bidSource,manifestComplete:false},bidEvidence),false);
assert.equal(cmpMod.officialSourceCoverage({...bidSource,files:[
 {...bidSource.files[0],sourceTextScanComplete:false}]},bidEvidence),false);

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

// Default-included screening: unknown evidence is a provisional candidate,
// while only demonstrated disqualifications, closed notices or non-SW scope block.
const resultsById={
 industry_match:'industry_match', unverified:'unverified', missing:'missing'
};
const verdictMod=new Function('jobTimeInfo','jobSoftwareScope','jobQualificationVerdict','comparePartnerJob','htmlEscape','rfpSnapshotForJob',
 part('function participationVerdict(x,p){','function matchRowsHTML(x,p){')+
 'return {participationVerdict,participationStrip};'
)(x=>({key:x.closed?'closed':'open'}),x=>x.kind==='thng'?'out':'candidate',
 x=>({type:x.industry||'unverified',reason:'면허검증 대기'}),
 (x,p)=>({complete:!!x.full,counts:{ok:x.ok??2,pending:x.pending??1,unknown:x.unknown??1,missing:0},
    rows:x.missing?[{id:x.missingId||'license-1',status:'missing',reason:'공식 조건 불일치'}]:[]}),
 x=>String(x),x=>x.rfp||null);
const bidder={id:'changcom',short:'창컴',name:'창컴정보통신(주)',smeRecord:{size:'소기업',validState:'valid'}};
const verdict=(x,p=bidder)=>verdictMod.participationVerdict({kind:'servc',...x},p);
assert.equal(verdict({industry:'industry_match'}).type,'ready');
assert.equal(verdict({industry:'industry_match'}).label,'적격 후보');
assert.equal(verdict({industry:'industry_match'}).verified,false);
assert.equal(verdict({industry:'unverified'}).type,'ready',
 'missing license API is not evidence of disqualification');
assert.equal(verdict({industry:'unverified'}).verified,false);
assert.equal(verdict({industry:'no_restriction'}).type,'ready',
 'zero industry restrictions produce an eligible candidate');
assert.equal(verdict({industry:'no_restriction',full:false,ok:2,pending:0,unknown:1}).type,'ready');
assert.equal(verdict({industry:'no_restriction',full:false,ok:2,pending:0,unknown:1}).verified,false);
assert.equal(verdict({industry:'no_restriction',full:true,ok:2,pending:0,unknown:0}).type,'ready');
assert.equal(verdict({industry:'no_restriction',full:true,ok:2,pending:0,unknown:0}).verified,true,
 'only completely verified conditions count as confirmed');
assert.equal(verdict({industry:'missing'}).type,'blocked');
assert.equal(verdict({industry:'unverified',missing:true}).type,'ready',
 'single unmatched row in an unknown OR group cannot exclude the whole bid');
assert.equal(verdict({industry:'unverified',missing:true}).verified,false,
 'alternative license rule remains unverified rather than confirmed eligible');
assert.equal(verdict({industry:'industry_match',missing:true,missingId:'region'}).type,'blocked',
 'verified mandatory region mismatch still excludes the bid');
assert.equal(verdict({industry:'missing',missing:true}).type,'blocked',
 'official group-level license mismatch still excludes the bid');
assert.equal(verdict({industry:'industry_match',closed:true}).type,'blocked',
 'a closed notice is excluded');
assert.equal(verdict({industry:'industry_match',full:false,ok:6,pending:0,unknown:0}).type,'ready',
 'unknown attachments do not eliminate an otherwise plausible candidate');
assert.equal(verdict({industry:'industry_match',full:false,ok:6,pending:0,unknown:0}).verified,false);
assert.equal(verdict({industry:'industry_match',full:true,ok:7,pending:0,unknown:0}).verified,true);
assert.equal(verdict({industry:'industry_match',condition:'소상공인만 입찰'}).type,'blocked',
 'officially verified company size does not meet a micro-only bid');
assert.equal(verdict({industry:'industry_match',condition:'공동수급 불허'}).type,'ready',
 'a no-consortium rule does not forbid sole bidding');
assert.equal(verdict({industry:'industry_match',pending:3,unknown:5,full:false}).type,'ready',
 'unknown clauses are not a rejection and remain individually visible');
const html=verdictMod.participationStrip({id:'test-bid',condition:'',industry:'industry_match'},
  [bidder,{id:'other',short:'다른 업체',smeRecord:{size:'소기업',validState:'valid'}}]);
assert.ok(html.includes('data-partner-id="changcom"')&&html.includes('data-partner-id="other"'));
assert.ok(html.includes('적격 후보'));
assert.ok(source.includes('participationStrip(x,comparisonCompanies)'));
assert.ok(source.includes('function participationVerdict(x,p)'));
assert.ok(source.includes('job-verdict ready')===false,'do not hardcode all notices as ready');

// Status filters must be interactive, cover all currently displayed items, and
// show a reason even when the notice is outside the software candidate scope.
const filterView=new Function('partners','participationVerdict','document','htmlEscape','jobQualificationVerdict','repeatYears','pastCompetitionSummary','jobSoftwareScope','bidAdvantageFromHistory',
 part('function partnerVerdictTypes(x,selected){','function jobEntryLabel(v){')+
 'return {partnerVerdictTypes,matchesVerdictFilter,refreshVerdictFilters};'
)([bidder],(x,p)=>({type:x.verdict||'checking'}),{
 querySelectorAll:()=>[],
 getElementById:()=>({hidden:false})
},value=>String(value),(x,p)=>({type:x.industry||'unverified'}),x=>x.repeat||0,
 x=>({low:!!x.low,lowRecentPair:!!x.lowRecentPair,changedWinner:!!x.changedWinner,sameWinner:!!x.sameWinner}),
 ()=> 'candidate',
 z=>z.lowRecentPair&&z.changedWinner?{level:3}:
   z.low&&z.sameWinner?{level:1}:z.low?{level:2}:{level:null,kind:'unknown'});
for(const [verdict,type] of [['ready','ready'],['conditional','conditional'],['blocked','blocked'],['checking','checking']]){
 assert.equal(filterView.matchesVerdictFilter({verdict},null,type),true);
 assert.equal(filterView.matchesVerdictFilter({verdict},null,'all'),true);
 assert.equal(filterView.matchesVerdictFilter({verdict},null,type==='ready'?'blocked':'ready'),false);
}
assert.equal(filterView.matchesVerdictFilter({industry:'industry_match'},null,'registered'),true);
assert.equal(filterView.matchesVerdictFilter({industry:'no_restriction'},null,'no-restriction'),true);
assert.equal(filterView.matchesVerdictFilter({industry:'unverified'},null,'registered'),false);
assert.equal(filterView.matchesVerdictFilter({industry:'unverified'},null,'no-restriction'),false);
assert.equal(filterView.matchesVerdictFilter({repeat:2},null,'repeat'),true);
assert.equal(filterView.matchesVerdictFilter({repeat:1},null,'repeat'),false);
assert.equal(filterView.matchesVerdictFilter({low:true},null,'low-bids'),false,
 'past low competition only appears among eligible candidates');
assert.equal(filterView.matchesVerdictFilter({low:true,verdict:'ready'},null,'low-bids'),true,
 'confirmed past one-to-two bidders can be prioritized among eligible candidates');
assert.equal(filterView.matchesVerdictFilter({low:true,verdict:'ready'},null,'adv-2'),true);
assert.equal(filterView.matchesVerdictFilter({low:true,sameWinner:true,verdict:'ready'},null,'adv-1'),true);
assert.equal(filterView.matchesVerdictFilter({lowRecentPair:true,changedWinner:true,verdict:'ready'},null,'adv-3'),true);
assert.equal(filterView.matchesVerdictFilter({lowRecentPair:true,changedWinner:true,verdict:'blocked'},null,'adv-3'),false,
 'historical competition cannot override a verified exclusion');
assert.equal(filterView.matchesVerdictFilter({verdict:'ready'},null,'adv-1'),false,
 'unresearched history is unrated, not one chip');
assert.equal(filterView.matchesVerdictFilter({lowRecentPair:true,changedWinner:true,verdict:'ready'},
 null,'low-changed'),true, 'verified historic turnover is a visible filter');
assert.equal(filterView.matchesVerdictFilter({lowRecentPair:true,sameWinner:true,verdict:'ready'},
 null,'low-incumbent'),true, 'confirmed historic same-bizno awards are separate');
assert.equal(filterView.matchesVerdictFilter({lowRecentPair:true,sameWinner:true,verdict:'ready'},
 null,'low-changed'),false, 'incumbent is not a changed winner');
assert.equal(filterView.matchesVerdictFilter({lowRecentPair:true,changedWinner:true,verdict:'blocked'},
 null,'low-changed'),false, 'verified exclusion still blocks proposed bid');
assert.equal(filterView.matchesVerdictFilter({lowRecentPair:false,changedWinner:true,verdict:'ready'},
 null,'low-changed'),false, 'both previous years need confirmed 1-2 participants');

assert.ok(source.includes('data-verdict-filter="ready"'));
assert.ok(!source.includes('data-verdict-filter="conditional"'), 'obsolete conditional filter removed');
assert.ok(source.includes('data-verdict-filter="blocked"'));
assert.ok(source.includes('data-verdict-filter="checking"'));
assert.ok(source.includes('data-verdict-filter="registered"'));
assert.ok(source.includes('data-verdict-filter="no-restriction"'));
assert.ok(source.includes('data-verdict-filter="repeat"'));
assert.ok(source.includes('data-verdict-filter="low-bids"'));
for(const i of [1,2,3])assert.ok(source.includes('data-verdict-filter="adv-'+i+'"'));
assert.ok(source.includes('data-advantage-tier'));
assert.ok(source.includes('opportunityMarkup'));
assert.ok(source.includes('bidAdvantageOrder(bidAdvantageFromHistory(pastCompetitionSummary(a.x)))'));
assert.ok(source.includes('value="competition"'));
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
