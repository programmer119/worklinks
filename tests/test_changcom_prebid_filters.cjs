const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../startup-support/changcom-prebid.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const ctx={
  g2bCardAwardMetadata:x=>({awardMethodCode:x.awardMethodCode,sourceVerified:x.awardFieldsVerified===true}),
  worklinksPartnerAccess:()=>true,renderJobs:()=>{},
  document:{},Date,Map,Set,String,Number,Boolean,encodeURIComponent,
  htmlEscape:x=>String(x),jobSearchNormalized:x=>String(x).toLowerCase(),
  jobSearchText:'',jobRenderLimit:40
};
vm.createContext(ctx);
vm.runInContext(src+'\nthis.__filter={swBuildTitle,partnerBidMatchesNewFilters,prebidCache};',ctx);
const {swBuildTitle,partnerBidMatchesNewFilters}=ctx.__filter;
assert.equal(swBuildTitle({kind:'servc',title:'교육정보시스템 구축'}),true);
assert.equal(swBuildTitle({kind:'servc',title:'데이터베이스 고도화'}),true);
assert.equal(swBuildTitle({kind:'cnstwk',title:'정보통신 전기공사'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'CCTV 카메라 단순 구매'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'청사 건축공사'}),false);
assert.equal(swBuildTitle({kind:'servc',title:'AI 서버 공급'}),false);
const bid=code=>({id:'g2b-servc-R26BK-test-000',kind:'servc',title:'정보시스템 구축',
 awardMethodCode:code,awardFieldsVerified:true});
vm.runInContext("partnerSwScope='build';partnerAwardFilter='price';",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030021')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030022')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030029')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),false);
assert.equal(partnerBidMatchesNewFilters(bid('낙030002')),false);
assert.equal(partnerBidMatchesNewFilters({...bid('낙030021'),awardFieldsVerified:false}),false);
vm.runInContext("partnerAwardFilter='qualification';",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030001')),true);
vm.runInContext("partnerAwardFilter='spec-price';",ctx);
assert.equal(partnerBidMatchesNewFilters(bid('낙030018')),true);
assert.equal(partnerBidMatchesNewFilters(bid('낙030002')),true);
assert.ok(html.includes('id="partnerNoticeStage"'));
assert.ok(html.includes('id="partnerAwardFilter"'));
assert.ok(html.includes('id="partnerSwScope"'));
assert.ok(html.includes('changcom-prebid.js'));
assert.ok(html.includes('partnerBidMatchesNewFilters(o.x)'));
console.log('CHANGCOM_PREBID_FILTERS=PASS');
