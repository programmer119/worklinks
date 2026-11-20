// Zero-network contract for KakaoTalk OG cards and exact WORKLINK notice routing.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const index=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
const script=fs.readFileSync(path.join(root,'startup-support/changcom-prebid.js'),'utf8');
const ids=[
 ['R26BD00301798','prespec','연세대학교'],
 ['R26BD00303409','prespec','국립창원대학교'],
 ['R26BD00302593','prespec','인천테크노파크'],
 ['R26BD00301029','prespec','공간정보품질관리원'],
 ['R26BK01843011','bid','충북보건과학대학교']
];
const image=fs.readFileSync(path.join(root,'startup-support/share/og-worklinks.png'));
assert.equal(image.subarray(0,8).toString('hex'),'89504e470d0a1a0a');
assert.equal(image.readUInt32BE(16),1200);
assert.equal(image.readUInt32BE(20),630);
assert.ok(image.length>3000,'not a placeholder thumbnail');
for(const [id,stage,institution] of ids){
 const html=fs.readFileSync(path.join(root,'startup-support/share',id,'index.html'),'utf8');
 const url='https://worklinks.suaveforge.com/startup-support/share/'+id+'/';
 for(const tag of ['og:title','og:description','og:image','og:url','og:image:width','og:image:height'])
  assert.ok(html.includes('property="'+tag+'"'),'missing '+tag+' '+id);
 assert.ok(html.includes('content="'+url+'"'),'wrong OG canonical '+id);
 assert.ok(html.includes('share/og-worklinks.png'),'missing native thumbnail '+id);
 assert.ok(html.includes(institution),'institution mismatch '+id);
 assert.ok(html.includes('stage='+stage+'&amp;q=')||html.includes('stage='+stage+'&q='),
  'not routed to original stage '+id);
 assert.ok(html.includes('open='+id),'not requesting direct detail '+id);
 assert.ok(!html.includes('meta http-equiv="refresh"'),'crawler must not lose per-notice tags');
}
assert.ok(!index.includes('<meta property="og:title"'), 'shared previews must stay per-notice, not common shell');
assert.ok(index.includes("function scheduleWorklinksShareOpen()"));
assert.ok(index.includes("if(typeof renderPrebidSourceDetail==='function'&&renderPrebidSourceDetail(x))return;"));
assert.ok(index.includes("if(/^g2b-prebid-/.test(String(id)))return;"));
assert.ok(script.includes("data-job-card="),'prebid card must open detail, not plain text');
assert.ok(script.includes("function renderPrebidSourceDetail(item)"));
assert.ok(script.includes("data-external-source="));
const ctx={
 document:{getElementById:()=>null},window:{location:{search:''},worklinksKeeps:{keepButton:()=>''}},
 g2bCardAwardMetadata:()=>({}),worklinksPartnerAccess:()=>true,
 renderJobs:()=>{},g2bFetch:()=>{},
 htmlEscape:x=>String(x).replace(/"/g,'&quot;'),
 jobSearchNormalized:x=>String(x||'').toLowerCase(),jobSearchText:'',
 jobRenderLimit:40,jobSort:'recent',Map,Set,String,Number,Boolean,Date,
 encodeURIComponent,URLSearchParams,Array,Object
};
vm.createContext(ctx);
vm.runInContext(script,ctx);
const prespec={
 stage:'prespec',kind:'servc',id:'R26BD00301798',
 title:'연세대학교 학생관리 시스템 구축',org:'연세대학교 미래캠퍼스',
 posted:'2026-11-17',budget:'39930000',url:'',files:[]
};
ctx.document.getElementById=id=>({
 jobDetailTitle:{},jobDetailSub:{},jobDetailBody:{}
}[id]||null);
const nodes={jobDetailTitle:{textContent:''},jobDetailSub:{textContent:''},jobDetailBody:{innerHTML:''}};
ctx.document.getElementById=id=>nodes[id]||null;
vm.runInContext("prebidCache.prespec.items=[{stage:'prespec',kind:'servc',id:'R26BD00301798',title:'연세대학교 학생관리 시스템 구축',org:'연세대학교 미래캠퍼스',posted:'2026-11-17',budget:'39930000',url:'',files:[]}]",ctx);
const card=vm.runInContext("prebidNoticeCardMarkup(prebidCache.prespec.items[0])",ctx);
assert.ok(card.includes('data-job-card="g2b-prebid-prespec-servc-R26BD00301798"'));
assert.ok(card.includes('./share/R26BD00301798/'));
assert.ok(card.includes('data-job-detail='));
assert.equal(vm.runInContext("renderPrebidSourceDetail({id:'g2b-prebid-prespec-servc-R26BD00301798'})",ctx),true);
assert.ok(nodes.jobDetailBody.innerHTML.includes('3,993만원'));
assert.ok(nodes.jobDetailBody.innerHTML.includes('입찰조건 미확정'));
assert.ok(nodes.jobDetailBody.innerHTML.includes('나라장터에서 R26BD00301798 검색'));
console.log('WORKLINK_KAKAO_SOCIAL_SHARE_AND_DETAIL=PASS');
