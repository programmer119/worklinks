const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html=fs.readFileSync('startup-support/index.html','utf8');
const begin=html.indexOf('function jobRequirementEvidence(x){');
const end=html.indexOf('function jobDetailRequirementGrid(x){',begin);
assert(begin>0&&end>begin,'WorkLinks requirement evaluator and badge renderer exist');
const script=html.slice(begin,end);
const notice='R26BK01234567:000';

function getEvidence({complete=true,kind='role_unspecified',mandatoryCount=null,requirements=[],onsite=false}={}){
  const fact=kind?{kind,role:'개발',sourceFile:'제안요청서.pdf',sourceText:'투입인력의 업무분장 및 인력구성 계획을 제출한다. 인원 수 지정 없음.'}:null;
  const file={
    readable:true,sourceTextScanComplete:complete,qualificationScanTruncated:false,
    clauseCandidatesTruncated:false,staffingRoleScanVersion:complete?4:0,
    staffingFactScanVersion:complete?2:0,staffingRoleScanTruncated:false,
    staffingFacts:fact?[fact]:[],
    staffingRoles:Number.isInteger(mandatoryCount)?[{role:'개발자',count:mandatoryCount,sourceFile:'제안요청서.pdf',
      sourceText:'개발자 '+mandatoryCount+'명 필수 투입'}]:[],
    clauseCandidates:onsite?[{sourceText:'상주 인력 배치 의무가 있다.',explicitMust:true,sourceFile:'제안요청서.pdf'}]:[]
  };
  const full={status:'text_extracted_requires_review',manifestComplete:true,
    files:[file],staffingFacts:requirements};
  const ctx={
    jobBidIdentity:()=>({bidNo:'R26BK01234567',order:'000'}),
    rfpSnapshotByNotice:new Map([[notice,full]]),
    jobSearchRfpState:new Map(),jobListRfpState:new Map(),
    rfpScanProvenanceByNotice:new Map(),
    changcomPrecheckByNotice:new Map(),rfpSnapshotLoading:false,
    rfpSnapshotCheckedAt:'2026-11-14',htmlEscape:s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  };
  vm.createContext(ctx);
  vm.runInContext(script,ctx);
  return {
    evidence:ctx.jobRequirementEvidence({title:'2027년 지휘훈련시스템 유지보수 용역'}),
    markup:ctx.jobRequirementBadges({title:'2027년 지휘훈련시스템 유지보수 용역'})
  };
}
const flexible=getEvidence({kind:'role_unspecified'});
assert.equal(flexible.evidence.roles.status.key,'role_count_unspecified');
assert.equal(flexible.evidence.roles.status.label,'인원 자율');
assert(flexible.markup.includes('인원 자율'));
assert(flexible.markup.includes('role_count_unspecified'));
assert(flexible.markup.includes('✓'));
assert(!flexible.markup.includes('인원 수 미명시'));
console.log('NO_MANDATORY_HEADCOUNT = PASS');

const noRequirements=getEvidence({kind:null});
assert.equal(noRequirements.evidence.roles.status.key,'role_unspecified');
assert.equal(noRequirements.evidence.roles.status.label,'인원 자율');
console.log('NO_STAFFING_REQUIREMENTS = PASS');

const incomplete=getEvidence({complete:false,kind:'role_unspecified'});
assert(!['role_count_unspecified','role_unspecified'].includes(incomplete.evidence.roles.status.key));
console.log('INCOMPLETE_EXTRACTION_NOT_MARKED_FLEXIBLE = PASS');

const fixed=getEvidence({kind:null,mandatoryCount:2});
assert.equal(fixed.evidence.roles.status.key,'role_found');
assert(fixed.markup.includes('역할별 인원'));
console.log('EXPLICIT_REQUIRED_ROLE_COUNT_PRESERVED = PASS');

const qualification=getEvidence({kind:null,requirements:[{
  kind:'staffing_requirement',requirementType:'certificate',
  label:'개발자 자격증 필수',sourceText:'투입 개발자는 관련 자격증을 보유해야 한다.',
  sourceFile:'제안요청서.pdf'
}]});
assert.equal(qualification.evidence.roles.status.key,'role_requirements');
console.log('SEPARATE_PERSONNEL_CONDITION_PRESERVED = PASS');
