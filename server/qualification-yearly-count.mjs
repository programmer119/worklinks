#!/usr/bin/env node
/**
 * WorkLinks: verified G2B annual industry-filtered notice count.
 * Method: API PPSSrch indstrytyCd, service/goods notices, per-month fully paginated,
 * de-duplicate bid numbers. Separate title-screened SW candidates from all notices.
 * No direct-production certificates or other attachments are counted here.
 * Requires G2B_SERVICE_KEY env or /run/g2b.env (never emit key in logs).
 */
const fs=require('fs');
const key=process.env.G2B_SERVICE_KEY || (()=>{try {return fs.readFileSync('/run/g2b.env','utf8').match(/^G2B_SERVICE_KEY=(.*)$/m)?.[1]?.trim()||''}catch{return ''}})();
if(!key){console.error('ERROR=missing_server_api_key');process.exit(2)}
const output=process.argv[2]||'/work/report/qualification-year.json';
const startDate='2025-10-12',endDate='2026-10-12';
const base='https://apis.data.go.kr/1230000/ad/BidPublicInfoService';
const operations={servc:'getBidPblancListInfoServcPPSSrch',thng:'getBidPblancListInfoThngPPSSrch'};
const codes=[
 {id:'1468',label:'SW사업자(컴퓨터관련서비스사업)'},
 {id:'1426',label:'SW사업자(패키지SW개발·공급사업)'},
 {id:'1469',label:'SW사업자(디지털콘텐츠개발서비스사업)'},
 {id:'1470',label:'SW사업자(DB제작·검색서비스사업)'},
 {id:'1169',label:'학술·연구용역'},
 {id:'0036',label:'정보통신공사업'}
];
const swTitle=/(소프트웨어|에스더블유|[A-Z]\/W|(?:^|[^a-z])SW(?:[^a-z]|$)|정보\s*시스템|업무\s*시스템|IT\s|전산|홈페이지|웹\s*사이트|웹\s*서비스|웹\s*페이지|정보화|인공지능|인공\s*지능|\bAI\b|클라우드|데이터|데이타|DB\s|DB$|DB\b|디지털|네트워크|플랫폼|전산화|시스템|프로그램|정보\s*보안|사이버\s*보안|정보\s*보호|정보\s*통신|모바일|어플리케이션|\bICT\b|\bRPA\b|정보\s*인프라|서버|GIS|전자\s*문서|로봇\s*프로세스)/i;
const months=[];
for(let year=2025,month=10; year<2026||(year===2026&&month<=10);month++){
 if(month===13){year++;month=1}
 if(year===2026&&month>10)break;
 const first=new Date(Date.UTC(year,month-1,1)),last=new Date(Date.UTC(year,month,0));
 const a=new Date(Math.max(first.getTime(),Date.parse(startDate+'T00:00:00Z')));
 const b=new Date(Math.min(last.getTime(),Date.parse(endDate+'T00:00:00Z')));
 if(a<=b)months.push({from:a.toISOString().slice(0,10).replace(/-/g,''),to:b.toISOString().slice(0,10).replace(/-/g,'')});
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let apiCalls=0;
async function req(op,params){
 const u=new URL(base+'/'+op);for(const [k,v] of Object.entries({serviceKey:key,type:'json',inqryDiv:1,pageNo:1,numOfRows:500,...params}))u.searchParams.set(k,String(v));
 let last;
 for(let attempt=1;attempt<=3;attempt++){
  try{
   apiCalls++;
   const r=await fetch(u,{signal:AbortSignal.timeout(18000)});
   const doc=await r.json();
   const h=doc?.response?.header||doc?.['nkoneps.com.response.ResponseError']?.header||{};
   if(r.status!==200 || !['00','0'].includes(String(h.resultCode))){
     const reason='HTTP='+r.status+' resultCode='+String(h.resultCode||'none');
     if(!['05','22','23'].includes(String(h.resultCode)))throw Error(reason);
     throw Error('RETRY '+reason)
   }
   const body=doc.response?.body||{};
   let items=body.items||[];
   if(!Array.isArray(items))items=items.item||[];
   if(!Array.isArray(items))items=[items];
   return{items,total:Number(body.totalCount||items.length)};
  }catch(e){
   last=String(e.message).replace(key,'[redacted]');
   if(attempt<3)await sleep(1000*attempt);
  }
 }
 throw Error(last);
}
async function run(){
 const counts=[];
 const errors=[];
 const started=new Date().toISOString();
 for(const code of codes){
  const all=new Map();
  const screened=new Map();
  let rawTotalSum=0,codeCalls=0,fullyRead=true,nonMatching=0;
  for(const kind of Object.keys(operations)){
   for(const win of months){
    const params={inqryBgnDt:win.from+'0000',inqryEndDt:win.to+'2359',indstrytyCd:code.id};
    try{
      const first=await req(operations[kind],params);codeCalls++;
      if(first.total>15000)throw Error('window_too_large_to_page: '+first.total);
      const pages=Math.ceil(first.total/500)||1;
      let arr=first.items.slice();
      for(let page=2;page<=pages;page++){
        const part=await req(operations[kind],{...params,pageNo:page});codeCalls++;
        arr.push(...part.items);
      }
      if(arr.length<first.total)throw Error('missing_records '+arr.length+'/'+first.total);
      rawTotalSum+=first.total;
      for(const x of arr){
        const no=String(x.bidNtceNo||'').trim(),title=String(x.bidNtceNm||'').trim();
        if(!no){nonMatching++;continue}
        const id=kind+':'+no;
        all.set(id,{id:no,kind,title,url:x.bidNtceDtlUrl||'',date:x.bidNtceDt||''});
        if(swTitle.test(title))screened.set(id,{id:no,kind,title,url:x.bidNtceDtlUrl||'',date:x.bidNtceDt||''});
      }
    }catch(e){fullyRead=false;errors.push({code:code.id,kind,window:win.from+'-'+win.to,error:String(e.message).slice(0,90)});}
    await sleep(160);
   }
  }
  const example=[...screened.values()].sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,4);
  counts.push({code:code.id,label:code.label,rawCount:all.size,swTitleCount:screened.size,complete:fullyRead,
    rawReportedCount:rawTotalSum,requests:codeCalls,examples:example});
  console.log('YEARLY_CODE '+code.id+' allDistinct='+all.size+' SWTitleCandidate='+screened.size+' complete='+fullyRead+' calls='+codeCalls);
 }
 const result={source:'나라장터 입찰공고정보서비스 / getBidPblancListInfoServcPPSSrch + getBidPblancListInfoThngPPSSrch',from:startDate,to:endDate,generatedAt:new Date().toISOString(),startedAt:started,filters:{types:['servc','thng'],industryCodes:codes.map(x=>x.id),title:'SW/IT 제목 키워드 후보',excluded:'공사·외자 및 원문 첨부의 개별 증명서 요건'},counts,errors,apiCalls,complete:errors.length===0,interpretation:'해당 업종코드의 API 검색 결과에서 SW/IT 관련 공고 제목만 걸러 중복 공고번호를 제거한 수치. 정확한 필수자격 인정 여부와 직접생산증명서 요구건수는 첨부원문 검증 필요.'};
 fs.mkdirSync(require('path').dirname(output),{recursive:true});
 fs.writeFileSync(output,JSON.stringify(result,null,2));
 console.log('YEARLY_RESULT_JSON='+output+' apiCalls='+apiCalls+' errors='+errors.length+' complete='+result.complete);
 if(errors.length){console.log('YEARLY_ERRORS',JSON.stringify(errors.slice(0,25)));process.exitCode=3}
}
run().catch(e=>{console.error('YEARLY_FATAL',e.name,String(e.message).slice(0,160));process.exitCode=4});
