'use strict';
const { chromium }=require('playwright-core');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const chrome=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium'].find(fs.existsSync);
 if(!chrome)throw Error('CHROME_NOT_AVAILABLE');
 const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const cases=[
 ['prespec-detail','https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo=R26BD00301798'],
 ['prespec-search','https://www.g2b.go.kr/link/PRCA001_04/single/?flag=cnrtSl&srch=0002&bfSpecRegNo=R26BD00301798&srchPreStdRgstNo=R26BD00301798'],
 ['plan-detail','https://www.g2b.go.kr/link/PRPA015_01/single/?oderPlanNo=R26DD20933570']
 ];
 fs.mkdirSync(path.join(__dirname,'../artifacts'),{recursive:true});
 try{
  for(const [label,url] of cases){
   const page=await browser.newPage({viewport:{width:1365,height:900},locale:'ko-KR'});
   let status=null,error=null;
   try{
    const response=await page.goto(url,{timeout:22000,waitUntil:'domcontentloaded'});
    status=response&&response.status();
    await page.waitForTimeout(6000);
    const title=await page.title();
    const location=page.url();
    const body=(await page.locator('body').innerText().catch(()=>'')); 
    const extract=body.replace(/\\s+/g,' ').slice(0,1400);
    const exact=body.includes(label==='plan-detail'?'R26DD20933570':'R26BD00301798');
    console.log('G2B_ROUTE_PROBE '+JSON.stringify({label,status,title,location,exact,excerpt:extract}));
    await page.screenshot({path:path.join(__dirname,'../artifacts','g2b-route-'+label+'.png'),fullPage:false});
   }catch(e){error=String(e&&e.message||e).slice(0,250);console.log('G2B_ROUTE_PROBE '+JSON.stringify({label,status,error}));}
   await page.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});