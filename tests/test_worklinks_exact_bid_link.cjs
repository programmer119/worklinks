'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
const prebid=fs.readFileSync(path.join(root,'startup-support/changcom-prebid.js'),'utf8');
// Compile the unchanged scripts in the real page; catch JS syntax mistakes.
for(const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)){
 if(m[1].trim())new vm.Script(m[1],{filename:'startup-support/index.html'});
}
new vm.Script(prebid,{filename:'startup-support/changcom-prebid.js'});
assert.ok(prebid.includes("/^R\\d{2}BK\\d{8}$/i.test(String(jobSearchText||'').trim())"),
 'An exact tender ID must not trigger a 73,941-row broad fetch');
assert.ok(html.includes("const exactBidQuery=partnerAllMode&&/^R\\d{2}BK\\d{8}$/i.test("),
 'An exact notice ID must bypass stale view filters');
assert.ok(html.includes("if(keepMode!=='all'||exactBidQuery)return true;"),
 'Exact lookup must not be excluded by partner filter state');
assert.ok(html.includes("if(partnerMode&&member&&keepMode==='all'&&!exactBidQuery)"),
 'Exact lookup must not be excluded by award or software filter');
assert.ok(html.includes("more.style.display=keepMode!=='all'||exactBidQuery?'none'"),
 'Exact lookup cannot show a misleading DB 0/0 pagination button');
assert.ok(html.includes("jobSearchRemoteError?'공고번호 서버 검색 실패"),
 'Failed search must not be represented as empty results');
assert.ok(html.includes("const safeRead=path.startsWith('/saved?')||path.startsWith('/prebid?')||")&&
 html.includes("path.startsWith('/prebid-file-names?');")&&
 html.includes("if(selected===G2B_DEFAULT_URL||!safeRead)throw err;"),
 'A broken stored API URL must recover only the verified saved/plan/prespec read-only routes');
assert.ok(html.includes("if(typeof worklinksShareExactBidRow!=='undefined'&&worklinksShareExactBidRow?.id===id)"),
 'Details must survive concurrent paginated search clearing its array');
const start=html.indexOf('const initialJobSearch=');
const end=html.indexOf('localStorage.setItem("worklinks_job_filter_v1"',start);
assert.ok(start>0&&end>start,'shared direct-open source block exists');
const block=html.slice(start,end);
async function exercise(searchData,expects){
 const opened=[],requested=[],el={textContent:''};
 const ctx={
  location:{search:'?view=changcom&open=R26BK01843011&q=R26BK01843011&stage=bid'},
  URLSearchParams,jobSearchByWorkspace:{changcom:''},jobSearchText:'R26BK01843011',
  jobSearchRemote:[],jobSearchServerTotal:null,partnerAllBids:{items:[],total:0,loaded:0,state:'error'},
  g2bLiveJobs:[],prebidCache:{plan:{state:'idle',items:[]},prespec:{state:'idle',items:[]}},
  jobSearchNormalized:v=>String(v||'').toLowerCase(),
  worklinksPartnerAccess:()=>true,worklinksIsChangcomView:()=>true,
  setTimeout:fn=>{queueMicrotask(fn);return 1;},
  document:{getElementById:()=>el},scheduleJobsRender:()=>{},
  openJobDetail:id=>opened.push(id),g2bCardFromServer:x=>({id:'g2b-'+x.kind+'-'+x.bidNo+'-'+x.order,noticeNumber:x.bidNo,title:x.title}),
  g2bFetch:async path=>{requested.push(path);if(searchData instanceof Error)throw searchData;return searchData;},
  encodeURIComponent,Promise,String,Number,Array,Map
 };
 vm.createContext(ctx);
 vm.runInContext(block,ctx);
 vm.runInContext('scheduleWorklinksShareOpen()',ctx);
 for(let i=0;i<12;i++)await new Promise(r=>setImmediate(r));
 assert.equal(requested.length,1,'Exactly one saved-DB lookup, never a full-corpus crawl');
 assert.equal(requested[0],'/saved?sw=0&limit=10&offset=0&q=R26BK01843011');
 assert.equal(opened.length,expects.opened);
 if(expects.opened){
  assert.equal(opened[0],'g2b-servc-R26BK01843011-000');
  assert.equal(ctx.jobSearchRemote.length,1);
  assert.equal(ctx.jobSearchServerTotal,1);
  assert.equal(vm.runInContext('worklinksSharePendingId',ctx),'');
 }else{
  assert.equal(ctx.jobSearchRemote.length,0);
  assert.ok(el.textContent.includes('조회 실패')||vm.runInContext('worklinksShareExactBidError',ctx));
 }
}
(async()=>{
 const record={bidNo:'R26BK01843011',order:'000',kind:'servc',title:'2026학년도 혁신지원사업 학사행정시스템 고도화 구축'};
 await exercise({ok:true,searchMode:'saved_only',totalCount:1,items:[record]}, {opened:1});
 await exercise(new Error('network disconnected'),{opened:0});
 console.log('WORKLINK_EXACT_BID_LINK=PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
