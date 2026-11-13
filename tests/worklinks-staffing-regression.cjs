// Offline, source-grounded staffing badge test. Does not call production APIs.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const start=html.indexOf('function jobRequirementEvidence(x){');
const stop=html.indexOf('function jobDetailRequirementGrid(x){',start);
assert.ok(start>=0&&stop>start,'full staffing UI functions must exist');
const script=html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(script);
assert.doesNotThrow(()=>new Function(script[1]),'full page JS must compile');
const factory=new Function('jobBidIdentity','rfpSnapshotByNotice','jobSearchRfpState',
  'jobListRfpState','changcomPrecheckByNotice','rfpSnapshotLoading',
  'rfpSnapshotCheckedAt','htmlEscape',html.slice(start,stop)+
  'return {jobRequirementEvidence,jobRequirementBadges};');
const snapshot=(text,roles=[])=>({
 status:'text_extracted_requires_review',manifestComplete:true,
 files:[{name:'제안요청서.pdf',readable:true,sourceTextScanComplete:true,
  qualificationScanTruncated:false,clauseCandidatesTruncated:false,
  staffingRoleScanVersion:3,staffingRoleScanTruncated:false,
  staffingRoles:roles,clauseCandidates:[{type:'staff_proof',
   sourceText:text,sourceFile:'제안요청서.pdf'}]}]
});
const map=new Map([
 ['Y:000',snapshot('상주 개발인력 11개월, 투입률 75%')],
 ['N:000',snapshot('전문 기술인력 필수, 고정 인원 수는 정하지 않음')],
 ['M:000',snapshot('PM 1명, 개발자 2명',[{role:'PM',count:1,sourceFile:'제안요청서.pdf',
   sourceText:'PM 1명',scope:'document'},{role:'개발자',count:2,
   sourceFile:'제안요청서.pdf',sourceText:'개발자 2명',scope:'document'}])],
 ['E:000',snapshot('제안요청서 본문 및 예산 내역')]
]);
const model=factory(x=>({bidNo:x.noticeNumber,order:'000'}),
 map,new Map(),new Map(),new Map(),false,'',s=>String(s)
 .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'));
const expected=[
 ['Y','role_workload_only','공수 확인'],
 ['N','role_count_unspecified','인원 수 미명시'],
 ['M','role_found','역할별 인원'],
 ['E','role_unspecified','인원표 미검출']
];
for(const [noticeNumber,state,label] of expected){
 const input={noticeNumber};
 const evidence=model.jobRequirementEvidence(input);
 assert.equal(evidence.roles.status.key,state,noticeNumber);
 assert.ok(model.jobRequirementBadges(input).includes(label),noticeNumber);
}
assert.equal(model.jobRequirementEvidence({noticeNumber:'M'}).roles.items.length,2);
console.log('WORKLINKS_STAFFING_UI_REGRESSION_PASS',expected.length);
