'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../startup-support/changcom-prebid.js'),'utf8');
const ctx={
 URL,URLSearchParams,Date,Map,Set,String,Number,Boolean,encodeURIComponent,
 window:{location:{search:''},addEventListener(){},setInterval(){},worklinksKeeps:{keepButton:()=>''}},
 document:{getElementById:()=>null},
 htmlEscape:s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'),
 jobSearchText:'',jobRenderLimit:40,renderJobs(){},
};
vm.createContext(ctx);
vm.runInContext(src+'\nthis.__source={prebidOfficialFileEntries,prebidSourceMarkup,prebidOfficialDetailUrl,prebidNoticeCardMarkup,renderPrebidSourceDetail,prebidCache};',ctx);
const t=ctx.__source;
const id='R26BD00302593';
const files=[1,2,3].map(seq=>'https://www.g2b.go.kr/pn/pnz/pnza/UntyAtchFile/downloadFile.do?bfSpecRegNo='+id+'&fileType=BFDTL&fileSeq='+seq);
const spec={id,stage:'prespec',kind:'servc',title:'사업 관리 시스템',org:'인천테크노파크',files,url:''};
const names=['붙임 제안요청서.hwpx','붙임 제출서식.hwpx','붙임 긴급입찰사유서.hwpx'];
assert.deepEqual(t.prebidOfficialFileEntries(spec).map(v=>v.name),names);
const thumb=t.prebidNoticeCardMarkup(spec);
for(const name of names)assert.ok(thumb.includes(name),name);
assert.ok(!thumb.includes('규격서 1')&&!thumb.includes('규격서 2'),'no invented filenames');
assert.ok(thumb.includes('원본문서 보기'));
assert.ok(!thumb.includes('나라장터 원문 보기'),'prespec file is not a verified detail page');
const updated={...spec,id:'R26BD00302578',fileNames:['RFP 최종본.pdf','지침.docx']};
assert.deepEqual(t.prebidOfficialFileEntries(updated).map(v=>v.name),['RFP 최종본.pdf','지침.docx','']);
const other=t.prebidNoticeCardMarkup(updated);
assert.ok(other.includes('RFP 최종본.pdf'));
assert.ok(!other.includes('붙임 제안요청서.hwpx'),'verified sample names must not leak to other IDs');
const plan={id:'R26DD20928584',stage:'plan',kind:'servc',title:'정보시스템 구축 발주',files:[],url:''};
const url=t.prebidOfficialDetailUrl(plan);
assert.equal(url,'https://www.g2b.go.kr/link/PRPA015_01/single/?oderPlanNo=R26DD20928584');
assert.ok(t.prebidNoticeCardMarkup(plan).includes('나라장터 원문 보기'));
assert.ok(t.prebidNoticeCardMarkup(plan).includes('PRPA015_01/single/'));
assert.equal(t.prebidOfficialDetailUrl(spec),'','prespec direct route must not be invented');
assert.ok(t.prebidNoticeCardMarkup({...spec,files:[]}).includes('나라장터 공고조회'));
console.log('WORKLINKS_PREBID_VERIFIED_FILENAMES_AND_SOURCE_LINKS_PASS');
