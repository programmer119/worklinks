'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'startup-support/changcom-prebid.js'),'utf8');
const html=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
const ctx={
 URL,URLSearchParams,Date,Map,Set,String,Number,Boolean,encodeURIComponent,Array,Object,
 window:{location:{search:''},worklinksKeeps:{keepButton:()=>''}},
 document:{getElementById:()=>null,hidden:false},
 htmlEscape:s=>String(s||''),jobSearchText:'',jobRenderLimit:40,
 worklinksPartnerAccess:()=>true,worklinksIsChangcomView:()=>true,
 renderJobs:()=>{ctx.renderCount++},renderCount:0,
 setTimeout:fn=>{Promise.resolve().then(fn);return 1;}
};
vm.createContext(ctx);
vm.runInContext(source,ctx);
const make=(stage,count)=>Array.from({length:count},(_,i)=>({
 id:(stage==='prespec'?'R26BD':'R26DD')+String(i).padStart(8,'0'),
 kind:'servc',stage,title:'공공 시스템 구축 '+i,org:'테스트 발주기관',
 posted:'2026-11-23 12:00:00',budget:1000000
}));
const prespec=make('prespec',1300);
let active=0,peak=0,attempts={};
ctx.g2bFetch=async u=>{
 const params=new URL('https://test.local'+u).searchParams;
 const offset=Number(params.get('offset'));
 attempts[offset]=(attempts[offset]||0)+1;
 active++;peak=Math.max(peak,active);
 await Promise.resolve();
 active--;
 if(offset===500&&attempts[offset]===1)throw new TypeError('Failed to fetch');
 return {ok:true,ready:true,stage:'prespec',total:prespec.length,items:prespec.slice(offset,offset+500)};
};
(async()=>{
 vm.runInContext("partnerNoticeStage='prespec';",ctx);
 await vm.runInContext("loadPrebidJobs('prespec')",ctx);
 let state=vm.runInContext('prebidCache.prespec',ctx);
 assert.equal(state.state,'ready');
 assert.equal(state.items.length,1300);
 assert.equal(state.total,1300);
 assert.equal(state.items[1299].id,prespec[1299].id);
 assert.equal(attempts[500],2,'transient 500-page should be retried');
 assert.ok(peak>=2,'stage pages must load concurrently');

 // A later refresh must not erase the last fully verified list.
 ctx.g2bFetch=async()=>{throw Error('HTTP 403')};
 await vm.runInContext("loadPrebidJobs('prespec',true)",ctx);
 state=vm.runInContext('prebidCache.prespec',ctx);
 assert.equal(state.state,'ready');
 assert.equal(state.items.length,1300);
 assert.ok(state.staleError.includes('HTTP 403'));

 // An initial failure cannot manufacture a completed zero-result stage.
 await vm.runInContext("loadPrebidJobs('plan',true)",ctx);
 const plan=vm.runInContext('prebidCache.plan',ctx);
 assert.equal(plan.state,'error');
 assert.equal(plan.items.length,0);

 // A custom obsolete API origin must fall back on the verified prebid API.
 const start=html.indexOf('async function g2bFetch(path){');
 const stop=html.indexOf('async function g2bCheckStatus(){',start);
 assert.ok(start>=0&&stop>start,'G2B reader must be found');
 const requests=[],defaults='https://api-suaveforge.suaveforge.com:18458/api/g2b';
 const net={
   G2B_PROXY_URL:'https://obsolete.suaveforge.com/api/g2b',
   G2B_DEFAULT_URL:defaults,AbortController,
   setTimeout:()=>1,clearTimeout:()=>{},Error,URL,Date,
   localStorage:{setItem:()=>{}},
   fetch:async url=>{
     requests.push(url);
     if(url.includes('obsolete'))throw new TypeError('Failed to fetch');
     return {ok:true,status:200,json:async()=>({ok:true,ready:true,items:[]})};
   }
 };
 vm.createContext(net);
 vm.runInContext(html.slice(start,stop),net);
 const fetched=await vm.runInContext("g2bFetch('/prebid?stage=plan&limit=500&offset=0')",net);
 assert.equal(fetched.ok,true);
 assert.equal(requests.length,2);
 assert.equal(net.G2B_PROXY_URL,defaults);
 assert.ok(requests[1].startsWith(defaults+'/prebid?'));
 console.log('WORKLINKS_PREBID_RECOVERY_COMPLETE_PAGINATION_AND_FALLBACK_PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
