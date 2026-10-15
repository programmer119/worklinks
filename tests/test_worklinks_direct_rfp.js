#!/usr/bin/env node
// Deterministic frontend regression: no AI dependency, no invented approval.
'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('startup-support/index.html','utf8');
assert(!html.includes('ai-qualification.json'),'frontend must not load legacy AI snapshot');
assert(!html.includes('rfpAiForJob'),'frontend must not call legacy classifier');
let compiled=0;
for(const [,attributes,body] of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){
  if(/\bsrc\s*=|\btype\s*=\s*["'](?:application\/json|importmap)/i.test(attributes))continue;
  new vm.Script(body,{filename:'startup-support/index.html'});
  compiled++;
}
assert(compiled>0,'no inline JS was syntax checked');
function section(start,end){
 const a=html.indexOf(start),b=html.indexOf(end,a);
 assert(a>=0&&b>a,'missing direct evidence function');
 return html.slice(a,b);
}
const sandbox={rfpSnapshotForJob:(x)=>x.rfp,
 partnerRegisteredCode:(p,code)=>(p.registeredCodes||[]).includes(code)?true:null,
 regionRequirementCheck:(x,p)=>x.regionTest||{status:'unknown',reason:'unverified region'}};
vm.createContext(sandbox);
vm.runInContext(section('const directRfpCache=new WeakMap();','function productionRequirementCheck(x,p){')+
                section('function officialSourceCoverage(rfp,evidence){','function comparePartnerJob(x,p){'),sandbox);
const file={
  name:'입찰공고문.hwp',readable:true,sourceSha256:'a'.repeat(64),
  sourceTextScanComplete:true,unmatchedQualificationAnchorCount:0,
  qualificationScanTruncated:false,clauseCandidatesTruncated:false,
  clauseCandidates:[
    {type:'industry_code',codes:['1468'],sourceFile:'입찰공고문.hwp',
      sourceText:'입찰참가자격 업종코드 1468 등록한 자',explicitMust:true},
    {type:'industry_code',codes:['1468'],sourceFile:'입찰공고문.hwp',
      sourceText:'입찰참가자격 업종코드 1468 등록한 자',explicitMust:true},
    {type:'direct_production',codes:['8111189901'],
      sourceText:'직접생산확인증명서 8111189901 소지한 자',explicitMust:true},
    {type:'performance_proof',codes:[],sourceText:'제안서 실적 배점표',explicitMust:false},
    {type:'sme_certificate',codes:[],sourceText:'소기업 확인서를 소지한 자',explicitMust:true},
  ]
};
const source={status:'text_extracted_requires_review',manifestComplete:true,
  attachmentManifestCount:1,files:[file],reviewComplete:false,requiredConditionsComplete:false};
const evidence={attachments:{ok:true,complete:true,items:[{name:file.name}]}};
const rules=sandbox.directRfpRequirements({rfp:source});
assert.equal(rules.length,3,'must condense duplicates and ignore optional score text');
assert(rules.some(q=>q.type==='industry_code'&&q.codes.includes('1468')));
assert(rules.some(q=>q.type==='direct_production'&&q.codes.includes('8111189901')));
assert(sandbox.extractedRfpRequirements({rfp:source}).includes('1468'));
assert.equal(sandbox.officialSourceCoverage(source,evidence),true,'complete source coverage');
assert.equal(sandbox.officialReviewCoverage(source,evidence),false,
  'complete source text is not proof of full qualification review');
assert.equal(sandbox.officialSourceCoverage({...source,files:[{...file,sourceTextScanComplete:false}]},evidence),false);
assert.equal(sandbox.officialSourceCoverage({...source,manifestComplete:false},evidence),false);
assert.equal(sandbox.officialSourceCoverage({...source,attachmentManifestCount:2},evidence),false);
assert.equal(sandbox.officialSourceCoverage({...source,files:[{...file,sourceSha256:''}]},evidence),false);
assert.equal(sandbox.officialSourceCoverage(source,{attachments:{ok:true,complete:false,items:[{}]}}),false);
// Verified official snapshot must remain usable during a temporary 429,
// but never override a newer contradictory complete official manifest.
const recent={...source,checkedAt:new Date().toISOString()};
assert.equal(sandbox.officialSourceCoverage(recent,{}),true,
 'recent hash-checked source snapshot should survive transient API 429');
const expiredSnapshot={...source,checkedAt:new Date(Date.now()-48*3600000).toISOString()};
assert.equal(sandbox.officialSourceCoverage(expiredSnapshot,{}),false,
 'stale source may not substitute for current official manifest');
assert.equal(sandbox.officialSourceCoverage(recent,{attachments:{
 ok:true,complete:true,items:[{name:'변경된입찰공고문.hwp'}]
}}),false,'newer changed official attachment list invalidates cached review');

assert.equal(sandbox.officialReviewCoverage({...source,reviewComplete:true,requiredConditionsComplete:true},evidence),true,
  'only explicitly reviewed source can clear the full audit gate');
const withExtra={...source,files:[{...file,clauseCandidates:[
  ...file.clauseCandidates,{type:'industry_code',codes:['9999'],sourceText:'업종코드 9999 필수',explicitMust:true}
]}]};
assert.equal(sandbox.directRfpRequirements({rfp:withExtra}).length,4,
  'different mandatory code cannot disappear during dedupe');

// The former type+code dedup discarded materially different mandatory rules.
const distinctConditions={...source,files:[{...file,clauseCandidates:[
 ...file.clauseCandidates,
 {type:'industry_code',codes:['1468'],sourceText:'1468 등록 외에 별도 면허증도 필수',explicitMust:true},
 {type:'region_restriction',codes:[],sourceText:'사업장 서울 소재 필수',explicitMust:true},
 {type:'region_restriction',codes:[],sourceText:'특정 구에 있는 사무소 필수',explicitMust:true},
 {type:'staff_proof',codes:[],sourceText:'필수 경력 3년 이상',explicitMust:true},
 {type:'staff_proof',codes:[],sourceText:'필수 자격증 보유',explicitMust:true},
 {type:'performance_proof',codes:[],sourceText:'제안서 실적 점수',explicitMust:false},
]}]};
const distinct=sandbox.directRfpRequirements({rfp:distinctConditions});
assert.equal(distinct.length,8,'different mandatory clauses must not collapse into same type/code');
assert.equal(distinct.filter(q=>q.type==='industry_code').length,2);
assert.equal(distinct.filter(q=>q.type==='region_restriction').length,2);
assert.equal(distinct.filter(q=>q.type==='staff_proof').length,2);
assert(!distinct.some(q=>q.sourceText==='제안서 실적 점수'));
assert(sandbox.extractedRfpRequirements({rfp:distinctConditions}).includes('특정 구에 있는 사무소 필수'));
assert.equal(sandbox.officialReviewCoverage(distinctConditions,evidence),false,
 'retaining all candidates does not authorize an eligibility verdict');

const matchedPartner={
 registeredCodes:['1468'],
 smeRecord:{validState:'valid',size:'소기업'},smeCheckedAt:'2026-10-16'
};
assert.equal(sandbox.officialSourceClauseResult({
 type:'industry_code',codes:['1468'],sourceText:'입찰참가자격 업종코드 1468 등록한 자'
},{},matchedPartner).status,'ok','single official registration can pass its own basic requirement');
assert.equal(sandbox.officialSourceClauseResult({
 type:'industry_code',codes:['1468','1169'],sourceText:'1468 또는 1169'
},{},matchedPartner).status,'unknown','OR clauses may not be assumed satisfied');
assert.equal(sandbox.officialSourceClauseResult({
 type:'industry_code',codes:['9999'],sourceText:'업종코드 9999'
},{},matchedPartner).status,'unknown','missing company entry is not proof of an exclusive prerequisite');
assert.equal(sandbox.officialSourceClauseResult({
 type:'sme_certificate',codes:[],sourceText:'중소기업확인서 필수'
},{},matchedPartner).status,'ok','valid SMPP record matches general SME condition');
assert.equal(sandbox.officialSourceClauseResult({
 type:'sme_certificate',codes:[],sourceText:'소상공인만 참가 가능'
},{},matchedPartner).status,'unknown','SME must not pass a micro-only condition');
assert.equal(sandbox.officialSourceClauseResult({
 type:'region_restriction',codes:[],sourceText:'지역제한 서울'
},{regionTest:{status:'ok',reason:'서울 일치'}},matchedPartner).status,'ok');
assert.equal(sandbox.officialSourceClauseResult({
 type:'region_restriction',codes:[],sourceText:'지역제한 제주'
},{regionTest:{status:'missing',reason:'제주 불일치'}},matchedPartner).status,'unknown',
 'a source fragment alone cannot override the exact region rules');
assert.equal(sandbox.officialSourceClauseResult({
 type:'joint_participation',codes:[],sourceText:'공동수급 불가 단독 참가'
},{},matchedPartner).status,'ok','no consortium does not disqualify sole bidder');
assert.equal(sandbox.officialSourceClauseResult({
 type:'direct_production',codes:['8111189901'],sourceText:'직접생산확인증명서 필수'
},{},matchedPartner).status,'pending','historical certificate is not live SMPP validity');
assert.equal(sandbox.officialSourceClauseResult({
 type:'staff_proof',codes:[],sourceText:'자격증을 소지한 투입인력 필수'
},{},matchedPartner).status,'unknown','staff evidence may not be fabricated');

// Full review can now be established for a genuinely simple, completely
// scanned official source without a permanently false extraction flag.
const simple={...source,files:[{...file,qualificationAnchorCount:1,
 clauseCandidates:[file.clauseCandidates[0]]}]};
const company={...matchedPartner,registryCheckedAt:'2026-10-16',registryComplete:true};
assert.equal(sandbox.officialReviewCoverage(simple,evidence,{rfp:simple},company),true,
 'single fully cited registered-industry clause should have a reachable review path');
assert.equal(sandbox.officialReviewCoverage({
 ...simple,files:[{...simple.files[0],clauseCandidates:[
  ...simple.files[0].clauseCandidates,
  {type:'performance_proof',sourceText:'입찰참가자격 유사실적 증명 필수',explicitMust:true}
 ]}]},evidence,{rfp:simple},company),false,'additional unverified qualification must veto approval');
assert.equal(sandbox.officialReviewCoverage({
 ...simple,files:[{...simple.files[0],clauseCandidates:[
  {...simple.files[0].clauseCandidates[0],codes:['9999']}]}]
},evidence,{rfp:simple},company),false,'missing industry cannot auto qualify');
assert.equal(sandbox.officialReviewCoverage({
 ...simple,files:[{...simple.files[0],qualificationAnchorCount:0}]
},evidence,{rfp:simple},company),false,'empty qualification audit cannot certify a notice');
assert.equal(sandbox.officialReviewCoverage(simple,evidence,{rfp:simple},
 {...company,registryComplete:false}),false,'incomplete company registry must veto');

const actual=JSON.parse(fs.readFileSync('startup-support/rfp-clauses.json','utf8')).byNotice;
const preferred=['R26BK01756420:000','R26BK01753188:000',
 'R26BK01755213:000','R26BK01747543:000'];
const sampleIds=[...preferred.filter(id=>actual[id]&&actual[id].files?.length),
 ...Object.keys(actual).reverse().filter(id=>actual[id]?.files?.some(f=>f.readable))];
const checked=new Set();
for(const noticeId of sampleIds){
 if(checked.has(noticeId))continue;
 checked.add(noticeId);
 const notice=actual[noticeId];
 const extracted=sandbox.directRfpRequirements({rfp:notice});
 const meta={attachments:{
  ok:true,complete:true,items:notice.files.map(f=>({name:f.name}))}};
 const scan=sandbox.officialSourceCoverage(notice,meta);
 const final=sandbox.officialReviewCoverage(notice,meta);
 assert(!final,'automatic text extraction may not count as full qualification review');
 console.log('WORKLINKS_DIRECT_RFP_SAMPLE',JSON.stringify({
  id:noticeId,files:notice.files.length,sourceCandidates:extracted.length,
  codes:[...new Set(extracted.flatMap(c=>c.codes))],
  fullSourceScan:scan,fullQualificationReview:final
 }));
 if(checked.size>=4)break;
}
assert.equal(checked.size,4,'expected four retained real official RFPs');

console.log('WORKLINKS_DIRECT_RFP_NO_AI_AND_FAIL_CLOSED=PASS scripts='+compiled);
