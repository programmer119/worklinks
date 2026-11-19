/* Changcom: source-backed procurement stage and SW award filters.
 * Existing bid records require no new G2B requests; prebid reads local server DB.
 */
let partnerSwScope='all', partnerAwardFilter='all', partnerNoticeStage='bid';
const prebidCache={plan:{state:'idle',items:[],total:0,error:'',at:''},
                   prespec:{state:'idle',items:[],total:0,error:'',at:''}};
const PRICE_METHODS=new Set(['낙030021','낙030022','낙030029']);
const SPEC_PRICE_METHODS=new Set(['낙030002','낙030003','낙030018']);
function swBuildTitle(x){
 const raw=String(x?.title||x?.name||'').normalize('NFKC');
 const subject=String(x?.subject||x?.purchsObjPrdctList||'');
 const text=(raw+' '+subject).toLowerCase();
 // Building electrical, fire safety or telecom construction is not SW development.
 if(/^(cnstwk|frgcpt)$/.test(String(x?.kind||''))&&!/(sw|s\/w|소프트웨어|정보시스템|전산시스템|플랫폼|웹|앱|데이터베이스)/i.test(raw))return false;
 // Ancillary procurement must not masquerade as an SW-development contract.
 if(/(감리|인력\s*지원|청소\s*용역|시설\s*관리|홍보\s*영상|기자재\s*(?:구매|구입|설치)|소모품|토너|구축\s*방안\s*연구|정보화\s*교육\s*운영)/.test(raw))return false;
 // '인재개발원' and '개발제한구역' are not software development.
 const development=/(구축|고도화|개편|재구축|전환|시스템\s*(?:기능\s*)?개선|기능\s*개선|리뉴얼|개발(?!원|제한구역))/.test(raw);
 const software=/(소프트웨어|정보시스템|전산시스템|플랫폼|웹사이트|웹서비스|홈페이지|모바일\s*앱|응용sw|s\/w|\bsw\b|데이터베이스|통합시스템|(?:업무|보험|행정|학사|운영|관리)시스템|전자정부|ai\s*시스템|인공지능\s*시스템|디지털\s*서비스)/i.test(text);
 return development&&software;
}
function partnerBidMatchesNewFilters(x){
 if(partnerSwScope==='build'&&!swBuildTitle(x))return false;
 if(partnerAwardFilter==='all')return true;
 if(!/^g2b-/.test(String(x?.id||'')))return false;
 const m=g2bCardAwardMetadata(x);
 if(!m.sourceVerified)return false; // never infer an award method from title
 const code=String(m.awardMethodCode||'');
 switch(partnerAwardFilter){
 case 'price':return PRICE_METHODS.has(code);
 case 'qualification':return code==='낙030001';
 case 'spec-price':return SPEC_PRICE_METHODS.has(code);
 case 'negotiation':return code==='낙030005';
 default:return true;
 }
}
async function loadPrebidJobs(stage,force=false){
 if(!['plan','prespec'].includes(stage)||!worklinksPartnerAccess())return;
 const state=prebidCache[stage];
 if(state.state==='loading')return;
 if(!force&&state.state==='ready'&&Date.now()-Number(state.cachedAt||0)<60000)return;
 state.state='loading';state.error='';
 renderJobs();
 try{
  let data=[],offset=0,total=null,at='',ready=false,complete=false;
  for(let page=0;page<10;page++){
   const res=await g2bFetch('/prebid?stage='+stage+'&limit=500&offset='+offset);
   if(!res||res.ok!==true)throw Error(res?.error||'사전 단계 목록 응답 오류');
   if(!res.ready)throw Error(res.error||'사전 단계 수집 자료 없음');
   ready=true;at=res.asOf||at;total=Number(res.total||0);
   if(!Number.isSafeInteger(total)||total<0||!Array.isArray(res.items))throw Error('사전 단계 DB 집계 오류');
   data.push(...res.items);offset=data.length;
   if(offset>=total){complete=true;break}
   if(!res.items.length)throw Error('사전 단계 목록 페이지 불완전');
  }
  if(!ready||!complete)throw Error('사전 단계 목록 일부만 수신, 전체 판정 보류');
  state.items=data;state.total=data.length;state.at=at;state.state='ready';state.cachedAt=Date.now();
 }catch(err){
  state.state='error';state.error=String(err?.message||err).slice(0,160);
 }finally{if(partnerNoticeStage===stage)renderJobs()}
}
function prebidWon(value){
 const n=Number(value);
 if(!Number.isFinite(n)||n<=0)return '예산 미기재';
 return n>=1e8?Number((n/1e8).toFixed(2)).toLocaleString('ko-KR')+'억 원':
  Math.round(n/10000).toLocaleString('ko-KR')+'만원';
}
function renderPrebidJobs(el){
 const stage=partnerNoticeStage,report=prebidCache[stage],name=stage==='plan'?'발주계획':'사전규격';
 const summary=document.getElementById('partnerSummary'),decision=document.getElementById('jobDecisionSummary');
 if(summary)summary.textContent='';
 if(decision)decision.textContent='';
 const more=document.getElementById('g2bMore');if(more)more.style.display='none';
 const filt=document.getElementById('jobVerdictFilter');if(filt)filt.hidden=true;
 const count=document.getElementById('partnerJobCount');
 const message=report.state==='loading'?'불러오는 중':report.state==='error'?'수집 확인 필요':report.state==='idle'?'조회 전':'';
 if(report.state!=='ready'){
  if(count)count.textContent='확인 중';
  const detail=/prebid_official_http_403/.test(report.error)?'공식 API 접근 거부(403) · 해당 서비스 활용승인 확인 필요':
   /prebid_official_http_429/.test(report.error)?'공식 API 요청 제한(429)':
   /prebid_daily_request_budget_exhausted/.test(report.error)?'오늘의 수집 한도 도달':
   report.error;
  el.innerHTML='<div class="emptycard">'+htmlEscape(name)+' · '+htmlEscape(message)+
   (report.state==='error'?' ('+htmlEscape(detail)+')':'')+
   ' <button type="button" id="prebidRetry" class="job-vf">다시 조회</button></div>';
  el.querySelector('#prebidRetry')?.addEventListener('click',()=>void loadPrebidJobs(stage,true));
  return;
 }
 const word=jobSearchNormalized(jobSearchText);
 let rows=report.items.filter(x=>partnerSwScope!=='build'||swBuildTitle(x));
 if(word)rows=rows.filter(x=>jobSearchNormalized([x.title,x.org,x.id].join(' ')).includes(word));
 rows.sort((a,b)=>String(b.posted||'').localeCompare(String(a.posted||'')));
 if(count)count.textContent=rows.length+'건';
 if(!rows.length){el.innerHTML='<div class="emptycard">'+htmlEscape(name)+' · 해당 조건의 저장된 SW 후보가 없습니다. ('+
  '전체 수집 '+report.total.toLocaleString('ko-KR')+'건)</div>';return}
 el.innerHTML=rows.slice(0,Math.max(20,Math.min(250,jobRenderLimit||40))).map(x=>{
  const url=String(x.url||'');
  const safe=/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(url)?url:'';
  const fileLinks=(x.files||[]).filter(y=>/^https:\/\/(?:www\.)?g2b\.go\.kr(?:\/|$)/i.test(y)).slice(0,4);
  return '<article class="card" data-prebid-id="'+htmlEscape(x.id)+'"><div class="cardtop">'+
   '<span class="tag">'+htmlEscape(name)+'</span><span class="tag">'+htmlEscape(x.kind==='servc'?'용역':'물품')+'</span></div>'+
   '<h3>'+htmlEscape(x.title||'(사업명 없음)')+'</h3>'+
   '<p>'+htmlEscape(x.org||'발주기관 미기재')+' · '+htmlEscape(x.posted||'등록일 미기재')+'</p>'+
   '<p><strong>'+htmlEscape(prebidWon(x.budget))+'</strong> · '+
   htmlEscape(stage==='plan'?'예정 '+(x.plannedMonth||'시기 미기재'):'의견마감 '+(x.opinionDeadline||'미기재'))+'</p>'+
   (safe?'<a href="'+htmlEscape(safe)+'" target="_blank" rel="noopener noreferrer">원문 보기</a>':
   '<span class="tag">등록번호 '+htmlEscape(x.id||'미기재')+'</span>')+
   (fileLinks.length?' · '+fileLinks.map((url,i)=>'<a href="'+htmlEscape(url)+'" target="_blank" rel="noopener noreferrer">규격서 '+(i+1)+'</a>').join(' · '):'')+
   (x.bidLinked?' <span class="tag">입찰공고 연결됨</span>':'')+'</article>';
 }).join('');
}
