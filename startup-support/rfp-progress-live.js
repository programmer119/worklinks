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
   '<div class="rfp-rescan-stage-track" role="progressbar" aria-label="'+title+' 완료" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">'+
   '<span style="width:0%"></span></div></div>';
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
   '<div class="rfp-rescan-section-header"><h3>기능별 판독 완료</h3></div>'+
   '<div class="rfp-rescan-feature-list">'+stageKeys.map(pair=>row(pair[0],pair[1])).join('')+'</div>'+
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
   failed:number(counts.failed),incomplete:number(counts.incomplete),pct:pct.toFixed(1)+'%'
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
  updateField(panel,'liveChange',delayed?'마지막 정상 집계 표시':
   activeParts.join(' · ')||(delta>0?'최근 판독 +'+number(delta)+'건':''));
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
   track.firstElementChild.style.width=progress.toFixed(2)+'%';
  }
  const unknownTotal=Math.max(0,Number(counts.unknownDeadline||0));
  panel.querySelector('#rfpRescanUnknown').hidden=!unknownTotal;
  updateField(panel,'unknown',number(unknownTotal)+'건 · 별도 판독 '+
   number(counts.unknownDeadlineCompleted)+' / '+number(unknownTotal)+'건');
  updateField(panel,'serverTime','서버 집계 '+rfpClock(info.asOf));
  updateField(panel,'lastRead','최근 확인 '+rfpClock(rfpRescanLastSuccessAt));
  count.textContent='완료 '+number(done)+' / '+number(all)+'건';
  label.textContent=pct.toFixed(1)+'%'+(delayed?' · 갱신 지연':'');
  fill.style.width=pct.toFixed(2)+'%';
  const next=document.getElementById('rfpRescanNext');
  if(next)next.textContent=delayed?'조회 오류':active?'작업 중':worker?.upgradeActive?'진행 확인 중':'현황';
  const launch=document.getElementById('rfpRescanLaunch');
  if(launch)launch.title='판독 완료 '+number(done)+' / '+number(all)+'건 · '+
   (active?'작업 진행 중':'서버 집계 '+rfpClock(info.asOf));
  window.paintRfpLiveCountdown();
 };
})();
