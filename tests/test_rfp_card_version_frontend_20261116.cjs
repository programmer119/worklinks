#!/usr/bin/env node
'use strict';
// Exercises the exact frontend helpers from index.html with stale saved-list
// state, the live per-notice batch API and two real notice identifiers.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'..','startup-support','index.html'),'utf8');
const start=html.indexOf('var rfpCardEvidenceRequested=new Set()');
const end=html.indexOf('// A compact, official-byte-verified fact feed',start);
assert(start>=0&&end>start,'version-aware live card helper missing');
const fragment=html.slice(start,end);

const keys=['R26BK01810506:001','R26BK01826049:000'];
const unversioned={
 seen:true,complete:true,scanComplete:true,
 staffingRoleScanComplete:true,status:'text_extracted_requires_review',
 documentCount:4,readableCount:3,effectiveReadableCount:4
};
const versioned={
 ...unversioned,parserCurrent:true,versionSource:'coverage_index',
 classificationVersion:23,hwpxReaderVersion:3,
 staffingRoleVersions:[4],staffingFactVersions:[2],
 checkedAt:'2026-11-15T17:00:00Z'
};
const saved=new Map(keys.map(k=>[k,{...unversioned}]));
const completed=new Map();
const calls=[];
let renders=0;
const ctx={
 jobSearchRfpState:saved,jobListRfpState:completed,
 jobBidIdentity(x){return {bidNo:x.bidNo,order:x.order}},
 g2bFetch(url){calls.push(url);
   return Promise.resolve({ok:true,sourceAvailable:true,
       byNotice:Object.fromEntries(keys.map(k=>[k,{...versioned}]))})},
 scheduleJobsRender(){renders++},
 Date,Map,Set,Number,encodeURIComponent,Promise,
};
vm.createContext(ctx);
vm.runInContext(fragment,ctx);
const rows=[{bidNo:'R26BK01810506',order:'001'},
            {bidNo:'R26BK01826049',order:'000'}];
async function main(){
  ctx.ensureVisibleRfpCardEvidence(rows);
  assert.equal(calls.length,1,'unversioned saved rows must trigger a live fetch');
  await Promise.resolve();
  await Promise.resolve();
  for(const key of keys){
    assert.equal(ctx.rfpBestCardScan(key).parserCurrent,true,key);
    assert.equal(ctx.rfpBestCardScan(key).classificationVersion,23,key);
    assert.equal(ctx.rfpBestCardScan(key).versionSource,'coverage_index',key);
  }
  assert(renders>0,'live version update must rerender cards');
  ctx.ensureVisibleRfpCardEvidence(rows);
  assert.equal(calls.length,1,'already verified rows must not refetch');
  const stale={...unversioned,checkedAt:'2026-11-15T17:00:01Z'};
  saved.set(keys[0],stale);
  assert.equal(ctx.rfpBestCardScan(keys[0]).parserCurrent,true,
    'newer unversioned search state must never obscure verified card evidence');
  console.log('WORKLINKS_ONSITE_CARD_CURRENT_VERSION_FALLBACK_AND_DEDUP=PASS');
}
main().catch(e=>{console.error(e);process.exitCode=1});
