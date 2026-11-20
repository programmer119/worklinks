'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'..');
const src=fs.readFileSync(path.join(root,'startup-support/changcom-prebid.js'),'utf8');
const html=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
const elements=Object.fromEntries(['jobDetailTitle','jobDetailSub','jobDetailBody'].map(k=>[k,{textContent:'',innerHTML:''}]));
const ctx={
 window:{location:{search:''},worklinksKeeps:{keepButton:id=>'<button data-keep-toggle="'+id+'">킵</button>'}},
 document:{getElementById:id=>elements[id]||null},
 htmlEscape:x=>String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;'),
 jobSearchNormalized:x=>String(x).toLowerCase(),
 g2bCardAwardMetadata:x=>({awardMethodCode:x.awardMethodCode}),
 jobOriginUrl:x=>x.url||'',jobAmountLabel:x=>String(x),
 jobSearchText:'',jobRenderLimit:40,
 worklinksPartnerAccess:()=>true,renderJobs:()=>{},
 Date,Map,Set,String,Number,Boolean,encodeURIComponent,URLSearchParams
};
vm.createContext(ctx);
vm.runInContext(src,ctx);
const spec={id:'R26BD00301798',stage:'prespec',kind:'servc',
 title:'학생관리 시스템 구축 용역',org:'연세대학교 미래캠퍼스',
 posted:'2026-11-17 16:37:24',budget:'39930000',
 opinionDeadline:'202611191800',subject:'학생관리',url:'',files:[]};
const key='g2b-prebid-prespec-servc-R26BD00301798';
vm.runInContext('prebidCache.prespec.items=[__testRow]',Object.assign(ctx,{__testRow:spec}));
const markup=vm.runInContext('prebidNoticeCardMarkup(__testRow)',ctx);
assert.ok(markup.includes('data-job-card="'+key+'"'),'reuse normal card action');
assert.ok(markup.includes('data-keep-toggle="'+key+'"'),'preserve keep');
assert.ok(!markup.includes('공유 링크'),'no duplicate share link on thumbnail');
assert.ok(markup.includes('data-job-detail="'+key+'"'),'title uses same detail handler');
assert.equal(vm.runInContext("renderPrebidSourceDetail({id:'"+key+"'})",ctx),true);
assert.ok(elements.jobDetailSub.textContent.includes('사전규격'));
assert.ok(elements.jobDetailBody.innerHTML.includes('의견등록'));
assert.ok(elements.jobDetailBody.innerHTML.includes('학생관리')); // subject not a false bid-specific eligibility
assert.ok(elements.jobDetailBody.innerHTML.includes('상세 직링크 미확인'));
assert.ok(elements.jobDetailBody.innerHTML.includes('나라장터에서 조회'),
 'missing prespec direct link must be labelled lookup, not original detail');
assert.ok(!elements.jobDetailBody.innerHTML.includes('입찰참가자격 확인'));
const keepMarkup=vm.runInContext("prebidKeptCardMarkup({id:'"+key+"',title:'학생관리 시스템 구축 용역',org:'연세대학교 미래캠퍼스',amount:'3993만원',url:''})",ctx);
assert.ok(keepMarkup.includes('data-job-card="'+key+'"'),'kept cards click using existing original handler');
vm.runInContext('prebidCache.prespec.items=[]',ctx);
const fallback=vm.runInContext("prebidKeepJobFromId('"+key+"')",ctx);
assert.equal(fallback.id,key);
assert.equal(fallback.title,'학생관리 시스템 구축 용역');
assert.equal(vm.runInContext("renderPrebidSourceDetail(prebidKeepJobFromId('"+key+"'))",ctx),true,
 'offline kept cards stay on early-stage renderer, not ordinary bid renderer');
assert.ok(elements.jobDetailBody.innerHTML.includes('상세 직링크 미확인'));
const plan={id:'R26DD20928584',stage:'plan',kind:'servc',title:'정보시스템 구축 발주',
 org:'발주기관',posted:'2026-11-18',plannedMonth:'2026-12',budget:'120000000',
 url:'https://www.g2b.go.kr/link/PRPA015_01/single/?oderPlanNo=R26DD20928584',files:[]};
ctx.__plan=plan;
vm.runInContext('prebidCache.plan.items=[__plan]',ctx);
const planKey='g2b-prebid-plan-servc-R26DD20928584';
assert.equal(vm.runInContext("renderPrebidSourceDetail({id:'"+planKey+"'})",ctx),true);
assert.ok(elements.jobDetailBody.innerHTML.includes('발주예정'));
assert.ok(elements.jobDetailBody.innerHTML.includes('href="https://www.g2b.go.kr/link/PRPA015_01/single/'));
assert.equal(vm.runInContext("renderPrebidSourceDetail({id:'g2b-servc-R26BK01830000-000'})",ctx),false,
 'ordinary tenders must never enter stage-specific renderer');
assert.ok(vm.runInContext("combinedBidCardMarkup({id:'g2b-servc-R26BK01830000-000',title:'일반 입찰',kind:'servc',amount:'100000000'})",ctx).includes('data-job-card="g2b-servc-R26BK01830000-000"'));
assert.ok(html.includes("if(typeof renderPrebidSourceDetail==='function'&&renderPrebidSourceDetail(x))return;"));
assert.ok(html.includes("if(/^g2b-prebid-/.test(String(id)))return;"),'no bid evidence API calls for early stage');
assert.ok(html.includes("const card=e.target.closest('[data-job-card]')"),'ordinary click handler unchanged');
console.log('WORKLINK_STAGE_MODAL_SAFETY=PASS');
