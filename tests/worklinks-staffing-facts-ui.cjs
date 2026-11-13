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
 ['N:000',mk([f('headcount_recommended',{count:8,mandatory:false,minimum:true,onsite:true,
  sourceText:'* 위 인원은 분야를 조정할 수 있으나, 상주인력 월평균 8명 이상을 유지 권고',
  sourceFile:'붙임1_제안요청서.hwpx'}),f('role_unspecified',{role:'사업관리자(PM)',headcount:null})])],
 ['X:000',mk([f('staffing_plan_required',{headcount:null,mandatory:true})])],
 ['E:000',mk([])],
 ['C:000',{...mk([]),excerpts:[{text:'상주 여부 및 상주 인원은 계약 체결 후 발주기관과 협의하여 결정한다',
  sourceFile:'협의조건_제안요청서.pdf'}]}],
 ['L:000',{...mk([]),excerpts:[{text:'상주인력의 휴가 및 근무시간은 발주처와 협의하여 조정한다',
  sourceFile:'상주근무_안내서.pdf'}]}],
 ['F:000',{...mk([]),excerpts:[{text:'상주인력 2명 배치하여야 한다',
  sourceFile:'필수상주_제안요청서.pdf'}]}],
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
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).onsite.status.key,'onsite');
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).onsite.status.label,'상주 필수');
assert.equal(app.jobRequirementEvidence({bidNo:'N'}).onsite.status.key,'onsite_recommended');
assert.equal(app.jobRequirementEvidence({bidNo:'N'}).onsite.status.label,'상주 권고');
const northBadgeHtml=app.jobRequirementBadges({bidNo:'N'});
assert.ok(northBadgeHtml.includes('상주 권고'),'onsite badge must show recommendation');
const northTooltip=northBadgeHtml.slice(northBadgeHtml.indexOf('data-requirement="onsite"'),
 northBadgeHtml.indexOf('data-requirement="roles"'));
for(const fragment of ['상주인력 · 월평균','8명 이상','유지 권고 · 필수 인원 아님',
 '상주인력 월평균 8명 이상을 유지 권고','붙임1_제안요청서.hwpx']){
 assert.ok(northTooltip.includes(fragment),'missing sourced recommendation '+fragment);
}
assert.ok(!northTooltip.includes('상주 여부 미확정'),'known recommendation is not unknown');
assert.equal(app.jobRequirementEvidence({bidNo:'E'}).onsite.status.key,'offsite');
assert.equal(app.jobRequirementEvidence({bidNo:'E'}).onsite.status.label,'비상주');
assert.match(app.jobRequirementEvidence({bidNo:'E'}).onsite.status.reason,/상주 관련 조건 미검출/);
assert.equal(app.jobRequirementEvidence({bidNo:'X'}).onsite.status.key,'offsite');
assert.equal(app.jobRequirementEvidence({bidNo:'C'}).onsite.status.key,'onsite_negotiable');
assert.equal(app.jobRequirementEvidence({bidNo:'C'}).onsite.status.label,'상주 협의');
assert.equal(app.jobRequirementEvidence({bidNo:'L'}).onsite.status.key,'offsite',
 'negotiating leave or work hours does not imply negotiating onsite requirements');
assert.equal(app.jobRequirementEvidence({bidNo:'F'}).onsite.status.key,'onsite');
assert.equal(app.jobRequirementEvidence({bidNo:'F'}).onsite.status.label,'상주 필수');
const consultBadge=app.jobRequirementBadges({bidNo:'C'});
for(const fragment of ['상주 협의','상주 여부·인원','발주기관과 협의하여 결정',
 '협의조건_제안요청서.pdf']){
 assert.ok(consultBadge.includes(fragment),'consult badge missing '+fragment);
}
assert.ok(!app.jobRequirementBadges({bidNo:'L'}).includes('상주 협의'));
assert.ok(html.includes('[data-state="onsite_negotiable"] .job-req-trigger{background:#ecfccb'),
 'negotiated onsite badge must be light lime, not orange or red');
assert.ok(html.includes('[data-state="onsite"] .job-req-trigger{background:#fef2f2'),
 'mandatory onsite must be red');
assert.ok(html.includes('[data-state="onsite_recommended"] .job-req-trigger{background:#fff2e5'),
 'recommended onsite must be orange');
assert.ok(html.includes('[data-state="offsite"] .job-req-trigger{background:#dcfce7'),
 'offsite must be green');
assert.ok(app.jobRequirementBadges({bidNo:'Y'}).includes('상주 필수'));
assert.ok(app.jobRequirementBadges({bidNo:'E'}).includes('비상주'));
assert.ok(!app.jobRequirementBadges({bidNo:'E'}).includes('상주 미확정'));
assert.ok(!html.includes("label:'상주 미확정'"));
assert.ok(!html.includes("label:'상주 확인'"));
assert.ok(!app.jobRequirementBadges({bidNo:'Y'}).includes('비상주 ✓'));
assert.ok(app.jobRequirementEvidence({bidNo:'Y'}).roles.factLines.some(v=>v.includes('8.280MM')));
assert.ok(!app.jobRequirementBadges({bidNo:'Y'}).includes('인원 미확인'));
const yonginBadgeHtml=app.jobRequirementBadges({bidNo:'Y'});
assert.ok(yonginBadgeHtml.includes('역할별 인원 1명'),'the thumbnail must show the person count');
assert.ok(yonginBadgeHtml.includes('<strong>응용SW 개발자</strong>'),'the role detail must name the developer');
assert.ok(yonginBadgeHtml.includes('job-req-tip-count">1명</strong>'),'the role detail must show one person');
const onsiteYongin=yonginBadgeHtml.slice(yonginBadgeHtml.indexOf('data-requirement="onsite"'),
 yonginBadgeHtml.indexOf('data-requirement="roles"'));
for(const fragment of ['응용SW 개발자','job-req-onsite-count">1명</strong>',
 '투입기간 11.04개월','투입률 75%','8.28MM','공내역서.xlsx']){
 assert.ok(onsiteYongin.includes(fragment),'onsite tooltip missing '+fragment);
}
assert.ok(!yonginBadgeHtml.includes('공수 11.522MM'),'do not replace headcount with man-month effort');
const onsiteBadge=yonginBadgeHtml.slice(yonginBadgeHtml.indexOf('data-requirement="onsite"'),yonginBadgeHtml.indexOf('data-requirement="roles"'));
const workloadBadge=yonginBadgeHtml.slice(yonginBadgeHtml.indexOf('data-requirement="roles"'),yonginBadgeHtml.indexOf('<span class="job-req-tip" role="tooltip">',yonginBadgeHtml.indexOf('data-requirement="roles"')));
assert.ok(!onsiteBadge.includes('job-req-icon'),'verified onsite source is not a grey failure/info circle');
assert.ok(!workloadBadge.includes('job-req-icon'),'verified workload source is not a grey failure/info circle');
assert.equal(app.jobRequirementEvidence({bidNo:'Y'}).roles.status.key,'role_found');
assert.ok(app.jobRequirementEvidence({bidNo:'N'}).roles.factLines[0].includes('필수 아님'));
const verified=JSON.parse(fs.readFileSync(path.join(__dirname,'../startup-support/staffing-source-verified.json'),'utf8')).byNotice;
const northOfficial=verified['R26BK01783957:000'];
assert.ok(northOfficial&&northOfficial.verification==='official_attachment_sha256');
assert.equal(northOfficial.sha256,'0bac97cb72b9f30cdeb2e00cd6dbab748c2faf00d2d8da5eb78fc9a97e64b645');
assert.equal(northOfficial.staffingFacts.length,1);
assert.equal(northOfficial.staffingFacts[0].count,8);
assert.equal(northOfficial.staffingFacts[0].mandatory,false);
assert.match(northOfficial.staffingFacts[0].sourceText,/상주인력 월평균 8명 이상을 유지 권고/);
for(const [key,expectedCount] of [['R26BK01818412:000',3],['R26BK01810885:000',4]]){
 const original=verified[key];
 assert.ok(original&&original.verification==='official_attachment_sha256'&&original.staffingFacts.length===expectedCount,key);
 assert.ok(original.staffingFacts.every(f=>f.kind==='staffing_requirement'&&f.sourceFile===original.sourceFile&&f.sourceLine>0));
}
const docs=new Map(Object.entries(verified).map(([key,value])=>[key,{staffingFacts:value.staffingFacts}]));
const records=new Map([
 ['R26BK01818412:000',mk([])],
 ['R26BK01810885:000',{seen:true,status:'text_extracted_requires_review',
  complete:false,scanComplete:false,documentCount:5,readableCount:3,effectiveReadableCount:4,
  staffingRoleScanComplete:true,staffingRoles:[],staffingFacts:[]}]
]);
const evidenceUI=moduleUI(x=>({bidNo:x.bidNo,order:'000'}),docs,records,new Map(),new Map(),false,'',
 s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'));
const lx={bidNo:'R26BK01818412'},seoul={bidNo:'R26BK01810885'};
const recoveredNorth=evidenceUI.jobRequirementEvidence({bidNo:'R26BK01783957'});
assert.equal(recoveredNorth.onsite.status.key,'onsite_recommended');
assert.equal(recoveredNorth.onsite.status.label,'상주 권고');
assert.ok(evidenceUI.jobRequirementBadges({bidNo:'R26BK01783957'}).includes('월평균'));
assert.ok(evidenceUI.jobRequirementBadges({bidNo:'R26BK01783957'}).includes('붙임1_제안요청서'));
assert.equal(evidenceUI.jobRequirementEvidence(lx).roles.status.key,'role_requirements');
const lxHtml=evidenceUI.jobRequirementBadges(lx);
for(const label of ['인력 조건 확인','근무조건 협의','FP 산정 전문가 포함','참여인력 재직·경력 증빙'])assert.ok(lxHtml.includes(label),label);
assert.ok(!lxHtml.includes('job-req-tip-total">인원 수 미명시'),'never headline non-information');
assert.ok(!lxHtml.includes('role_requirements">?'),'verified conditions are not failure');
const seoulEvidence=evidenceUI.jobRequirementEvidence(seoul);
assert.equal(seoulEvidence.onsite.status.key,'onsite');
assert.equal(seoulEvidence.roles.status.key,'role_requirements');
assert.equal(seoulEvidence.insurance.status.key,'employment_proof');
const seoulHtml=evidenceUI.jobRequirementBadges(seoul);
for(const text of ['재직증빙 확인','상주 필수','PM 10년 경력','건강보험 자격득실'])assert.ok(seoulHtml.includes(text),text);
const seoulOnsiteTip=seoulHtml.slice(seoulHtml.indexOf('data-requirement="onsite"'),
 seoulHtml.indexOf('data-requirement="roles"'));
for(const fragment of ['상주인력 근무·휴가 조건','2. 제안요청서.hwpx','상주인력의 휴가']){
 assert.ok(seoulOnsiteTip.includes(fragment),'onsite requirement must show evidence: '+fragment);
}
assert.ok(!seoulHtml.includes('상주조건 확인'),'onsite confirmed labels must be unified');
assert.ok(!seoulHtml.includes('확인실패'),'positive evidence must not become three failed statuses');
// Generic legacy notices may have source excerpts, not yet structured facts.
// Their card must show the original staffing requirement, not "미명시 ?".
const legacy=new Map([
 ['G:000',{...mk([]),status:'text_extracted_requires_review',
   staffingRoleScanComplete:true,documentCount:5,readableCount:3,
   effectiveReadableCount:4,complete:false,scanComplete:false,
   excerpts:[{text:'제안사는 투입될 인원 현황을 제시하여야 하며 업무 분장 내역을 제시해야 함',
              type:'staff_proof',sourceFile:'제안요청서.hwpx'}]}],
 ['H:000',{...mk([]),status:'text_extracted_requires_review',
   staffingRoleScanComplete:true,documentCount:5,readableCount:3,
   effectiveReadableCount:4,complete:false,scanComplete:false}]
]);
const legacyApp=moduleUI(x=>({bidNo:x.bidNo,order:'000'}),new Map(),legacy,
  new Map(),new Map(),false,'',
  s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'));
const legacyReq=legacyApp.jobRequirementEvidence({bidNo:'G'});
assert.equal(legacyReq.roles.status.key,'role_requirements');
assert.ok(legacyReq.roles.requirements.some(x=>x.label==='인력 현황 제출'));
const legacyHtml=legacyApp.jobRequirementBadges({bidNo:'G'});
assert.ok(legacyHtml.includes('인력 현황 제출'));
assert.ok(legacyHtml.includes('투입될 인원 현황'));
assert.ok(!legacyHtml.includes('role_count_unspecified'));
assert.equal(legacyApp.jobRequirementEvidence({bidNo:'H'}).onsite.status.key,'offsite',
 'general contract archive failure must not invalidate completed project staffing scans');
console.log('WORKLINKS_STAFFING_FACTS_UI_PASS',expected.length,'source-backed notices',2,
 'legacy source fallback 1, scoped archive failure 1');
