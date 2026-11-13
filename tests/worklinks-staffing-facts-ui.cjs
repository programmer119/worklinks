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
 ['E:000',mk([])],
 ['M:000',mk([f('workload_role',{role:'응용SW 개발자',durationMonths:10,allocationRate:.5,onsite:true,sourceText:'(상주인력) 응용SW 개발자'}),
  f('workload_role',{role:'보안 담당자',durationMonths:10,allocationRate:.5,onsite:true,sourceText:'(상주인력) 보안 담당자'})])]
]);
const app=moduleUI(x=>({bidNo:x.bidNo,order:'000'}),new Map(),states,
 new Map(),new Map(),false,'',s=>String(s)
 .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'));
const expected=[['Y','role_found','역할별 인원 1명'],
 ['N','role_recommended','8명 권고'],['X','role_count_unspecified','인원 수 미명시'],
 ['E','role_unspecified','인원표 미검출']];
for(const [bidNo,key,label] of expected){
 const row={bidNo};const result=app.jobRequirementEvidence(row);
 assert.equal(result.roles.status.key,key,bidNo);
 assert.ok(app.jobRequirementBadges(row).includes(label),'missing badge '+bidNo);
}
assert.ok(app.jobRequirementEvidence({bidNo:'Y'}).roles.factLines[0].includes('인원 수 아님'));
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).roles.items.length,1);
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).roles.items[0].roleName,'응용SW 개발자');
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).roles.items[0].count,1);
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).roles.items[0].inferredFromWorkload,true);
assert.equal(app.jobRequirementEvidence({bidNo:'M'}).roles.status.key,'role_workload','multiple onsite rows must not imply a single person');
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).onsite.status.key,'onsite_present');
assert.equal(app.jobRequirementEvidence({bidNo:'E'}).onsite.status.key,'not_specified');
assert.ok(app.jobRequirementBadges({bidNo:'Y'}).includes('상주 확인'));
assert.ok(!app.jobRequirementBadges({bidNo:'Y'}).includes('비상주 ✓'));
assert.ok(app.jobRequirementEvidence({bidNo:'Y'}).roles.factLines.some(v=>v.includes('8.280MM')));
assert.ok(!app.jobRequirementBadges({bidNo:'Y'}).includes('인원 미확인'));
const yonginBadgeHtml=app.jobRequirementBadges({bidNo:'Y'});
assert.ok(yonginBadgeHtml.includes('역할별 인원 1명'),'the thumbnail must show the person count');
assert.ok(yonginBadgeHtml.includes('<strong>응용SW 개발자</strong>'),'the role detail must name the developer');
assert.ok(yonginBadgeHtml.includes('job-req-tip-count">1명</strong>'),'the role detail must show one person');
assert.ok(!yonginBadgeHtml.includes('공수 11.522MM'),'do not replace headcount with man-month effort');
const onsiteBadge=yonginBadgeHtml.slice(yonginBadgeHtml.indexOf('data-requirement="onsite"'),yonginBadgeHtml.indexOf('data-requirement="roles"'));
const workloadBadge=yonginBadgeHtml.slice(yonginBadgeHtml.indexOf('data-requirement="roles"'),yonginBadgeHtml.indexOf('<span class="job-req-tip" role="tooltip">',yonginBadgeHtml.indexOf('data-requirement="roles"')));
assert.ok(!onsiteBadge.includes('job-req-icon'),'verified onsite source is not a grey failure/info circle');
assert.ok(!workloadBadge.includes('job-req-icon'),'verified workload source is not a grey failure/info circle');
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).roles.status.key,'role_found');
assert.ok(app.jobRequirementEvidence({bidNo:'N'}).roles.factLines[0].includes('필수 아님'));
console.log('WORKLINKS_STAFFING_FACTS_UI_PASS',expected.length);
