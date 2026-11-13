const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const start=html.indexOf('function jobRequirementEvidence(x){');
const end=html.indexOf('function jobDetailRequirementGrid(x){',start);
assert.ok(start>0&&end>start);
const moduleUI=new Function('jobBidIdentity','rfpSnapshotByNotice',
 'jobSearchRfpState','jobListRfpState','changcomPrecheckByNotice',
 'rfpSnapshotLoading','rfpSnapshotCheckedAt','htmlEscape',
 html.slice(start,end)+'return {jobRequirementEvidence,jobRequirementBadges};');
const f=(kind,rest)=>({kind,sourceText:'공식 문서 인력조건',sourceFile:'제안요청서.pdf',...rest});
const mk=(facts)=>({seen:true,status:'text_extracted_requires_review',
 complete:true,scanComplete:true,documentCount:1,effectiveReadableCount:1,
 staffingRoleScanComplete:true,staffingFacts:facts,staffingRoles:[]});
const states=new Map([
 ['Y:000',mk([f('workload_role',{role:'IT PM',headcount:null,manMonths:.342,durationMonths:3,allocationRate:.114}),
  f('workload_role',{role:'응용SW 개발자',headcount:null,manMonths:8.28,durationMonths:11.04,allocationRate:.75,onsite:true,sourceText:'(상주인력) 응용SW 개발자 평균 11.04 0.75 0',sourceFile:'공내역서.xlsx'}),
  f('workload_total',{manMonths:11.522})])],
 ['N:000',mk([f('headcount_recommended',{count:8,mandatory:false,minimum:true,onsite:true}),f('role_unspecified',{role:'사업관리자(PM)',headcount:null})])],
 ['X:000',mk([f('staffing_plan_required',{headcount:null,mandatory:true})])],
 ['E:000',mk([])]
]);
const app=moduleUI(x=>({bidNo:x.bidNo,order:'000'}),new Map(),states,
 new Map(),new Map(),false,'',s=>String(s)
 .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'));
const expected=[['Y','role_workload','11.522MM'],
 ['N','role_recommended','8명 권고'],['X','role_count_unspecified','인원 수 미명시'],
 ['E','role_unspecified','인원표 미검출']];
for(const [bidNo,key,label] of expected){
 const row={bidNo};const result=app.jobRequirementEvidence(row);
 assert.equal(result.roles.status.key,key,bidNo);
 assert.ok(app.jobRequirementBadges(row).includes(label),'missing badge '+bidNo);
}
assert.ok(app.jobRequirementEvidence({bidNo:'Y'}).roles.factLines[0].includes('인원 수 아님'));
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).onsite.status.key,'onsite_present');
assert.equal(app.jobRequirementEvidence({bidNo:'E'}).onsite.status.key,'not_specified');
assert.ok(app.jobRequirementBadges({bidNo:'Y'}).includes('상주인력 기재'));
assert.ok(!app.jobRequirementBadges({bidNo:'Y'}).includes('비상주 ✓'));
assert.ok(app.jobRequirementBadges({bidNo:'Y'}).includes('8.280MM'));
assert.ok(app.jobRequirementBadges({bidNo:'Y'}).includes('인원 수는 별도 명시되지 않았습니다.'));
const yonginBadgeHtml=app.jobRequirementBadges({bidNo:'Y'});
assert.ok(yonginBadgeHtml.includes('<table class="job-req-effort-table">'),'workload must be a readable table');
assert.ok(yonginBadgeHtml.includes('2개 투입항목'),'workload count is not a headcount');
const onsiteBadge=yonginBadgeHtml.slice(yonginBadgeHtml.indexOf('data-requirement="onsite"'),yonginBadgeHtml.indexOf('data-requirement="roles"'));
const workloadBadge=yonginBadgeHtml.slice(yonginBadgeHtml.indexOf('data-requirement="roles"'),yonginBadgeHtml.indexOf('<span class="job-req-tip" role="tooltip">',yonginBadgeHtml.indexOf('data-requirement="roles"')));
assert.ok(!onsiteBadge.includes('job-req-icon'),'verified onsite source is not a grey failure/info circle');
assert.ok(!workloadBadge.includes('job-req-icon'),'verified workload source is not a grey failure/info circle');
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).roles.status.key,'role_workload');
assert.ok(app.jobRequirementEvidence({bidNo:'N'}).roles.factLines[0].includes('필수 아님'));
console.log('WORKLINKS_STAFFING_FACTS_UI_PASS',expected.length);
