#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'..','startup-support','index.html'),'utf8');
const start=html.indexOf('function jobRequirementEvidence(x){');
const end=html.indexOf('function jobCollectionMarkup(x){',start);
assert(start>=0&&end>start,'render script missing');
const source=html.slice(start,end);
const key='R26BK01826049:000';
const bid={noticeNumber:'R26BK01826049',noticeOrder:'000'};
const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const sourceState={
 sourceAvailable:true,seen:true,status:'text_extracted_requires_review',
 scanComplete:true,complete:true,staffingRoleScanComplete:true,
 documentCount:1,readableCount:1,effectiveReadableCount:1,
 staffingRoles:[],staffingFacts:[],excerpts:[],
 requirementScanVersion:2,requirementScanComplete:true,
 requirementVerdicts:{
  performance:{scanVersion:2,status:'required',sourceComplete:true,
   reason:'explicit_required',hasEvaluation:false,
   evidence:[{kind:'required',sourceFile:'공고문.pdf',sourceLine:8,
     sourceText:'입찰 참가 자격: 유사 용역 수행실적 3억원 이상 보유하여야 한다.',
     sourceUrl:'https://www.g2b.go.kr/example.pdf'}]},
  directProduction:{scanVersion:2,status:'not_required',sourceComplete:true,
   reason:'full_official_attachments_no_mandatory_clause',hasEvaluation:false,
   evidence:[]}
 }};
function render(saved){
 const factory=new Function('jobBidIdentity','rfpSnapshotByNotice','jobSearchRfpState',
 'jobListRfpState','changcomPrecheckByNotice','rfpScanProvenanceByNotice',
 'rfpSnapshotLoading','rfpSnapshotCheckedAt','rfpCardEvidenceFetchErrors',
 'htmlEscape','worklinksPartnerAccess','partners',
 source+'return {jobDetailRequirementGrid};');
 return factory(x=>({bidNo:x.noticeNumber,order:x.noticeOrder||'000'}),
  new Map(),new Map([[key,saved]]),new Map(),
  new Map(),new Map(),false,'',new Set(),esc,()=>false,[]);
}
const output=render(sourceState).jobDetailRequirementGrid(bid);
assert(output.includes('필수 수행실적 요구'),output.slice(0,500));
assert(output.includes('직접생산 요구 없음'),output.slice(0,800));
assert(output.includes('유사 용역 수행실적 3억원 이상'),output);
assert(output.includes('출처: 공고문.pdf'),output);
assert(!output.includes('확인실패'),output);
const broken={...sourceState,requirementScanComplete:false,
 requirementVerdicts:{...sourceState.requirementVerdicts,directProduction:{
  ...sourceState.requirementVerdicts.directProduction,sourceComplete:false}}};
const partial=render(broken).jobDetailRequirementGrid(bid);
assert(!partial.includes('입찰 필수 직접생산 요구 없음'),
 'partial corpus cannot make a negative decision');
assert(!partial.includes('요구 없음 확인'),partial);
const reviewed={...sourceState,requirementVerdicts:{
 ...sourceState.requirementVerdicts,directProduction:{
  scanVersion:2,status:'review',sourceComplete:true,evidence:[],
  reason:'ambiguous_qualification_wording'}}};
assert(render(reviewed).jobDetailRequirementGrid(bid).includes('직접생산 판정 보류'));
console.log('WORKLINKS_RFP_SOURCE_VERIFIED_PERFORMANCE_DIRECT_VERDICTS_UI_PASS');
