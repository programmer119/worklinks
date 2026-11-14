/* Server-backed RFP progress. Keep DOM mounted across 10s polls for smooth updates. */
(function(){
 'use strict';
 const laneKeys=[['manifest','첨부목록 확보'],['download','원본 다운로드'],['scan','문서 판독']];
 const stageKeys=[['classification','RFP 조건'],['roles','역할·인원'],['facts','인력 요구사항'],['hwpx','HWPX 해석']];
 function row(key,title){
  return '<div class="rfp-rescan-stage-row" data-rfp-stage="'+key+'">'+
   '<div class="rfp-rescan-stage-label"><span class="rfp-rescan-stage-name">'+title+'</span>'+
   '<span class="rfp-rescan-stage-right"><strong data-rfp-field="'+key+'Count">—</strong>'+
   '<span class="rfp-rescan-stage-note" data-rfp-field="'+key+'State">확인 중</span></span></div>'+
   '<div class="rfp-rescan-stage-track" role="progressbar" aria-label="'+title+' 전체 완료" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">'+
   '<span class="rfp-stage-file-fill" style="width:0%"></span>'+
   '<span class="rfp-stage-aggregate-fill" style="width:0%"></span>'+
   '<span class="rfp-stage-focus"><span class="rfp-stage-focus-name">작업 정보 확인 중</span>'+
   '<span class="rfp-stage-focus-metric"></span></span></div></div>';
 }
 function mount(panel){
  panel.innerHTML=
   '<div class="rfp-rescan-livebar" role="status" aria-live="polite" aria-atomic="true">'+
    '<span class="rfp-rescan-live-indicator" aria-hidden="true"></span>'+
    '<strong data-rfp-field="liveText">서버 상태 확인 중</strong>'+
    '<span class="rfp-rescan-live-change" data-rfp-field="liveChange"></span>'+
    '<span class="rfp-rescan-live-spacer"></span>'+
    '<span class="rfp-rescan-poll" id="rfpRescanModalRefresh">조회 중…</span></div>'+
   '<div class="rfp-rescan-totals">'+
    '<div class="rfp-rescan-metric"><span>관리 대상</span><strong data-rfp-field="total">—</strong></div>'+
    '<div class="rfp-rescan-metric"><span>최신 판독 완료</span><strong data-rfp-field="complete">—</strong></div>'+
    '<div class="rfp-rescan-metric"><span>재판독 필요</span><strong data-rfp-field="rescanRequired">—</strong></div></div>'+
   '<div class="rfp-rescan-overview"><span>전체 판독 완료</span><strong data-rfp-field="pct">—</strong></div>'+
   '<div class="rfp-rescan-big-track" role="progressbar" aria-label="전체 최신 판독 완료" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"><span style="width:0%"></span></div>'+
   '<div class="rfp-rescan-breakdown"><span>최초 미판독 <b data-rfp-field="unscanned">—</b></span>'+
    '<span>구버전 <b data-rfp-field="legacy">—</b></span>'+
    '<span>실패 <b data-rfp-field="failed">—</b></span>'+
    '<span>검증 미완료 <b data-rfp-field="incomplete">—</b></span></div>'+
   '<div class="rfp-rescan-section-header"><h3>작업 진행</h3>'+
    '<span>첨부목록 확보·원본 다운로드 → 별도 문서 판독</span></div>'+
   '<div class="rfp-rescan-lanes">'+laneKeys.map(pair=>row(pair[0],pair[1])).join('')+'</div>'+
   '<details class="rfp-rescan-features"><summary>기능별 판독 상세</summary>'+
   '<div class="rfp-rescan-feature-list">'+stageKeys.map(pair=>row(pair[0],pair[1])).join('')+'</div></details>'+
   '<div class="rfp-rescan-unknown" id="rfpRescanUnknown" hidden>'+
    '<strong>마감일 미제공</strong> <span data-rfp-field="unknown"></span></div>'+
   '<div class="rfp-rescan-bottomline"><span data-rfp-field="serverTime">서버 집계 —</span>'+
    '<span data-rfp-field="lastRead">최근 확인 —</span>'+
    '<button type="button" class="rfp-rescan-refresh-now" id="rfpRescanRefreshNow">↻ 지금 조회</button></div>';
  panel.dataset.ready='1';
  panel.querySelector('#rfpRescanRefreshNow').addEventListener('click',()=>void refreshRfpRescanProgress(true));
 }
 function updateField(panel,name,value){
  const el=panel.querySelector('[data-rfp-field="'+name+'"]');
  if(el)el.textContent=String(value);
 }
 window.paintRfpLiveCountdown=function(){
  const node=document.getElementById('rfpRescanModalRefresh');
  if(node){
   const waiting=Math.max(0,rfpRescanNextReadAt-Date.now());
   node.textContent=rfpRescanBusy?'조회 중…':'다음 조회 '+Math.ceil(waiting/1000)+'초';
  }
  const button=document.getElementById('rfpRescanRefreshNow');
  if(button)button.disabled=Boolean(rfpRescanBusy);
  if(typeof window.paintRfpLaneFocus==='function')window.paintRfpLaneFocus();
 };



 function formatRfpError(raw){
  const value=String(raw||'');
  if(/not present in verified date batch|not_present_in_complete_date_batch/.test(value))
   return '검증된 날짜별 목록에 해당 공고가 없음';
  if(/quota|rate.limit|429|upstream_result_22|upstream_result_23/i.test(value))
   return '공식 API 호출 제한';
  if(/complete_bulk_manifest_missing|manifest_not_confirmed|official page incomplete/i.test(value))
   return '첨부목록 확보 미완료';
  if(/cached_original_missing/.test(value))return '보관된 원본 파일 누락';
  if(/503|502|timeout|connection/i.test(value))return '연결 오류';
  return value.slice(0,100);
 }
 function retryRfpText(epoch,now){
  const seconds=Math.max(0,Math.ceil(Number(epoch||0)-now));
  if(!epoch)return '재시도 시각 미제공';
  if(seconds===0)return '재시도 시각 도달';
  if(seconds>=3600)return '재시도 '+Math.floor(seconds/3600)+'시간 '+Math.ceil((seconds%3600)/60)+'분 후';
  if(seconds>=60)return '재시도 '+Math.floor(seconds/60)+'분 '+seconds%60+'초 후';
  return '재시도 '+seconds+'초 후';
 }
 function updateRfpText(el,value){
  if(el&&el.textContent!==value)el.textContent=value;
 }
 window.paintRfpLaneFocus=function(){
  const panel=document.getElementById('rfpRescanContent');
  if(!panel||panel.dataset.ready!=='1')return;
  const info=rfpRescanProgress,activity=info?.activity;
  const now=Date.now()/1000,stale=Boolean(rfpRescanProgressError);
  const fmt=n=>(Math.max(0,Number(n)||0)/1048576).toFixed(2)+'MB';
  for(const [key] of laneKeys){
   const node=panel.querySelector('[data-rfp-stage="'+key+'"]');
   if(!node)continue;
   const track=node.querySelector('.rfp-rescan-stage-track');
   const label=track.querySelector('.rfp-stage-focus-name');
   const metric=track.querySelector('.rfp-stage-focus-metric');
   const fileFill=track.querySelector('.rfp-stage-file-fill');
   const state=node.querySelector('[data-rfp-field="'+key+'State"]');
   const lane=info?.lanes?.[key];
   const worker=activity?.workers?.[key];
   const allItems=activity?.available&&Array.isArray(activity.items)
    ?activity.items.filter(x=>x.lane===key):[];
   const working=allItems.filter(x=>x.status==='working'&&now-Number(x.updatedEpoch||0)<=90);
   const broken=allItems.filter(x=>x.status==='retry');
   const recent=allItems.filter(x=>x.status==='done'&&now-Number(x.updatedEpoch||0)<=30);
   const choices=working.length?[...working.slice(0,8),...broken.slice(0,2)]
    :broken.length?broken.slice(0,5):recent.slice(0,3);
   const selected=choices.length?choices[Math.floor(Date.now()/4000)%choices.length]:null;
   const active=Math.max(0,Number(lane?.active||0));
   const failed=Math.max(0,Number(lane?.failed||0));
   const problems=Math.max(failed,broken.length);
   let badge=active?'진행 '+active+'건':problems?'재시도 '+problems+'건':'';
   if(active&&problems)badge+=' · 오류 '+problems+'건';
   if(worker?.status==='retry'&&Number(worker.retryEpoch)>now)
    badge=retryRfpText(worker.retryEpoch,now);
   else if(worker?.stale&&active===0)badge='상태 갱신 끊김';
   else if(stale)badge='집계 갱신 지연';
   else if(!badge&&Number(lane?.done)>=Number(lane?.total)&&lane?.total>0)badge='완료';
   else if(!badge&&key==='manifest')badge='순차 확보';
   else if(!badge)badge='진행 확인 중';
   updateRfpText(state,badge);
   node.classList.toggle('has-rfp-error',Boolean(worker?.status==='retry'||worker?.stale||problems||stale));
   let name='현재 처리 파일 없음',detail='';
   const bits=[];
   if(selected){
    name=selected.fileName||selected.noticeKey||'공고';
    if(selected.phase)bits.push(selected.phase);
    if(selected.filesTotal>0&&key!=='manifest')bits.push('파일 '+selected.filesDone+'/'+selected.filesTotal);
    if(selected.bytesDone>0||selected.bytesTotal>0)
     bits.push(fmt(selected.bytesDone)+' / '+(selected.bytesTotal>0?fmt(selected.bytesTotal):'총용량 미제공'));
    if(selected.status==='retry'){
     if(selected.error)bits.push(formatRfpError(selected.error));
     if(selected.retryEpoch)bits.push(retryRfpText(selected.retryEpoch,now));
    }
   }else if(worker?.status==='retry'){
    name='작업 일시 중단';
    if(worker.error)bits.push(formatRfpError(worker.error));
    bits.push(retryRfpText(worker.retryEpoch,now));
   }else if(worker?.stale){
    name='서버 작업 기록 갱신 끊김';
   }else if(!activity?.available){
    name='실시간 파일 정보 연결 확인 필요';
   }else if(active>0){
    name='진행 중 · 파일별 정보 갱신 확인 필요';
   }
   if(selected&&choices.length>1)bits.push((choices.indexOf(selected)+1)+'/'+choices.length);
   detail=bits.join(' · ');
   const filePct=selected?.bytesTotal>0?
    Math.max(0,Math.min(100,100*Number(selected.bytesDone||0)/Number(selected.bytesTotal))):0;
   const width=filePct.toFixed(1)+'%';
   if(fileFill.style.width!==width)fileFill.style.width=width;
   updateRfpText(label,name);
   updateRfpText(metric,detail);
   const tooltip=[name,detail,worker?.error?'작업 오류: '+formatRfpError(worker.error):'']
     .filter(Boolean).join(' · ');
   if(track.title!==tooltip)track.title=tooltip;
  }
 };

 window.paintRfpLiveProgress=function(){
  const label=document.getElementById('rfpRescanLabel');
  const count=document.getElementById('rfpRescanCount');
  const fill=document.getElementById('rfpRescanMiniFill');
  const panel=document.getElementById('rfpRescanContent');
  if(!label||!count||!fill||!panel)return;
  const info=rfpRescanProgress;
  if(!info||!info.counts||!Number.isFinite(Number(info.counts.total))){
   label.textContent='—%';count.textContent='판독 현황 조회 불가';fill.style.width='0%';
   if(panel.dataset.ready!=='error'){
    panel.dataset.ready='error';
    panel.innerHTML='<div class="rfp-rescan-service-error"><strong>운영 집계 연결 오류</strong><p>서버에서 진행 건수를 받지 못했습니다.</p>'+
     '<button type="button" id="rfpRescanRetry" class="rfp-rescan-retry">다시 조회</button></div>';
    panel.querySelector('#rfpRescanRetry').addEventListener('click',()=>void refreshRfpRescanProgress(true));
   }
   window.paintRfpLiveCountdown();
   return;
  }
  if(panel.dataset.ready!=='1')mount(panel);
  const counts=info.counts;
  const all=Math.max(0,Number(counts.total||0));
  const done=Math.max(0,Number(counts.completed||0));
  const pct=all?Math.max(0,Math.min(100,100*done/all)):0;
  const number=rfpProgressNumber;
  const delayed=Boolean(rfpRescanProgressError);
  const lanes=info.lanes?.available===true?info.lanes:null;
  const worker=info.worker?.available===true?info.worker:null;
  const upgrade=worker?.tasks?.rfpUpgrade||null;
  const scanWorkerActive=Boolean(worker?.upgradeActive&&upgrade?.status==='started');
  const dlActive=Math.max(0,Number(lanes?.download?.active||0));
  const scanActive=Math.max(0,Number(lanes?.scan?.active||0));
  const active=!delayed&&(dlActive>0||scanActive>0||scanWorkerActive);
  for(const [name,value] of Object.entries({
   total:number(all),complete:number(done),rescanRequired:number(counts.rescanRequired),
   unscanned:number(counts.unscanned),legacy:number(counts.legacy),
   failed:number(counts.failed),incomplete:number(counts.incomplete),pct:pct.toFixed(2)+'%'
  }))updateField(panel,name,value);
  const totalBar=panel.querySelector('.rfp-rescan-big-track');
  totalBar.setAttribute('aria-valuenow',pct.toFixed(1));
  totalBar.firstElementChild.style.width=pct.toFixed(2)+'%';
  const live=panel.querySelector('.rfp-rescan-livebar');
  live.classList.toggle('is-active',active);
  live.classList.toggle('is-stale',delayed);
  updateField(panel,'liveText',delayed?'서버 집계 갱신 지연':
   active?'실제 작업 진행 중':worker?.upgradeActive?'판독 작업 확인 중':'현재 처리 중인 공고 없음');
  const activeParts=[];
  if(dlActive)activeParts.push('다운로드 '+number(dlActive)+'건');
  if(scanActive)activeParts.push('판독 '+number(scanActive)+'건');
  if(scanWorkerActive&&!scanActive)activeParts.push('판독 배치 실행');
  const delta=Number(rfpRescanLastDelta||0);
  if(delta>0)activeParts.push('최근 판독 +'+number(delta)+'건');
  updateField(panel,'liveChange',delayed?'마지막 정상 집계 표시':activeParts.join(' · '));
  for(const [key,name] of laneKeys.concat(stageKeys)){
   const node=panel.querySelector('[data-rfp-stage="'+key+'"]');
   if(!node)continue;
   const stage=key==='manifest'||key==='download'||key==='scan'?lanes?.[key]:info.stages?.[key];
   const available=stage&&Number.isFinite(Number(stage.total));
   const total=available?Math.max(0,Number(stage.total)):0;
   const completed=available?Math.max(0,Math.min(total,Number(stage.done||0))):0;
   const progress=total?Math.max(0,Math.min(100,100*completed/total)):0;
   const stageActive=Boolean(!delayed&&available&&
    ((key==='download'&&Number(stage.active||0)>0)||
     (key==='scan'&&(Number(stage.active||0)>0||scanWorkerActive))));
   let state=available?(total?progress.toFixed(1)+'%':'해당 없음'):'집계 미제공';
   if(stageActive)state='진행 중'+(Number(stage.active||0)>0?' '+number(stage.active)+'건':'');
   else if(available&&total&&completed===total)state='완료';
   else if(key==='manifest'&&available&&total&&completed<total)state='순차 확보';
   updateField(panel,key+'Count',available?number(completed)+' / '+number(total)+'건':'—');
   updateField(panel,key+'State',state);
   node.classList.toggle('is-active',stageActive);
   const track=node.querySelector('.rfp-rescan-stage-track');
   track.classList.toggle('is-active',stageActive);
   track.setAttribute('aria-valuenow',progress.toFixed(1));
   track.querySelector('.rfp-stage-aggregate-fill').style.width=progress.toFixed(2)+'%';
  }
  const unknownTotal=Math.max(0,Number(counts.unknownDeadline||0));
  panel.querySelector('#rfpRescanUnknown').hidden=!unknownTotal;
  updateField(panel,'unknown',number(unknownTotal)+'건 · 별도 판독 '+
   number(counts.unknownDeadlineCompleted)+' / '+number(unknownTotal)+'건');
  window.paintRfpLaneFocus();
  updateField(panel,'serverTime','서버 집계 '+rfpClock(info.asOf));
  updateField(panel,'lastRead','최근 확인 '+rfpClock(rfpRescanLastSuccessAt));
  count.textContent='완료 '+number(done)+' / '+number(all)+'건';
  label.textContent=pct.toFixed(2)+'%'+(delayed?' · 갱신 지연':'');
  fill.style.width=pct.toFixed(2)+'%';
  const next=document.getElementById('rfpRescanNext');
  if(next)next.textContent=delayed?'조회 오류':active?'작업 중':worker?.upgradeActive?'진행 확인 중':'현황';
  const launch=document.getElementById('rfpRescanLaunch');
  if(launch)launch.title='판독 완료 '+number(done)+' / '+number(all)+'건 · '+
   (active?'작업 진행 중':'서버 집계 '+rfpClock(info.asOf));
  window.paintRfpLiveCountdown();
 };

})();
