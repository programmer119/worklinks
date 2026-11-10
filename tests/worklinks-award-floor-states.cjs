// Verify truthful award-floor states without relying on unrelated Jobs ranking fixtures.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const begin=source.indexOf('function g2bCardAwardMetadata(x){');
const end=source.indexOf('function renderJobs(){',begin);
assert.ok(begin>=0&&end>begin,'missing display functions');
const methods=source.slice(begin,end);
const factory=new Function('g2bAwardFallbackByNotice','g2bAwardFallbackLoadState','htmlEscape','jobBidIdentity',
  methods+'return {g2bCardAwardMetadata,g2bAwardFloorDisplay,bidMethodCardMarkup}');
const escape=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const getId=x=>x.noticeNumber?{bidNo:x.noticeNumber,order:String(x.noticeOrder||'000').padStart(3,'0')}:null;
const base={id:'g2b-servc-R26BK00000101-000',noticeNumber:'R26BK00000101',noticeOrder:'000'};
function assess(code,rate='',options={},state='loaded',fallback=new Map()){
  const api=factory(fallback,state,escape,getId);
  const x={...base,awardMethodCode:code,awardFloorRate:rate,...options};
  const meta=api.g2bCardAwardMetadata(x);
  return {...api.g2bAwardFloorDisplay(meta),markup:api.bidMethodCardMarkup(x)};
}
for(const [code,rate,options,state,expected] of [
  ['낙030029','88',{},'loaded','88%'],
  ['낙030005','',{},'loaded','하한율 비적용'],
  ['낙030001','',{awardFieldsVerified:true},'loaded','원본 미기재'],
  ['낙030001','',{awardFieldsFetchStatus:'error'},'loaded','수집 실패'],
  ['낙030001','',{},'error','수집 실패'],
  ['낙030001','',{},'loading','조사 미완료'],
  ['낙030001','',{},'loaded','조사 미완료'],
  ['낙099999','',{},'loaded','확인 필요'],
  ['','',{},'not_started','조사 미완료'],
  ['','',{awardFieldsVerified:true},'loaded','원본 미기재'],
  ['낙030029','N/A',{awardFieldsVerified:true},'loaded','확인 필요']
]){
  const out=assess(code,rate,options,state);
  assert.equal(out.value,expected,JSON.stringify({code,rate,state,expected,actual:out.value}));
  assert.ok(out.markup.includes(expected),'display must match computed status');
  assert.ok(out.markup.includes('title="'),'each visible state must explain source interpretation');
}
const fallback=new Map([['R26BK00000101:000',{
  contract:'제한경쟁',awardMethodCode:'낙030001',awardFloorRate:'',awardFieldsVerified:true
}]]);
assert.equal(assess('','',{},'loaded',fallback).value,'원본 미기재',
  'server123 official DB fallback proves the missing field was from a successful request');
assert.equal(assess('낙030005','',{awardFieldsFetchStatus:'error'},'error').value,'하한율 비적용',
  'known nonapplicable method classification must remain independent of missing number');
assert.equal(assess('낙030029','0',{awardFieldsVerified:true}).value,'확인 필요',
  'invalid numeric zeros must not masquerade as a valid percent or source omission');
assert.equal(assess('낙030001','88.745',{awardFieldsFetchStatus:'error'}).value,'88.745%',
  'confirmed numeric value must not be hidden by a separate supplemental fetch failure');
let scripts=0;
for(const [,attrs,body] of source.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){
  if(/\bsrc\s*=/.test(attrs)||!body.trim()||/\btype=['"]application\/(?:ld\+json|json)/.test(attrs))continue;
  new vm.Script(body);scripts++;
}
assert.ok(scripts,'no inline script syntax checked');
console.log('WORKLINKS_AWARD_FLOOR_FIVE_STATES=PASS');
