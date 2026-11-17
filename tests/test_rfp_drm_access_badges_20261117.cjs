#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'..','startup-support','index.html'),'utf8');
const start=html.indexOf('function jobRequirementEvidence(x){');
const end=html.indexOf('function jobDetailRequirementGrid(x){',start);
assert(start>0&&end>start,'required card evidence functions unavailable');
const snippet=html.slice(start,end);
const bid={noticeNumber:'R26BK01825441',noticeOrder:'000'};
const key='R26BK01825441:000';
function render(saved){
  const fn=new Function(
    'jobBidIdentity','rfpSnapshotByNotice','jobSearchRfpState','jobListRfpState',
    'changcomPrecheckByNotice','rfpScanProvenanceByNotice','rfpSnapshotLoading',
    'rfpSnapshotCheckedAt','rfpCardEvidenceFetchErrors','htmlEscape',
    snippet+'return {jobRequirementEvidence,jobRequirementBadges};');
  return fn(x=>({bidNo:x.noticeNumber,order:x.noticeOrder||'000'}),
    new Map(),new Map([[key,saved]]),new Map(),new Map(),new Map(),
    false,'',new Set(),x=>String(x).replaceAll('&','&amp;')
      .replaceAll('<','&lt;').replaceAll('"','&quot;'));
}
const locked={
  sourceAvailable:true,seen:true,complete:false,scanComplete:false,
  staffingRoleScanComplete:false,status:'text_extracted_requires_review',
  documentCount:2,readableCount:1,effectiveReadableCount:1,
  staffingRoles:[],staffingFacts:[],excerpts:[],
  sourceAccess:{status:'restricted',protectedFileCount:1,
    protectedFiles:[{name:'설계내역서(상수도시설물).xlsx',
      reason:'DRMONE 원본 보호 · 권한 또는 해제된 문서 필요'}],
    otherUnreadableCount:0,isParserFailure:false}
};
const state=render(locked).jobRequirementEvidence(bid);
assert.deepEqual([state.insurance.status.key,state.onsite.status.key,
  state.roles.status.key],['source_restricted','source_restricted','source_restricted']);
const badge=render(locked).jobRequirementBadges(bid);
assert(badge.includes('보안문서')&&badge.includes('🔒'),badge);
assert(badge.includes('설계내역서(상수도시설물).xlsx'),badge);
assert(!badge.includes('확인실패')&&!badge.includes('인원 확인실패'),
  'a publicly listed DRM source must not be presented as a reader failure');
assert(!['not_required','offsite','role_unspecified'].includes(state.roles.status.key));
// Mixed content must preserve real reader errors instead of hiding them.
const mixed=render({...locked,sourceAccess:{...locked.sourceAccess,status:'mixed',
  otherUnreadableCount:1}}).jobRequirementEvidence(bid);
assert.equal(mixed.insurance.status.key,'failed');
assert.equal(mixed.roles.status.key,'failed');
// Positive requirements from other fully readable official documents remain
// valid even while a protected appendix is not open to the scanner.
const partial=render({...locked,excerpts:[
  {type:'staff_proof',text:'입찰 시 4대보험 증빙 제출 필수',sourceFile:'공고문.pdf'},
  {type:'staff_proof',text:'상주 인력 2명 배치 의무',sourceFile:'공고문.pdf'}
],staffingRoles:[{role:'개발자',count:2,sourceFile:'공고문.pdf',
    sourceText:'개발자 2명 투입'}]}).jobRequirementEvidence(bid);
assert.equal(partial.insurance.status.key,'required_at_bid');
assert.equal(partial.onsite.status.key,'onsite');
assert.equal(partial.roles.status.key,'role_found');
console.log('WORKLINKS_PUBLIC_DRM_SOURCE_SHOWN_AS_PROTECTED_NOT_SCAN_FAILURE=PASS');
