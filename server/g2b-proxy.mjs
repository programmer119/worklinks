import http from 'node:http';
import fs from 'node:fs';

/*
 * Standalone G2B service. Listens only on 127.0.0.1:18191.
 * Configure a Cloudflare Tunnel to expose /api/g2b/* over HTTPS.
 * No user-facing API keys; reads /home/worklinks/secrets/g2b.env.
 */
const PORT=Number(process.env.PORT||18191);

/*
 * 나라장터 전용 서버 프록시. G2B_SERVICE_KEY는 서버 파일에만 보관.
 * 공개 웹페이지로 인증키/요청 URL/원본 에러를 반환하지 않는다.
 */
const G2B_SECRET_PATH = '/home/worklinks/secrets/g2b.env';
const G2B_BASE = Object.freeze({
  bids:'https://apis.data.go.kr/1230000/ad/BidPublicInfoService',
  company:'https://apis.data.go.kr/1230000/ao/UsrInfoService',
  awards:'https://apis.data.go.kr/1230000/as/ScsbidInfoService'
});
const G2B_BID_KINDS = Object.freeze({
  servc:'getBidPblancListInfoServc',
  thng:'getBidPblancListInfoThng',
  cnstwk:'getBidPblancListInfoCnstwk',
  frgcpt:'getBidPblancListInfoFrgcpt'
});
const g2bCache = new Map();
function g2bSecret(){
  const fromEnv = (process.env.G2B_SERVICE_KEY || '').trim();
  if(fromEnv) return fromEnv;
  try {
    const val=fs.readFileSync(G2B_SECRET_PATH,'utf8').split(/\r?\n/).find(x=>x.startsWith('G2B_SERVICE_KEY='));
    return (val || '').slice('G2B_SERVICE_KEY='.length).trim();
  } catch { return ''; }
}
function g2bCors(req,res){
  const origin=req.headers.origin || '';
  if(['https://worklinks.suaveforge.com','https://programmer119.github.io'].includes(origin)){
    res.setHeader('Access-Control-Allow-Origin',origin);
    res.setHeader('Vary','Origin');
    res.setHeader('Access-Control-Allow-Methods','GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers','Content-Type');
  }
}
function g2bReply(res,status,value){
  res.statusCode=status;
  res.setHeader('Content-Type','application/json; charset=utf-8');
  res.setHeader('Cache-Control','no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  res.end(JSON.stringify(value));
}
function g2bDate(v){
  if(!/^\d{8}$/.test(v || ''))return null;
  const iso=v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8);
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) && new Date(iso+'T00:00:00Z').toISOString().slice(0,10)===iso ? Date.parse(iso+'T00:00:00Z') : null;
}
async function g2bCall(service,op,params){
  const key=g2bSecret();
  if(!key)throw Object.assign(new Error('secret_not_configured'),{http:503});
  const u=new URL(G2B_BASE[service]+'/'+op);
  u.searchParams.set('serviceKey',key);
  u.searchParams.set('type','json');
  for(const [k,v] of Object.entries(params))u.searchParams.set(k,String(v));
  let reply;
  try{reply=await fetch(u,{signal:AbortSignal.timeout(12000),headers:{'Accept':'application/json'}});}
  catch{throw Object.assign(new Error('upstream_unreachable'),{http:502})}
  if(!reply.ok)throw Object.assign(new Error('upstream_http_'+reply.status),{http:502});
  let json;
  try{json=JSON.parse(await reply.text())}
  catch{throw Object.assign(new Error('upstream_not_json'),{http:502})}
  const hdr=json.response?.header;
  if(!hdr || (String(hdr.resultCode)!=='00' && String(hdr.resultCode)!=='0')){
    // 응답의 원문에는 serviceKey나 조회 URL 등이 있을 수 있어 외부에 포함하지 않음.
    throw Object.assign(new Error('upstream_result_'+String(hdr?.resultCode || 'unknown').replace(/[^0-9A-Za-z_]/g,'').slice(0,20)),{http:502});
  }
  const body=json.response?.body || {};
  const raw=body.items;
  const list=Array.isArray(raw)?raw:Array.isArray(raw?.item)?raw.item:raw?.item?[raw.item]:[];
  return {totalCount:Number(body.totalCount || list.length),items:list};
}
function g2bMapBid(x,kind){
  return {
    kind,
    bidNo:String(x.bidNtceNo || ''),
    order:Number(x.bidNtceOrd || 0),
    title:String(x.bidNtceNm || ''),
    org:String(x.ntceInsttNm || x.dminsttNm || ''),
    agency:String(x.dminsttNm || ''),
    posted:String(x.bidNtceDt || ''),
    closes:String(x.bidClseDt || ''),
    budget:String(x.asignBdgtAmt || x.presmptPrce || ''),
    url:/^https:\/\//i.test(String(x.bidNtceDtlUrl || ''))?x.bidNtceDtlUrl:'',
    state:String(x.bidNtceSttusNm || ''),
    contract:String(x.cntrctCnclsMthdNm || '')
  };
}
async function g2bRoute(req,res,u){
  g2bCors(req,res);
  if(req.method==='OPTIONS')return g2bReply(res,200,{ok:true});
  if(req.method!=='GET')return g2bReply(res,405,{ok:false,error:'method_not_allowed'});
  if(u.pathname==='/api/g2b/status')return g2bReply(res,200,{ok:true,service:'g2b-proxy',configured:!!g2bSecret(),server_time:new Date().toISOString()});
  if(!g2bSecret())return g2bReply(res,503,{ok:false,error:'secret_not_configured'});
  const kind=u.searchParams.get('kind') || 'servc';
  const no=(u.searchParams.get('bidNo') || '').trim();
  const business=(u.searchParams.get('bizno') || '').replace(/-/g,'');
  const begin=u.searchParams.get('from') || '';
  const end=u.searchParams.get('to') || '';
  const page=Number(u.searchParams.get('page')||1);
  const rows=Number(u.searchParams.get('rows')||50);
  if(!Number.isInteger(page)||page<1||page>20||!Number.isInteger(rows)||rows<1||rows>100)
    return g2bReply(res,400,{ok:false,error:'invalid_pagination'});
  if(u.pathname==='/api/g2b/company'){
    if(!/^\d{10}$/.test(business))return g2bReply(res,400,{ok:false,error:'invalid_bizno'});
    const cacheKey='company:'+business;const prev=g2bCache.get(cacheKey);
    if(prev&&Date.now()-prev.at<3600000)return g2bReply(res,200,prev.data);
    try{
      const [basic,industries]=await Promise.all([
        g2bCall('company','getPrcrmntCorpBasicInfo',{pageNo:1,numOfRows:30,inqryDiv:3,bizno:business}),
        g2bCall('company','getPrcrmntCorpIndstrytyInfo',{pageNo:1,numOfRows:100,inqryDiv:3,bizno:business})
      ]);
      const data={ok:true,bizno:business,company:basic.items,industries:industries.items,generated_at:new Date().toISOString()};
      g2bCache.set(cacheKey,{at:Date.now(),data});return g2bReply(res,200,data);
    }catch(e){return g2bReply(res,e.http||502,{ok:false,error:e.message||'upstream_error'})}
  }
  if(u.pathname==='/api/g2b/awards'){
    if(!/^[A-Z0-9-]{8,40}$/i.test(no))return g2bReply(res,400,{ok:false,error:'invalid_bid_no'});
    try{
      const r=await g2bCall('awards','getScsbidListSttusServc',{pageNo:1,numOfRows:50,inqryDiv:4,bidNtceNo:no});
      return g2bReply(res,200,{ok:true,items:r.items,totalCount:r.totalCount,generated_at:new Date().toISOString()});
    }catch(e){return g2bReply(res,e.http||502,{ok:false,error:e.message||'upstream_error'})}
  }
  if(u.pathname!=='/api/g2b/bids')return g2bReply(res,404,{ok:false,error:'not_found'});
  if(!Object.hasOwn(G2B_BID_KINDS,kind))return g2bReply(res,400,{ok:false,error:'invalid_kind'});
  const b=g2bDate(begin),e=g2bDate(end);
  if(b===null||e===null||e<b||e-b>6*86400000)
    return g2bReply(res,400,{ok:false,error:'date_window_must_be_1_to_7_days'});
  const cacheKey='bids:'+kind+':'+begin+':'+end+':'+page+':'+rows;
  const hit=g2bCache.get(cacheKey);
  if(hit&&Date.now()-hit.at<15*60*1000)return g2bReply(res,200,{...hit.data,cached:true});
  try{
    const r=await g2bCall('bids',G2B_BID_KINDS[kind],{
      pageNo:page,numOfRows:rows,inqryDiv:1,inqryBgnDt:begin+'0000',inqryEndDt:end+'2359'
    });
    const data={ok:true,kind,from:begin,to:end,page,rows,totalCount:r.totalCount,items:r.items.map(x=>g2bMapBid(x,kind)),generated_at:new Date().toISOString(),cached:false};
    if(g2bCache.size>150)g2bCache.clear();
    g2bCache.set(cacheKey,{at:Date.now(),data});
    return g2bReply(res,200,data);
  }catch(e){return g2bReply(res,e.http||502,{ok:false,error:e.message||'upstream_error'})}
}

const server=http.createServer(async(req,res)=>{
 try{
  const u=new URL(req.url,'http://127.0.0.1');
  if(u.pathname==='/health')return g2bReply(res,200,{ok:true,service:'worklinks-g2b',configured:!!g2bSecret()});
  if(u.pathname.startsWith('/api/g2b/'))return await g2bRoute(req,res,u);
  return g2bReply(res,404,{ok:false,error:'not_found'});
 }catch(e){
  return g2bReply(res,502,{ok:false,error:String(e.message||e).slice(0,120)});
 }
});
server.listen(PORT,'127.0.0.1',()=>console.log('worklinks-g2b on 127.0.0.1:'+PORT));
