'use strict';
// Real Chrome click test: current main-page event handlers + the stage module.
// No network access to government APIs; no production data/service mutation.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright-core');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
const moduleJS=fs.readFileSync(path.join(root,'startup-support/changcom-prebid.js'),'utf8');
const extract=(start,end)=>{
 const a=html.indexOf(start),b=html.indexOf(end,a+start.length);
 assert.ok(a>=0&&b>a,'missing main-page region '+start);
 return html.slice(a,b);
};
const modal=extract('<div class="partner-modal" id="jobDetailModal"','<div class="partner-modal" id="jobHistoryModal"');
const originalOpen=extract('function openJobDetail(id){','function closeJobDetail(){');
const originalClose=extract('function closeJobDetail(){','// Limit expensive bid-card layout');
const originalCardEvents=extract('document.getElementById("jobCards").addEventListener("click",function(e){','renderPartners();');
const style=(html.match(/<style>([\s\S]*?)<\/style>/)||[])[1]||'';
const chrome=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium'].find(fs.existsSync);
assert.ok(chrome,'Chrome binary missing on test runner');
fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
  for(const [label,w,h] of [['desktop',1280,900],['mobile',390,844]]){
   const page=await browser.newPage({viewport:{width:w,height:h}});
   await page.setContent('<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>'+
    style+'</style></head><body><select id="partnerNoticeStage"><option value="all">전체</option>'+
    '<option value="prespec">사전규격</option></select><section id="jobsView" class="on">'+
    '<div class="cards" id="jobCards"></div></section>'+modal+'</body></html>');
   const fake=[
    'var activeDetailJobId=null,jobDetailPriorFocus=null,partners=[];',
    'var __record={ordinary:0,evidence:0};',
    'function partnerIdsOfJob(){return []}',
    'function loadStandardBidEvidence(){__record.evidence++}',
    'function loadJobEligibility(){__record.evidence++}',
    'function loadJobEvidence(){__record.evidence++}',
    'function openPartnerModal(){} function openHistoryModal(){}',
    'function worklinksPartnerAccess(){return true}',
    'function renderJobs(){}',
    'function jobSearchNormalized(v){return String(v||"").toLowerCase()}',
    'function jobOriginUrl(x){return x.url||""}',
    'function jobAmountLabel(v){return String(v)}',
    'function htmlEscape(v){return String(v||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;")}',
    'window.worklinksKeeps={keepButton:id=>"<button type=button data-keep-toggle="+id+">☆ 킵</button>"};'
   ].join('\n');
   await page.addScriptTag({content:fake});
   await page.addScriptTag({content:moduleJS});
   await page.addScriptTag({content:[
    'function getJobById(id){',
    ' const early=typeof prebidKeepJobFromId==="function"?prebidKeepJobFromId(id):null;',
    ' return early||{id,title:"일반 입찰공고",type:"나라장터",noticeNumber:"R26BK01830000"};',
    '}',
    'function renderJobDetail(x){',
    ' if(activeDetailJobId!==x.id)return;',
    ' if(typeof renderPrebidSourceDetail==="function"&&renderPrebidSourceDetail(x))return;',
    ' __record.ordinary++;',
    ' document.getElementById("jobDetailTitle").textContent=x.title;',
    '}'
   ].join('\n')});
   await page.addScriptTag({content:originalOpen+'\n'+originalClose+'\n'+originalCardEvents});
   await page.evaluate(()=>{
    prebidCache.prespec.items=[{id:'R26BD00301798',stage:'prespec',kind:'servc',
     title:'학생관리 시스템 구축 용역',org:'연세대학교 미래캠퍼스',budget:'39930000',
     posted:'2026-11-17 16:37:24',opinionDeadline:'202611191800',
     url:'',files:[],subject:'학생관리'}];
    document.getElementById('jobCards').innerHTML=prebidNoticeCardMarkup(prebidCache.prespec.items[0]);
   });
   assert.equal(await page.getByText('공유 링크').count(),0);
   await page.locator('#jobCards [data-job-card]').click();
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'false');
   assert.match(await page.locator('#jobDetailSub').innerText(),/사전규격/);
   assert.match(await page.locator('#jobDetailBody').innerText(),/학생관리/);
   assert.match(await page.locator('#jobDetailBody').innerText(),/나라장터 상세 연결이 안 되면/);
   assert.equal(await page.locator('#jobDetailBody a.job-external-link').count(),1);
   assert.equal(await page.locator('#jobDetailBody a.job-prebid-source-lookup').count(),1);
   assert.equal(await page.locator('#jobDetailBody a[href="./share/R26BD00301798/"]').count(),1);
   assert.equal(await page.evaluate(()=>__record.evidence),0,'no bid-specific extra API path');
   await page.screenshot({path:path.join(root,'artifacts','stage-final-'+label+'.png')});
   await page.locator('#jobDetailClose').click();
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   await page.locator('#jobCards [data-job-card]').focus();
   await page.keyboard.press('Enter');
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'false');
   await page.keyboard.press('Escape');
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   await page.locator('#jobCards [data-keep-toggle]').click();
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   // Real observed G2B Content-Disposition: no fake "규격서 1/2/3".
   await page.evaluate(()=>{
    const id='R26BD00302593';
    const files=[1,2,3].map(n=>'https://www.g2b.go.kr/pn/pnz/pnza/UntyAtchFile/downloadFile.do?bfSpecRegNo='+id+'&fileType=BFDTL&fileSeq='+n);
    const record={id,stage:'prespec',kind:'servc',title:'원문 첨부 확인',
     org:'인천테크노파크',posted:'2026-11-18',opinionDeadline:'2026-11-23',
     files,fileNames:['붙임 제안요청서.hwpx','붙임 제출서식.hwpx','붙임 긴급입찰사유서.hwpx'],url:''};
    prebidCache.prespec.items=[record];
    document.getElementById('jobCards').innerHTML=prebidNoticeCardMarkup(record);
   });
   for(const name of ['붙임 제안요청서.hwpx','붙임 제출서식.hwpx','붙임 긴급입찰사유서.hwpx'])
    assert.equal(await page.locator('#jobCards a.prebid-doc-link').filter({hasText:name}).count(),1);
   await page.locator('#jobCards [data-job-card]').click();
   for(const name of ['붙임 제안요청서.hwpx','붙임 제출서식.hwpx','붙임 긴급입찰사유서.hwpx'])
    assert.equal(await page.locator('#jobDetailBody a.job-source-file').filter({hasText:name}).count(),1);
   assert.equal(await page.locator('#jobDetailBody a.job-external-link').count(),1);
   assert.equal(await page.locator('#jobDetailBody a.job-prebid-source-file').count(),0);
   await page.screenshot({path:path.join(root,'artifacts','prespec-original-names-'+label+'.png')});
   await page.locator('#jobDetailClose').click();
   await page.evaluate(()=>{
    document.getElementById('jobCards').innerHTML=combinedBidCardMarkup({
     id:'g2b-servc-R26BK01830000-000',kind:'servc',title:'일반 입찰공고',
     org:'발주기관',amount:'100000000'});
   });
   await page.locator('#jobCards [data-job-card]').click();
   assert.ok(await page.evaluate(()=>__record.ordinary)>0,'ordinary bid renderer path preserved');
   assert.ok(await page.evaluate(()=>__record.evidence)>0,'ordinary bid APIs still reachable');
   await page.locator('#jobDetailClose').click();
   await page.close();
   console.log('WORKLINK_FINAL_STAGE_BROWSER_'+label.toUpperCase()+'=PASS');
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
