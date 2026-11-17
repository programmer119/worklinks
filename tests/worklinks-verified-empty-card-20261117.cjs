const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const start=html.indexOf('function jobSubmissionEvidence(x){');
const end=html.indexOf('function renderJobDetail(x){',start);
assert(start>0&&end>start);
const fake={
 officialAttachmentState:'verified_empty',status:'verified_no_public_attachments',
 sourceAvailable:true,seen:false,scanExcluded:true,submissionItems:[],scanComplete:false
};
const make=new Function('jobBidIdentity','rfpBestCardScan','rfpSnapshotForJob','htmlEscape',
 html.slice(start,end)+'return {jobSubmissionCardMarkup,jobSubmissionDetailMarkup};');
const app=make(()=>({bidNo:'R26BK01830918',order:'000'}),()=>fake,()=>null,s=>String(s)
 .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'));
const card=app.jobSubmissionCardMarkup({id:'LX',title:'LX정보시스템'});
assert(card.includes('RFP 첨부없음'),card);
assert(!card.includes('제출물 확인 필요'),card);
const detail=app.jobSubmissionDetailMarkup({id:'LX'});
assert(detail.includes('첨부문서 판독에서 제외'));
assert(detail.includes('공고 원문을 확인'));
const evidence=html.slice(html.indexOf('function jobRequirementEvidence(x){'),
 html.indexOf('function jobRequirementBadges(x){'));
assert(evidence.includes("const noPublicRfp=saved?.officialAttachmentState==='verified_empty'"));
assert(evidence.includes("if(noPublicRfp)return {key:'no_source'"));
assert(evidence.includes("noPublicRfp?{key:'no_source'"));
console.log('VERIFIED_EMPTY_CARD_UI_PASS');
