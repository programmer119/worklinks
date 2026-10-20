// Run on a networked CI runner: node tests/worklinks-live-partner-smoke.cjs
// Uses real public API responses and EXACT match functions from the deployed HTML source.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const part=(a,b)=>{const start=source.indexOf(a),end=source.indexOf(b,start+a.length);assert.ok(start>=0&&end>start);return source.slice(start,end)};
const base='https://api-suaveforge.suaveforge.com:18458/api/g2b';
async function get(uri){
 const response=await fetch(base+uri,{signal:AbortSignal.timeout(28000)});
 if(!response.ok)throw Error(uri+' HTTP '+response.status);
 return await response.json();
}
(async()=>{
 const [company,first]=await Promise.all([get('/company?bizno=1308185973'),get('/saved?sw=1&limit=500&offset=0')]);
 assert.ok(company.found&&company.complete,'Changcom registry must be complete');
 const partner={id:'changcom',name:'창컴정보통신(주)',
  registryCheckedAt:company.checkedAt,registryComplete:company.complete,
  industryRecords:company.industries};
 const code=part('const partnerIndustryKnownCodes=','var partnerFetchStarted=false')+
  part('function partnerRegisteredCode(p,code){','function comparePartnerJob(x,p){')+
  'return {jobSoftwareScope,jobQualificationVerdict,jobPartnerMatches,jobPartnerCandidates,partnerRegisteredCode};';
 const mod=new Function('partners','jobEligibilityData','kstISO','jobBidIdentity','jobTimeInfo','jobOriginUrl',code)(
  [partner],x=>x.bidEligibility,()=>new Date(Date.now()+9*3600000).toISOString().slice(0,10),
  ()=>null,()=>({start:null}),()=>'' );
 assert.equal(mod.partnerRegisteredCode(partner,'1468'),true,'official 1468 registration should be active');
 const rows=[...(first.items||[])];
 for(let offset=500;offset<Number(first.totalCount||0);offset+=500){
  const data=await get('/saved?sw=1&limit=500&offset='+offset);
  rows.push(...(data.items||[]));
 }
 // The public SQLite /saved SW index is the corpus to display. Recreate the
 // exact G2B card identity; a second title-only heuristic must not hide it.
 const indexed=rows.map(row=>({...row,id:'g2b-'+row.kind+'-'+row.bidNo+'-'+row.order,
  subject:row.purchsObjPrdctList||''}));
 const scopeTotals={candidate:0,mixed:0,unknown:0,out:0};
 for(const row of indexed)scopeTotals[mod.jobSoftwareScope(row)]++;
 assert.equal(scopeTotals.out,0,'no official SW-indexed notice may disappear through a title-only exclusion');
 assert.equal(indexed.length,Number(first.totalCount),'all saved SW candidates must be checked without an arbitrary page cap');
 console.log('WORKLINKS_INDEXED_SW_VISIBILITY',JSON.stringify({total:indexed.length,scopes:scopeTotals}));
 const relevant=indexed.filter(row=>mod.jobSoftwareScope(row)==='candidate'&&
  (!row.closes||Date.parse(row.closes.replace(' ','T')+'+09:00')>=Date.now()));
 const summary={total:rows.length,swServiceCandidates:relevant.length,confirmed:0,pending:0,missing:0,
  examples:[]};
 for(const row of relevant){
  const v=mod.jobQualificationVerdict(row,partner);
  if(v.type==='industry_match'){
   summary.confirmed++;
   if(summary.examples.length<10)summary.examples.push({bidNo:row.bidNo,title:row.title,
    closes:row.closes,codes:v.codes});
  }else if(v.type==='unverified')summary.pending++;
  else if(v.type==='missing')summary.missing++;
 }
 console.log('LIVE_PARTNER_MATCH_SUMMARY',JSON.stringify(summary));
 const sample=relevant.find(x=>x.bidNo==='R26BK01764205');
 if(sample){
  const match=mod.jobQualificationVerdict(sample,partner);
  console.log('REAL_NOTICE_R26BK01764205',JSON.stringify({type:match.type,codes:match.codes}));
  assert.equal(match.type,'industry_match','1468-only real notice must be matched');
 }
 assert.ok(summary.confirmed>0,'Live confirmed partner match must NOT be zero');
 console.log('LIVE_REAL_DATA_PARTNER_MATCH=PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
