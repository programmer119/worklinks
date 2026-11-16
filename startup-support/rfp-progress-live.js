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
    '<div class="rfp-rescan-metric"><span>판독 대상</span><strong data-rfp-field="total">—</strong></div>'+
    '<div class="rfp-rescan-metric"><span>최신 판독 완료</span><strong data-rfp-field="complete">—</strong></div>'+
    '<div class="rfp-rescan-metric"><span>남은 문서 판독</span><strong data-rfp-field="rescanRequired">—</strong></div></div>'+
   '<div class="rfp-rescan-overview"><span>판독 대상 중 완료</span><strong data-rfp-field="pct">—</strong></div>'+
   '<div class="rfp-rescan-big-track" role="progressbar" aria-label="전체 최신 판독 완료" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"><span style="width:0%"></span></div>'+
   '<div class="rfp-rescan-breakdown"><span>최초 미판독 <b data-rfp-field="unscanned">—</b></span>'+
    '<span>구버전 <b data-rfp-field="legacy">—</b></span>'+
    '<span>실패 <b data-rfp-field="failed">—</b></span>'+
    '<span>검증 미완료 <b data-rfp-field="incomplete">—</b></span></div>'+ 
    '<details class="rfp-rescan-excluded-detail"><summary>집계 상세</summary><span>전체 관리 공고 <b data-rfp-field="allNotices">—</b>건 · 판독 제외 <b data-rfp-field="excluded">—</b>건</span></details>'+
   '<div class="rfp-rescan-section-header"><h3>작업 진행</h3>'+
    '<span>첨부목록 확보·원본 다운로드 → 별도 문서 판독</span></div>'+
   '<div class="rfp-rescan-lanes">'+laneKeys.map(pair=>row(pair[0],pair[1])).join('')+'</div>'+
   '<div id="rfpDownloadErrorDetails" class="rfp-download-error-details" hidden></div>'+
   '<details class="rfp-rescan-features"><summary>기능별 판독 상세</summary>'+
   '<div class="rfp-rescan-feature-list">'+stageKeys.map(pair=>row(pair[0],pair[1])).join('')+'</div></details>'+
   '<div class="rfp-rescan-unknown" id="rfpRescanUnknown" hidden>'+
    '<strong>마감일 미제공</strong> <span data-rfp-field="unknown"></span></div>'+
   '<div class="rfp-rescan-bottomline"><span data-rfp-field="serverTime">서버 집계 —</span>'+
    '<span data-rfp-field="lastRead">최근 확인 —</span>'+
    '<button type="button" class="rfp-rescan-refresh-now" id="rfpRescanRefreshNow">↻ 지금 조회</button></div>';
  panel.dataset.ready='1';
  panel.querySelector('#rfpRescanRefreshNow').addEventListener('click',()=>void refreshRfpRescanProgress(true));
  panel.addEventListener('click',event=>{
   if(event.target?.id!=='rfpDownloadErrorButton')return;
   const root=panel.querySelector('#rfpDownloadErrorDetails');
   if(!root)return;
   if(!root.hidden){root.hidden=true;return;}
   const records=rfpRescanProgress?.lanes?.download?.errorDetails||[];
   root.replaceChildren();
   const heading=document.createElement('strong');
   heading.textContent='원본 조회 불가 확정';
   root.append(heading);
   for(const entry of records){
    for(const file of (entry.files||[])){
     const line=document.createElement('div');
     line.textContent=entry.noticeKey+' · '+(file.name||'파일명 미제공')+
       ' · HTTP '+(file.httpStatus||'—')+' · '+formatRfpError(file.reason);
     root.append(line);
    }
   }
   if(!records.length)root.append('오류 상세는 서버에서 확인할 수 없습니다.');
   root.hidden=false;
  });
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
  if(/official_attachment_reference_missing_422|official_missing_reference_422/.test(value))
   return '공식 원본 참조번호 조회 불가 (422)';
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
 function elapsedRfp(seconds){
  const value=Math.max(0,Math.floor(seconds||0));
  const pad=n=>String(n).padStart(2,'0');
  if(value>=3600)return pad(Math.floor(value/3600))+':'+pad(Math.floor(value/60)%60)+':'+pad(value%60);
  return pad(Math.floor(value/60))+':'+pad(value%60);
 }
 function updateRfpText(el,value){
  if(el&&el.textContent!==value)el.textContent=value;
 }
 window.paintRfpLaneFocus=function(){
  const panel=document.getElementById('rfpRescanContent');
  if(!panel||panel.dataset.ready!=='1')return;
  const info=rfpRescanProgress,activity=info?.activity;
  const now=Date.now()/1000,stale=Boolean(rfpRescanProgressError);
  const number=rfpProgressNumber;
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
   // A verified manifest is complete even if its original download is pending.
   if(key==='manifest'&&Number(lane?.total)>0&&Number(lane?.done)>=Number(lane.total)){
    updateRfpText(state,'확보 완료');
    updateRfpText(label,'첨부목록 전부 확보 · 원본 다운로드는 별도 진행');
    updateRfpText(metric,'');
    fileFill.style.width='0%';
    node.classList.remove('has-rfp-error','has-rfp-confirmed-error');
    track.title='첨부목록 확보 100% · 다운로드·판독 작업과 별도';
    continue;
   }
   // Exact physical file transfers from the server, not the eight notice slots.
   if(key==='download'){
    const group=activity?.downloadGroup;
    const fmtBytes=n=>(Math.max(0,Number(n)||0)/1048576).toFixed(2)+'MB';
    const activeCount=group?.available?Number(group.activeCount||0):0;
    const files=Array.isArray(group?.files)?group.files:[];
    const main=activeCount?files[0]:null;
    const oldest=Number(group?.startedEpoch||0);
    const elapsed=main&&oldest>0?elapsedRfp(now-oldest):'';
    const errors=Array.isArray(group?.recentErrors)?group.recentErrors:[];
    const due=errors.find(e=>Number(e.retryEpoch||0)>now);
    const stalled=Number(group?.stalledCount||0);
    const hasFailure=Boolean(stalled||errors.length||worker?.status==='retry'||
                              (worker?.stale&&group?.available));
    const failed=Math.max(0,Number(lane?.failed||0));
    const confirmed=Math.max(0,Number(lane?.errors||0));
    const processed=Math.max(0,Number(lane?.processed||0));
    const total=Math.max(0,Number(lane?.total||0));
    const normal=Math.max(0,Number(lane?.done||0));
    const verifiedComplete=total>0&&normal===total&&confirmed===0;
    const detail=Array.isArray(lane?.errorDetails)?lane.errorDetails:[];
    const note=errors[0];
    let caption='현재 전송 파일 없음',description='',
        badge=activeCount?activeCount+'개 전송 중':'진행 확인 중';
    const infoBits=[];
    if(!group?.available){
     caption='파일별 다운로드 상태 미제공';
     badge='집계 확인 필요';
     description='서버 파일 전송 정보 연결 확인 필요';
    }else if(main){
     caption=(main.name||main.noticeKey||'공식 첨부파일')+
       (activeCount>1?' 외 '+(activeCount-1)+'개':'');
     if(main.bytesTotal>0||main.bytesDone>0)
      infoBits.push(fmtBytes(main.bytesDone)+' / '+
        (main.bytesTotal>0?fmtBytes(main.bytesTotal):'총용량 미제공'));
     infoBits.push('다운로드 중 '+elapsed);
     if(stalled){
      badge='전송 정체 '+stalled+'개';
      infoBits.unshift('전송 정체 '+Number(group.oldestStallSeconds||0)+'초');
     }
     // The progress track shows only active transfers; errors live in the header.
     description=infoBits.join(' · ');
    }else if(due||worker?.status==='retry'){
     caption='다운로드 오류 · 자동 재시도';
     badge='재시도 예정';
     if(note?.reason||worker?.error)
      infoBits.push(formatRfpError(note?.reason||worker?.error));
     infoBits.push(retryRfpText(due?.retryEpoch||worker?.retryEpoch,now));
     description=infoBits.join(' · ');
    }else if(worker?.stale){
     caption='서버 전송 상태 갱신 끊김';
     badge='작업 상태 확인 필요';
    }else if(confirmed>0&&processed===total&&total>0){
     caption='현재 전송 파일 없음';
     badge='원본 오류 '+confirmed+'건';
    }else if(confirmed>0){
     caption='현재 전송 파일 없음';
     badge='원본 오류 '+confirmed+'건 · 다음 파일 준비';
    }else if(failed>0&&errors.length){
     caption='파일 다운로드 오류';
     badge='재시도 '+failed+'건';
     description=formatRfpError(note.reason);
    }else if(Number(lane?.done||0)>=Number(lane?.total||0)&&Number(lane?.total||0)>0){
     caption='모든 원본 다운로드 완료';badge='완료';
    }else{
     caption='현재 전송 파일 없음';
     badge=failed>0?'재시도 대상 '+failed+'건':'다음 다운로드 준비 중';
    }
    // Confirmed failures outrank scheduled retries, regardless of whether
    // the worker is currently online. Only 100% successful work can say complete.
    if(confirmed>0)badge='원본 오류 '+confirmed+'건';
    if(verifiedComplete){
     caption='모든 원본 정상 다운로드 완료';
     badge='정상 완료';
     description='';
    }
    if(stale&&group?.available)badge='집계 갱신 지연';
    updateRfpText(state,badge);
    if(main){
     // Separate count from long filename so "외 N개" cannot be ellipsized.
     const fileName=main.name||main.noticeKey||'공식 첨부파일';
     const more=activeCount>1?'외 '+(activeCount-1)+'개':'';
     if(label.dataset.activeFile!==fileName||label.dataset.moreFiles!==more){
      label.dataset.activeFile=fileName;
      label.dataset.moreFiles=more;
      const filename=document.createElement('span');
      filename.className='rfp-download-current-name';
      filename.textContent=fileName;
      label.replaceChildren(filename);
      if(more){
       const extra=document.createElement('span');
       extra.className='rfp-download-more-count';
       extra.textContent=more;
       label.append(extra);
      }
     }
    }else{
     delete label.dataset.activeFile;
     delete label.dataset.moreFiles;
     updateRfpText(label,caption);
    }
    updateRfpText(metric,description);
    const filePct=main?.bytesTotal>0?
      Math.max(0,Math.min(100,100*Number(main.bytesDone||0)/Number(main.bytesTotal))):0;
    const width=filePct.toFixed(1)+'%';
    if(fileFill.style.width!==width)fileFill.style.width=width;
    node.classList.toggle('has-rfp-error',!verifiedComplete&&((!main&&hasFailure)||stale));
    node.classList.remove('has-rfp-confirmed-error');
    const tooltipFiles=files.map(x=>(x.name||x.noticeKey||'공식 첨부파일')+' '+fmtBytes(x.bytesDone)+
      (x.bytesTotal>0?'/'+fmtBytes(x.bytesTotal):'')).join('\n');
    const tooltip=[caption,description,tooltipFiles].filter(Boolean).join('\n');
    if(track.title!==tooltip)track.title=tooltip;
    continue;
   }
   const allItems=activity?.available&&Array.isArray(activity.items)
    ?activity.items.filter(x=>x.lane===key):[];
   const working=allItems.filter(x=>x.status==='working'&&now-Number(x.updatedEpoch||0)<=90);
   const broken=allItems.filter(x=>x.status==='retry');
   const recent=allItems.filter(x=>x.status==='done'&&now-Number(x.updatedEpoch||0)<=30);
   const choices=working.length?[...working.slice(0,8),...broken.slice(0,2)]
    :broken.length?broken.slice(0,5):recent.slice(0,3);
   // Never rotate fake 'progress' by the clock. Show one real, latest
   // server-reported file and change it only when the server data changes.
   const selected=choices.length?choices[0]:null;
   const active=Math.max(0,Number(lane?.active||0));
   const failed=Math.max(0,Number(lane?.failed||0));
   const problems=Math.max(failed,broken.length);
   // The source queue may be temporarily empty while the pipeline is alive.
   // A silent file heartbeat in this state is NOT a disconnected server.
   const upstreamScan=String(info?.worker?.tasks?.rfpUpgrade?.status||'');
   const waitingForOriginal=key==='scan'&&info?.worker?.upgradeActive===true&&
     upstreamScan==='waiting_for_download';
   const waitingForEligibility=key==='scan'&&info?.worker?.upgradeActive===true&&
     upstreamScan==='no_eligible_now';
   // A production scan source-repair hold is authoritative even when the
   // scheduler's optional upgradeActive flag is absent or stale.
   const waitingForRepair=key==='scan'&&
     upstreamScan==='waiting_for_source_repair';
   const waitingForSource=key==='scan'&&info?.worker?.upgradeActive===true&&
     upstreamScan==='waiting_for_source';
   const ocrTask=info?.worker?.tasks?.rfpOpenRepair;
   const recentOcrRepair=key==='scan'&&info?.worker?.upgradeActive===true&&
     ocrTask?.status==='started'&&Number(ocrTask.attemptEpoch)>0&&
     now-Number(ocrTask.attemptEpoch)<600;
   let badge=active?(key==='scan'?'판독 시도 '+active+'건':'진행 '+active+'건'):
      problems?'재시도 '+problems+'건':'';
   if(active&&problems)badge+=' · 오류 '+problems+'건';
   if(waitingForRepair)badge='원본 판독 오류 · 복구 필요';
   else if(waitingForSource)badge='공식 원본 미확보 · 확인 필요';
   else if(waitingForOriginal)badge=recentOcrRepair?'원본 대기 · OCR 복구 중':'원본 다운로드 대기';
   else if(waitingForEligibility)badge='판독 가능한 원본 확인 중';
   else if(recentOcrRepair)badge='OCR 복구 시도 중';
   else if(worker?.status==='retry'&&Number(worker.retryEpoch)>now)
    badge=retryRfpText(worker.retryEpoch,now);
   else if(worker?.stale&&active===0)badge='상태 갱신 끊김';
   else if(stale)badge='집계 갱신 지연';
   else if(!badge&&Number(lane?.done)>=Number(lane?.total)&&lane?.total>0)badge='완료';
   else if(!badge&&key==='manifest')badge='순차 확보';
   else if(!badge)badge='진행 확인 중';
   if(key==='scan'&&Number(lane?.blockedNoAttachments||0)>0)
    badge+=' · 판독 제외 '+Number(lane.blockedNoAttachments)+'건';
   updateRfpText(state,badge);
   node.classList.toggle('has-rfp-error',Boolean(
     (worker?.status==='retry'&&!waitingForOriginal&&!waitingForEligibility&&!waitingForRepair&&!waitingForSource&&!recentOcrRepair)||
     (worker?.stale&&!waitingForOriginal&&!waitingForEligibility&&!waitingForRepair&&!waitingForSource&&!recentOcrRepair)||problems||stale));
   let name='현재 처리 파일 없음',detail='';
   const bits=[];
   if(waitingForRepair){
    name='원본 판독 실패 · 수정 또는 재검사 필요';
    if(failed>0)bits.push('재판독 필요 '+number(failed)+'건');
    // A held scan is never a completed action or a fake current file.
   }else if(waitingForSource){
    name='공식 원본이 확인되지 않아 판독할 수 없음';
    if(Number(lane?.blockedNoAttachments||0)>0)
     bits.push('원본 미확보 '+number(Number(lane.blockedNoAttachments))+'건');
   }else if(waitingForOriginal){
    name=recentOcrRepair?'원본 대기 · OCR 복구 실행 중':'원본 다운로드 완료 대기';
    const dl=info?.lanes?.download;
    if(dl?.total>0)bits.push('미확보 '+number(Math.max(0,Number(dl.total)-Number(dl.done||0)))+'건');
    if(failed>0)bits.push('재판독 오류 '+number(failed)+'건');
   }else if(waitingForEligibility){
    name='현재 바로 판독 가능한 공고 없음';
    if(failed>0)bits.push('재판독 오류 '+number(failed)+'건');
   }else if(recentOcrRepair){
    name='저장 원본 OCR 복구 실행 중';
    if(failed>0)bits.push('재판독 오류 '+number(failed)+'건');
   }else if(selected){
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
   }else if(key==='manifest'&&Number(lane?.total)>0){
    name='첨부목록 미확보 '+number(Math.max(0,Number(lane.total)-Number(lane.done||0)))+'건 · 공식 목록 재확인 필요';
   }else if(active>0){
    name='진행 상태 확인 필요 · 세부 작업 정보 미제공';
   }
   if(key==='scan'&&Number(lane?.notQueued||0)>0)
    bits.push('작업 큐 미편입 '+Number(lane.notQueued)+'건');
   // No '1/8' carousel counter: that was just a display index, not work.
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
  const excluded=Math.max(0,Number(counts.excluded||0));
  const eligible=Math.max(0,Number(counts.eligible??Math.max(0,all-excluded)));
  const pct=eligible?Math.max(0,Math.min(100,100*done/eligible)):0;
  const number=rfpProgressNumber;
  const delayed=Boolean(rfpRescanProgressError);
  const lanes=info.lanes?.available===true?info.lanes:null;
  const worker=info.worker?.available===true?info.worker:null;
  const upgrade=worker?.tasks?.rfpUpgrade||null;
  const scanWorkerActive=Boolean(worker?.upgradeActive&&upgrade?.status==='started');
  const dlNotices=Math.max(0,Number(lanes?.download?.active||0));
  const downloadGroup=info.activity?.downloadGroup;
  const dlFiles=downloadGroup?.available?Math.max(0,Number(downloadGroup.activeCount||0)):null;
  const scanActive=Math.max(0,Number(lanes?.scan?.active||0));
  const active=!delayed&&(dlNotices>0||dlFiles>0||scanActive>0||scanWorkerActive);
  const noCompletionFor=Math.max(0,Math.floor((Date.now()-Number(rfpRescanLastChangeAt||Date.now()))/1000));
  const noNewCompletion=Boolean(!delayed&&(scanActive>0||scanWorkerActive)&&noCompletionFor>=30);
  for(const [name,value] of Object.entries({
   total:number(eligible),allNotices:number(all),complete:number(done),rescanRequired:number(Math.max(0,Number(counts.remaining??(eligible-done)))),
   excluded:number(excluded),unscanned:number(counts.unscanned),legacy:number(counts.legacy),
   failed:number(counts.failed),incomplete:number(counts.incomplete),pct:pct.toFixed(2)+'%'
  }))updateField(panel,name,value);
  const totalBar=panel.querySelector('.rfp-rescan-big-track');
  totalBar.setAttribute('aria-valuenow',pct.toFixed(1));
  totalBar.firstElementChild.style.width=pct.toFixed(2)+'%';
  const live=panel.querySelector('.rfp-rescan-livebar');
  // Do not pulse like successful progress when the server only retries failures.
  live.classList.toggle('is-active',active&&!noNewCompletion);
  live.classList.toggle('is-stale',delayed);
  updateField(panel,'liveText',delayed?'서버 집계 갱신 지연':
   noNewCompletion?'판독 시도 중 · 완료 증가 없음':
   active?'작업 실행 확인 · 완료 미확정':worker?.upgradeActive?'판독 작업 확인 중':'현재 처리 중인 공고 없음');
  const activeParts=[];
  if(dlFiles>0)activeParts.push('파일 다운로드 '+number(dlFiles)+'개');
  else if(dlNotices>0)activeParts.push('원본 준비 '+number(dlNotices)+'건');
  if(scanActive)activeParts.push('판독 시도 '+number(scanActive)+'건');
  if(noNewCompletion)activeParts.push('신규 완료 0건 · '+noCompletionFor+'초');
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
   const processed=key==='download'&&available?
     Math.max(completed,Math.min(total,Number(stage.processed??completed))):completed;
   const errors=key==='download'&&available?Math.max(0,Number(stage.errors||0)):0;
   const progress=total?Math.max(0,Math.min(100,100*processed/total)):0;
   // Files actually received are successful; confirmed missing originals are
   // a separate red segment. Never paint confirmed errors as blue success.
   const successProgress=key==='download'&&total?
     Math.max(0,Math.min(100,100*completed/total)):progress;
   const errorProgress=key==='download'&&total?
     Math.max(0,Math.min(100-successProgress,100*errors/total)):0;
   const stageActive=Boolean(!delayed&&available&&
    ((key==='download'&&Number(stage.active||0)>0)||
     (key==='scan'&&(Number(stage.active||0)>0||scanWorkerActive))));
   let state=available?(total?progress.toFixed(1)+'%':'해당 없음'):'집계 미제공';
   if(key==='download'&&errors>0)state='원본 오류 '+number(errors)+'건';
   else if(key==='manifest'&&available&&total&&completed===total)state='확보 완료';
   else if(stageActive)state=key==='scan'
    ?(noNewCompletion?'완료 증가 없음':'판독 시도 중'+(Number(stage.active||0)>0?' '+number(stage.active)+'건':''))
    :'진행 중'+(Number(stage.active||0)>0?' '+number(stage.active)+'건':'');
   else if(available&&total&&processed===total)state='처리 완료';
   else if(key==='download'&&errors)state='오류 '+number(errors)+'건';
   else if(key==='manifest'&&available&&total&&completed<total)state='순차 확보';
   if(key==='download'&&available){
    const countNode=node.querySelector('[data-rfp-field="downloadCount"]');
    if(countNode){
     const withoutFiles=Math.max(0,Math.min(completed,Number(stage.skipped||0)));
     const withOriginals=Math.max(0,completed-withoutFiles);
     const caption='확보 '+number(withOriginals)+' · 첨부없음 '+number(withoutFiles)+' · ';
     const suffix=' · 전체 '+number(total)+'건';
     const next=caption+'오류 '+number(errors)+'건'+suffix;
     if(countNode.dataset.value!==next){
      countNode.dataset.value=next;
      const success=document.createElement('span');
      success.className='rfp-download-success-count';
      success.textContent='확보 '+number(withOriginals);
      countNode.replaceChildren(success,document.createTextNode(' · 첨부없음 '+number(withoutFiles)+' · '));
      const button=document.createElement('button');
      button.id='rfpDownloadErrorButton';
      button.type='button';
      button.className='rfp-download-error-count';
      button.textContent='오류 '+number(errors)+'건';
      button.disabled=errors===0;
      button.title=errors?'확정된 원본 오류 상세 보기':'확정 오류 없음';
      countNode.append(button,document.createTextNode(suffix));
     }
    }
   }else updateField(panel,key+'Count',available?number(completed)+' / '+number(total)+'건':'—');
   updateField(panel,key+'State',state);
   node.classList.toggle('is-active',stageActive);
   const track=node.querySelector('.rfp-rescan-stage-track');
   track.classList.toggle('is-active',stageActive);
   track.setAttribute('aria-valuenow',progress.toFixed(1));
   track.querySelector('.rfp-stage-aggregate-fill').style.width=successProgress.toFixed(2)+'%';
   let errorBar=track.querySelector('.rfp-stage-error-fill');
   if(key==='download'&&!errorBar){
    errorBar=document.createElement('span');
    errorBar.className='rfp-stage-error-fill';
    errorBar.setAttribute('aria-hidden','true');
    track.append(errorBar);
   }
   if(errorBar){
    errorBar.style.left=successProgress.toFixed(2)+'%';
    errorBar.style.width=errorProgress>0?'max(4px, '+errorProgress.toFixed(2)+'%)':'0%';
   }
   const retry=Number(stage?.failed||0)>0;
   const status=delayed?'warning':
    (key==='download'&&errors>0)?'danger':
    stageActive?'active':
    available&&total>0&&completed===total?'success':
    retry?'warning':'neutral';
   node.dataset.status=status;
  }
  const unknownTotal=Math.max(0,Number(counts.unknownDeadline||0));
  const unknownBox=panel.querySelector('#rfpRescanUnknown');
  if(unknownBox)unknownBox.hidden=!unknownTotal;
  updateField(panel,'unknown',number(unknownTotal)+'건 · 별도 판독 '+
   number(counts.unknownDeadlineCompleted)+' / '+number(unknownTotal)+'건');
  window.paintRfpLaneFocus();
  // The focus renderer updates live text, but semantic status belongs to
  // the authoritative stage counters and is applied above on every poll.
  const allStages=[...laneKeys,...stageKeys];
  for(const [key] of allStages){
   const node=panel.querySelector('[data-rfp-stage="'+key+'"]');
   if(!node)continue;
   const state=node.querySelector('[data-rfp-field="'+key+'State"]');
   if(state&&node.dataset.status==='success'){
    if(key==='manifest')updateRfpText(state,'확보 완료');
    else if(key==='download')updateRfpText(state,'전체 정상 완료');
    else if(key==='scan')updateRfpText(state,'최신 판독 완료');
   }
  }
  const completeNotice=done===all&&all>0;
  totalBar.dataset.status=completeNotice?'success':'active';
  const mini=document.querySelector('#rfpRescanMiniFill');
  if(mini)mini.dataset.status=completeNotice?'success':'active';
  updateField(panel,'serverTime','서버 집계 '+rfpClock(info.asOf));
  updateField(panel,'lastRead','최근 확인 '+rfpClock(rfpRescanLastSuccessAt));
  count.textContent='완료 '+number(done)+' / '+number(eligible)+'건';
   count.title='관리 대상 '+number(all)+'건 · 판독 제외 '+number(excluded)+'건';
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
