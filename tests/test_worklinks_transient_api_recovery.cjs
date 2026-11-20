const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const prebid=fs.readFileSync(path.join(__dirname,'../startup-support/changcom-prebid.js'),'utf8');
const keep=fs.readFileSync(path.join(__dirname,'../startup-support/worklinks-keep.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
assert.ok(html.includes('changcom-prebid.js?v=20261121-g2b-source-realname-v1'));
assert.ok(html.includes('worklinks-keep.js?v=20261120-transient-read-recovery-v1'));
assert.ok(keep.includes('keepNetworkRetryPending'));
assert.ok(keep.includes("window.addEventListener('online',recoverKeepNetworkRead)"));
assert.ok(keep.includes("document.documentElement.dataset.worklinksAuthState!=='granted'"));
async function run(){
 const calls=[];
 let failures=0,mode='transient';
 const ctx={
  URLSearchParams,Date,Map,Set,String,Number,Boolean,encodeURIComponent,
  window:{location:{search:''},addEventListener(){},setInterval(){}},
  document:{hidden:false,getElementById(){return null}},
  worklinksPartnerAccess:()=>true,worklinksIsChangcomView:()=>true,
  renderJobs(){},
  g2bFetch:async route=>{
   calls.push(route);
   if(mode==='transient'&&failures++===0)throw new TypeError('Failed to fetch');
   if(mode==='forbidden')throw new Error('HTTP 403');
   const offset=Number(new URL('https://test.invalid'+route).searchParams.get('offset'));
   if(offset===0)return {ok:true,ready:true,total:501,items:Array.from({length:500},(_,i)=>({id:String(i)}))};
   return {ok:true,ready:true,total:501,items:[{id:'last'}]};
  },
  setTimeout:fn=>{fn();return 1},
 };
 vm.createContext(ctx);
 vm.runInContext(prebid+'\nthis.__probe={loadPrebidJobs,prebidCache,prebidReadPageWithRetry,prebidTransientReadFailure};',ctx);
 const p=ctx.__probe;
 assert.equal(p.prebidTransientReadFailure(new TypeError('Failed to fetch')),true);
 assert.equal(p.prebidTransientReadFailure(new Error('HTTP 403')),false);
 await p.loadPrebidJobs('prespec',true);
 assert.equal(p.prebidCache.prespec.state,'ready');
 assert.equal(p.prebidCache.prespec.items.length,501);
 assert.equal(calls.length,3,'one transient retry + two successful pages');
 mode='forbidden';calls.length=0;
 await p.loadPrebidJobs('plan',true);
 assert.equal(p.prebidCache.plan.state,'error');
 assert.equal(calls.length,1,'403 must not be retried');
 assert.equal(p.prebidCache.prespec.items.length,501,'other stage data remains intact');
 console.log('WORKLINKS_TRANSIENT_PREBID_RECOVERY_PASS');
}
run().catch(e=>{console.error(e);process.exitCode=1});
