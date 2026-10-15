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
const sandbox={rfpSnapshotForJob:(x)=>x.rfp};
vm.createContext(sandbox);
vm.runInContext(section('function directRfpRequirements(x){','function productionRequirementCheck(x,p){')+
                section('function officialSourceCoverage(rfp,evidence){','function comparePartnerJob(x,p){'),sandbox);
const file={
  name:'입찰공고문.hwp',readable:true,sourceSha256:'a'.repeat(64),
  sourceTextScanComplete:true,unmatchedQualificationAnchorCount:0,
  qualificationScanTruncated:false,clauseCandidatesTruncated:false,
  clauseCandidates:[
    {type:'industry_code',codes:['1468'],sourceFile:'입찰공고문.hwp',
      sourceText:'입찰참가자격 업종코드 1468 등록한 자',explicitMust:true},
    {type:'industry_code',codes:['1468'],sourceFile:'입찰공고문.hwp',
      sourceText:'동일 요건 반복',explicitMust:true},
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
assert.equal(sandbox.officialReviewCoverage({...source,reviewComplete:true,requiredConditionsComplete:true},evidence),true,
  'only explicitly reviewed source can clear the full audit gate');
const withExtra={...source,files:[{...file,clauseCandidates:[
  ...file.clauseCandidates,{type:'industry_code',codes:['9999'],sourceText:'업종코드 9999 필수',explicitMust:true}
]}]};
assert.equal(sandbox.directRfpRequirements({rfp:withExtra}).length,4,
  'different mandatory code cannot disappear during dedupe');
console.log('WORKLINKS_DIRECT_RFP_NO_AI_AND_FAIL_CLOSED=PASS scripts='+compiled);
