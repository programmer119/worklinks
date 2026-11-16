#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const begin=html.indexOf('function jobRequirementEvidence(x){');
const end=html.indexOf('function jobDetailRequirementGrid(x){',begin);
assert(begin>0&&end>begin);
const snippet=html.slice(begin,end);
const key='R26BK01810506:001';
const bid={noticeNumber:'R26BK01810506',noticeOrder:'001'};
const oldBase={
 sourceAvailable:true,seen:true,complete:true,scanComplete:true,
 staffingRoleScanComplete:true,status:'text_extracted_requires_review',
 documentCount:1,readableCount:1,effectiveReadableCount:1,
 parserCurrent:true,versionSource:'last_success',classificationVersion:23,
 hwpxReaderVersion:3,staffingRoleVersions:[4],staffingFactVersions:[2],
 checkedAt:'2026-11-15T12:00:00Z',
 staffingRoles:[],staffingFacts:[],excerpts:[],
};
const positiveOld={...oldBase,
 staffingRoles:[{role:'개발자',count:2,sourceFile:'제안요청서.pdf',
                sourceText:'개발자 2명 투입'}],
 excerpts:[
   {type:'staff_proof',text:'입찰 참가 시 4대보험 가입 증명서 제출 필수',sourceFile:'제안요청서.pdf'},
   {type:'staff_proof',text:'상주 인력 2명 배치 의무',sourceFile:'제안요청서.pdf'}
 ]};
const oldNoRequirement={...oldBase};
function render(savedRow){
 const records=new Map([[key,savedRow]]);
 const f=new Function(
  'jobBidIdentity','rfpSnapshotByNotice','jobSearchRfpState','jobListRfpState',
  'changcomPrecheckByNotice','rfpScanProvenanceByNotice','rfpSnapshotLoading',
  'rfpSnapshotCheckedAt','rfpCardEvidenceFetchErrors','htmlEscape',
  snippet+'return {jobRequirementEvidence,jobRequirementBadges};'
 );
 return f(
  x=>({bidNo:x.noticeNumber,order:x.noticeOrder||'000'}),
  new Map(),records,new Map(),new Map(),new Map(),false,'',new Set(),
  v=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')
 );
}
const failed={
 sourceAvailable:true,seen:true,complete:false,scanComplete:false,
 staffingRoleScanComplete:false,status:'text_extraction_incomplete',
 documentCount:2,readableCount:1,effectiveReadableCount:1,
 classificationVersion:23,hwpxReaderVersion:3,
 staffingRoleVersions:[0],staffingFactVersions:[0],
 parserCurrent:false,versionSource:'checkpoint',
 checkedAt:'2026-11-16T02:00:00Z',
 staffingRoles:[],staffingFacts:[],excerpts:[]
};
for(const [name,previous,expected] of [
 ['positive',positiveOld,['required_at_bid','onsite','role_found']],
 ['negative',oldNoRequirement,['not_required','offsite','role_unspecified']],
]){
 const {jobRequirementEvidence,jobRequirementBadges}=render({
    ...failed,lastSuccessfulState:previous
 });
 const result=jobRequirementEvidence(bid);
 assert.deepEqual([result.insurance.status.key,result.onsite.status.key,
   result.roles.status.key],expected,name);
 assert.deepEqual(result.meta.lastSuccessfulFields,
    ['insurance','onsite','roles']);
 const html=jobRequirementBadges(bid);
 assert(!html.includes('상주 확인중'),name);
 assert(!html.includes('인원 확인실패'),name);
 assert(!html.includes('4대보험 확인실패'),name);
 assert(html.includes('이전 판독 결과 · 재검증 중'),
   'tooltip must distinguish stale-but-successful '+name);
}
// When a new source-verified current-version scan finishes, replace the old
// result rather than showing outdated success indefinitely.
const nowComplete={...oldBase,versionSource:'checkpoint',
 checkedAt:'2026-11-16T04:00:00Z',
 lastSuccessfulState:positiveOld};
const current=render(nowComplete).jobRequirementEvidence(bid);
assert.equal(current.meta.lastSuccessfulFields,undefined);
assert.equal(current.insurance.status.key,'not_required');
assert.equal(current.onsite.status.key,'offsite');
assert.equal(current.roles.status.key,'role_unspecified');
// If the source was changed, the API is forbidden to attach a prior state.
const changed=render({...failed,lastSuccessfulState:undefined}).jobRequirementEvidence(bid);
assert.equal(changed.meta.lastSuccessfulFields,undefined);
assert(!['not_required','offsite','role_unspecified'].every((x,i)=>
  [changed.insurance.status.key,changed.onsite.status.key,
   changed.roles.status.key][i]===x));
console.log('RFP_THREE_THUMBNAILS_LAST_SUCCESS_SURVIVES_RESCAN_BUT_NEW_SUCCESS_WINS=PASS');
