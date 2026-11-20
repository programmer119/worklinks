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
   await page.addScriptTag({content: