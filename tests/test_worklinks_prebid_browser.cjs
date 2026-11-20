'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright-core');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
const stageJS=fs.readFileSync(path.join(root,'startup-support/changcom-prebid.js'),'utf8');
function extract(start,end) {
 const a=html.indexOf(start),b=html.indexOf(end,a+start.length);
 assert.ok(a>=0&&b>a,'missing unchanged main-page code: '+start);
 return html.slice(a,b);
}
const css=(html.match(/<style>([\s\S]*?)<\/style>/)||[])[1]||'';
const modal=extract('<div class="partner-modal" id="jobDetailModal"','<div class="partner-modal" id="jobHistoryModal"');
const oldBidEvents=extract('document.getElementById("jobCards").addEventListener("click",function(e){','renderPartners();');
const oldCloseEvents=extract('function closeJobDetail(){','// Limit expensive bid-card layout');
const chrome=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium'].find(fs.existsSync);
assert.ok(chrome,'Chrome binary missing on CI runner');
fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:chrome,args:['--no-sandbox','--disable-dev-shm-usage']});
 try {
  for(const [label,width,height] of [['desktop',1280,900],['mobile',390,844]]){
   const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
   await page.setContent('<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>'+
    css+'</style></head><body><select id="partnerNoticeStage"><option value="all">전체</option>'+
    '<option value="prespec">사전규격</option></select><div class="cards" id="jobCards"></div>'+
    modal+'</body></html>');
   const bootstrap=[
    'var activeDetailJobId=null,jobDetailPriorFocus=null;',
    'var __oldBidOpen=[];',
    'function openJobDetail(id){__oldBidOpen.push(id)}',
    'function openPartnerModal(){} function openHistoryModal(){}',
    'function worklinksPartnerAccess(){return true}',
    'function renderJobs(){}',
    'function jobSearchNormalized(v){return String(v||"").toLowerCase()}',
    'function jobOriginUrl(x){return x.url||"https://www.g2b.go.kr/"}',
    'function jobAmountLabel(x){return String(x)}',
    'function htmlEscape(v){return String(v||"").replace(/[&<>"'+"']"+'/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'+
       '"\\"":"&quot;","'+"'\":"+"'&#39;'"+'}[c]))}',
    'window.worklinksKeeps={keepButton:id=>"<button type=button data-keep-toggle="+id+">☆ 킵</button>"};'
   ].join('\n');
   await page.addScriptTag({content:bootstrap});
   await page.addScriptTag({content:stageJS});
   await page.addScriptTag({content:oldCloseEvents+'\n'+oldBidEvents});
   await page.evaluate(()=>{
     prebidCache.prespec.items=[{id:'R26BD00301798',stage:'prespec',kind:'servc',
      title:'학생관리 시스템 구축 용역',org:'연세대학교 미래캠퍼스',
      posted:'2026-11-17 16:37:24',budget:'39930000',
      opinionDeadline:'202611191800',url:'',subject:'교육지원 시스템 구축',files:[]}];
     document.getElementById('jobCards').innerHTML=prebidNoticeCardMarkup(prebidCache.prespec.items[0]);
   });
   assert.equal(await page.locator('[data-prebid-detail]').count(),1);
   assert.equal(await page.getByText('공유 링크').count(),0);
   await page.locator('[data-prebid-detail]').click();
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'false');
   assert.match(await page.locator('#jobDetailSub').innerText(),/사전규격/);
   assert.match(await page.locator('#jobDetailBody').innerText(),/의견등록 마감/);
   assert.match(await page.locator('#jobDetailBody').innerText(),/원문 직접 주소 미확인/);
   assert.equal(await page.locator('#jobDetailBody a.job-external-link').count(),0);
   assert.equal(await page.evaluate(()=>__oldBidOpen.length),0);
   await page.screenshot({path:path.join(root,'artifacts','prespec-'+label+'.png')});
   await page.locator('#jobDetailClose').click();
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   await page.locator('[data-prebid-detail]').focus();
   await page.keyboard.press('Enter');
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'false');
   await page.keyboard.press('Escape');
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   await page.locator('[data-keep-toggle]').click();
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   await page.evaluate(()=>{
    prebidCache.plan.items=[{id:'R26DD20928584',stage:'plan',kind:'servc',
     title:'교육지원 시스템 발주계획',org:'발주기관',budget:'120000000',
     plannedMonth:'2026-12',url:'https://www.g2b.go.kr/link/PRPA015_01/single/?oderPlanNo=R26DD20928584',
     files:[]}];
    document.getElementById('jobCards').innerHTML=prebidNoticeCardMarkup(prebidCache.plan.items[0]);
   });
   await page.locator('[data-prebid-detail]').click();
   assert.match(await page.locator('#jobDetailBody').innerText(),/발주예정/);
   assert.match(await page.locator('#jobDetailSub').innerText(),/발주계획/);
   assert.equal(await page.locator('#jobDetailBody a.job-external-link').count(),1);
   await page.locator('#jobDetailClose').click();
   await page.evaluate(()=>{
    document.getElementById('jobCards').innerHTML=combinedBidCardMarkup({
     id:'g2b-servc-R26BK01830000-000',kind:'servc',title:'정상 입찰공고',
     org:'공공기관',amount:'100000000'});
   });
   await page.locator('[data-job-card]').click();
   const opened=await page.evaluate(()=>__oldBidOpen);
   assert.deepEqual(opened,['g2b-servc-R26BK01830000-000']);
   assert.equal(await page.locator('#jobDetailModal').getAttribute('aria-hidden'),'true');
   const metrics=await page.evaluate(()=>({
    page:document.documentElement.scrollWidth,viewport:innerWidth,
    cards:document.querySelector('#jobCards')?.children.length||0
   }));
   assert.ok(metrics.page<=metrics.viewport+2,'horizontal document overflow at '+label+': '+JSON.stringify(metrics));
   await page.close();
   console.log('WORKLINK_EARLY_STAGE_BROWSER_'+label.toUpperCase()+'=PASS');
  }
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
