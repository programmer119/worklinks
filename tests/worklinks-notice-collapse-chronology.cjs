const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const from=html.indexOf('function noticeGroupKey(x){');
const to=html.indexOf('function licenseLogic(line){',from);
assert.ok(from>0&&to>from);
const moduleUI=new Function('jobBidIdentity','jobTimeInfo','jobOriginUrl',
  html.slice(from,to)+'return {collapseSimilarNotices};');
const id=x=>x.noticeNumber?{bidNo:x.noticeNumber,order:x.noticeOrder}:null;
const time=x=>({start:x.posted?Date.parse(x.posted.replace(' ','T')+'+09:00'):null});
const fn=moduleUI(id,time,x=>'https://www.g2b.go.kr/'+x.noticeNumber);
const base={kind:'servc',org:'서울특별시',title:'2027년 서울시 에너지정보 통합시스템 운영 및 유지관리 용역',amount:'441674000'};
const original={...base,noticeNumber:'R26BK01810095',noticeOrder:'000',posted:'2026-11-04 18:00:41'};
const corrected={...base,noticeNumber:'R26BK01810095',noticeOrder:'001',posted:'2026-11-04 18:11:11'};
const reissued={...base,noticeNumber:'R26BK01810885',noticeOrder:'000',posted:'2026-11-04 18:15:42'};
for(const cases of [[original,corrected,reissued],[reissued,original,corrected],[corrected,reissued,original]]){
 const result=fn.collapseSimilarNotices(cases);
 assert.equal(result.length,1,'same agency title budget near timestamp should collapse');
 assert.equal(result[0].noticeNumber,'R26BK01810885','newest cross-notice official reissue must win');
 assert.equal(result[0].noticeOrder,'000','bid order from another bid number must not outrank reissue date');
 assert.equal(result[0].variants.length,3,'do not lose notice history');
}
const prior=fn.collapseSimilarNotices([corrected,original]);
assert.equal(prior[0].noticeOrder,'001','correction within same bid number remains latest');
const distinct=fn.collapseSimilarNotices([original,{...original,noticeNumber:'R26BK09999999',posted:'2027-03-01 10:00:00'}]);
assert.equal(distinct.length,2,'distant procurement must never merge');
console.log('WORKLINKS_NOTICE_CHRONOLOGY_PASS');
