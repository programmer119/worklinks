'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright-core');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
const css=(html.match(/<style>([\s\S]*?)<\/style>/)||[])[1]||'';
const extract=(a,b)=>{const start=html.indexOf(a),stop=html.indexOf(b,start+a.length);assert.ok(start>=0&&stop>start,'missing '+a);return html.slice(start,stop)};
const modal=extract('<div class="partner-modal" id="jobDetailModal"','<div class="partner-modal" id="jobHistoryModal"');
const openCode=extract('function openJobDetail(id){','function closeJobDetail(){');
const closeCode=extract('function closeJobDetail(){','// Limit expensive bid-card layout');
const shareCode=extract('const initialJobSearch=','localStorage.setItem("worklinks_job_filter_v1"');
const chrome=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium'].find(fs.existsSync);
assert.ok(chrome,'No Chrome installed');
fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
  for(const [name,w,h] of [['desktop',1280,900],['mobile',390,844]]){
   const page=await browser.newPage({viewport:{width:w,height:h}});
   await page.route('https://worklinks.suaveforge.com/startup-support/**',route=>route.fulfill({
    status:200,contentType:'text/html; charset=utf-8',body:'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>'+
    css+'</style></head><body><div id="jobSearchStatus"></div><div class="cards" id="jobCards"></div>'+modal+'</body></html>'
   }));
   await page.goto('https://worklinks.suaveforge.com/startup-support/?view=changcom&open=R26BK01843011&q=R26BK01843011&stage=bid');
   await page.addScriptTag({content:"\nvar activeDetailJobId=null,jobDetailPriorFocus=null,partners=[],jobSearchText='R26BK01843011';\nvar jobSearchRemote=[],jobSearchServerTotal=null,g2bLiveJobs=[],partnerAllBids={items:[],loaded:0,total:0,state:'error'};\nvar jobSearchByWorkspace={changcom:''},prebidCache={prespec:{state:'idle',items:[]},plan:{state:'idle',items:[]}};\nvar __calls=[],__evidence=0,__opened=0;\nfunction worklinksPartnerAccess(){return true}\nfunction worklinksIsChangcomView(){return true}\nfunction jobSearchNormalized(x){return String(x||'').toLowerCase()}\nfunction scheduleJobsRender(){}\nfunction g2bCardFromServer(x){return {id:'g2b-'+x.kind+'-'+x.bidNo+'-'+x.order,noticeNumber:x.bidNo,title:x.title,kind:x.kind,type:'나라장터 · DB 저장',org:x.org}}\nasync function g2bFetch(p){__calls.push(p);return {ok:true,searchMode:'saved_only',totalCount:1,items:[{bidNo:'R26BK01843011',kind:'servc',order:'000',title:'2026학년도 혁신지원사업 학사행정시스템 고도화 구축',org:'충북보건과학대학교',closes:'2026-12-01 14:00:00'}]}}\nfunction getJobById(id){return jobSearchRemote.find(x=>x.id===id)||(worklinksShareExactBidRow&&worklinksShareExactBidRow.id===id?worklinksShareExactBidRow:null)}\nfunction renderJobDetail(x){__opened++;document.getElementById('jobDetailTitle').textContent=x.title;document.getElementById('jobDetailSub').textContent=x.noticeNumber;document.getElementById('jobDetailBody').textContent=x.org}\nfunction loadStandardBidEvidence(){__evidence++}\nfunction loadJobEligibility(){__evidence++}\nfunction loadJobEvidence(){__evidence++}\nfunction partnerIdsOfJob(){return []}\nfunction openPartnerModal(){}\nfunction openHistoryModal(){}\nfunction g2bCheckStatus(){}\n"});
   await page.addScriptTag({content:openCode+'\n'+closeCode+'\n'+shareCode});
   await page.evaluate(()=>scheduleWorklinksShareOpen());
   await page.waitForSelector('#jobDetailModal.open',{timeout:4000});
   assert.match(await page.locator('#jobDetailTitle').innerText(),/학사행정시스템 고도화 구축/);
   assert.equal(await page.locator('#jobDetailSub').innerText(),'R26BK01843011');
   const state=await page.evaluate(()=>({calls:__calls,opened:__opened,cards:jobSearchRemote.length,count:jobSearchServerTotal}));
   assert.deepEqual(state.calls,['/saved?sw=0&limit=10&offset=0&q=R26BK01843011']);
   assert.equal(state.opened,1);
   assert.equal(state.cards,1);
   assert.equal(state.count,1);
   await page.screenshot({path:path.join(root,'artifacts','exact-bid-'+name+'.png')});
   await page.locator('#jobDetailClose').click();
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   console.log('WORKLINK_EXACT_BID_BROWSER_'+name.toUpperCase()+'=PASS');
   await page.close();
  }
 }finally{await browser.close()}
})().catch(err=>{console.error(err);process.exitCode=1});
