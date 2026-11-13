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
 staffingRoleScanComplete:true,staffingFacts:facts,staffingRoles:[]});
const states=new Map([
 ['Y:000',mk([f('workload_role',{role:'IT PM',headcount:null,manMonths:.342,durationMonths:3,allocationRate:.114}),f('workload_total',{manMonths:11.522})])],
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
assert.ok(app.jobRequirementEvidence({bidNo:'N'}).roles.factLines[0].includes('필수 아님'));
console.log('WORKLINKS_STAFFING_FACTS_UI_PASS',expected.length);
