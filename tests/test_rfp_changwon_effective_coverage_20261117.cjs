#!/usr/bin/env node
'use strict';
// Production regression: verified PDF sibling makes 3 physically opened files
// equal 4 effectively scanned source documents. Unknown bid conditions are
// REVIEW, never false parser failures or unsupported "not required" claims.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'..','startup-support','index.html'),'utf8');
const start=html.indexOf('function jobRequirementEvidence(x){');
const end=html.indexOf('function jobCollectionMarkup(x){',start);
assert(start>0&&end>start,'source render functions missing');
const snippet=html.slice(start,end);
const key='R26BK01826049:000';
const job={noticeNumber:'R26BK01826049',noticeOrder:'000'};
const source={
  sourceAvailable:true,seen:true,complete:true,scanComplete:true,
  staffingRoleScanComplete:true,status:'text_extracted_requires_review',
  documentCount:4,readableCount:3,pdfCoveredCount:1,effectiveReadableCount:4,
  checkedAt:'2026-11-17T06:21:25Z',classificationVersion:23,hwpxReaderVersion:3,
  staffingRoleVersions:[4],staffingFactVersions:[2],
  parserCurrent:true,versionSource:'coverage_index',
  staffingRoles:[],staffingFacts:[],excerpts:[],
  sourceAccess:{status:'none',protectedFileCount:0,otherUnreadableCount:0}
};
const escape=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
function render(saved=source,full=null){
  const factory=new Function(
    'jobBidIdentity','rfpSnapshotByNotice','jobSearchRfpState','jobListRfpState',
    'changcomPrecheckByNotice','rfpScanProvenanceByNotice',
    'rfpSnapshotLoading','rfpSnapshotCheckedAt','rfpCardEvidenceFetchErrors',
    'htmlEscape','worklinksPartnerAccess','partners',
    snippet+'return {jobRequirementEvidence,jobDetailRequirementGrid};');
  return factory(
    x=>({bidNo:x.noticeNumber,order:x.noticeOrder||'000'}),
    new Map(full?[[key,full]]:[]),new Map([[key,saved]]),new Map(),
    new Map(),new Map(),false,'',new Set(),escape,()=>false,[]);
}
const ui=render();
const evidence=ui.jobRequirementEvidence(job);
assert.equal(evidence.meta.scanFailed,false,'verified PDF substitution must not set scan failure');
assert.equal(evidence.meta.fullyReviewed,false,'automatic OCR is not a legal conditions audit');
const markup=ui.jobDetailRequirementGrid(job);
assert(markup.includes('판독 4/4건 (공식 PDF 대체 1건)'),markup.slice(0,850));
assert.equal((markup.match(/원문 검토 필요/g)||[]).length,2,markup);
assert(!markup.includes('확인실패'),markup);
assert(!markup.includes('요건 없음 확인'),markup);
assert(markup.includes('원문 판독 완료 · 필수 실적 문구 미검출'),markup);
assert(markup.includes('원문 판독 완료 · 직접생산 요구 문구 미검출'),markup);
// A genuine fourth unreadable original must still be reported as incomplete.
const genuine=render({...source,scanComplete:false,complete:false,
  pdfCoveredCount:0,effectiveReadableCount:3});
const actual=genuine.jobDetailRequirementGrid(job);
assert(actual.includes('판독 3/4건'),actual);
assert(actual.includes('확인실패'),actual);
// The full reader must verify the same-name PDF's SHA before covering HWPX.
const hwpName='공고서_국가(창원대).hwpx',pdfName='공고서_국가(창원대).pdf';
const pdf={name:pdfName,readable:true,sourceTextScanComplete:true,
  sourceSha256:'a'.repeat(64)};
const hwp={name:hwpName,readable:false,sourceTextScanComplete:false,
  skippedDuplicateFormat:true,alternatePdfEvidence:pdfName,
  alternatePdfSourceSha256:'a'.repeat(64)};
const original={...source,status:'text_extracted_requires_review'};
const full={...original,manifestComplete:true,reviewComplete:false,
  requiredConditionsComplete:null,files:[hwp,pdf,
    {name:'제안요청서.hwp',readable:true,sourceTextScanComplete:true,
     sourceSha256:'b'.repeat(64)},
    {name:'',readable:true,sourceTextScanComplete:true,sourceSha256:'b'.repeat(64)}]};
const v=render(source,full);
assert.equal(v.jobRequirementEvidence(job).meta.scanFailed,false);
assert(v.jobDetailRequirementGrid(job).includes('판독 4/4건 (공식 PDF 대체 1건)'));
const invalid=structuredClone(full);
invalid.files[0].alternatePdfSourceSha256='f'.repeat(64);
assert.equal(render({...source,scanComplete:false,complete:false,
  pdfCoveredCount:0,effectiveReadableCount:3},invalid).jobRequirementEvidence(job).meta.scanFailed,true,
  'never trust an unverified or mismatched PDF substitute');
console.log('WORKLINKS_CHANGWON_3_OF_4_PHYSICAL_4_OF_4_VERIFIED_PDF_AND_REVIEW_NOT_FAILED=PASS');
