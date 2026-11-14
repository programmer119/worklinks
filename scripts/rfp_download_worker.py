#!/usr/bin/env python3
"""Server123's dedicated RFP download process: no text extraction or scan waits.

In one persistent run it discovers the ENTIRE current unexpired backlog,
then fills the durable download queue with at most eight in-flight notices.
The independent scan process only consumes already-downloaded originals.
"""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request
import urllib.error

import refresh_worklinks_rfp as reader
from rfp_call_ledger import cache_key
from rfp_dual_queue import RfpDualQueue
import rfp_live_activity as live
from rfp_bulk_manifests import BulkManifestPlanner, BulkManifestQuota, BulkManifestError

DATA=Path(os.environ.get('G2B_PIPELINE_DATA','/app/data'))
SCRIPTS=Path(os.environ.get('G2B_PIPELINE_SCRIPTS','/app/scripts'))
SEEDS=DATA/'snapshots'
QUEUE=DATA/'rfp-dual-queue.sqlite3'
WORKERS=max(1,min(8,int(os.environ.get('WORKLINKS_RFP_DOWNLOAD_CONCURRENCY','8'))))
POLL_SECONDS=2
REFRESH_SECONDS=600
BULK_ENABLED=os.environ.get('WORKLINKS_RFP_BATCH_MANIFESTS')=='1'

class ProviderBackoff(RuntimeError):
    pass

class Pace:
    def __init__(self,interval=.25):
        self.interval=interval
        self.lock=threading.Lock()
        self.next=0
    def acquire(self):
        with self.lock:
            now=time.monotonic()
            start=max(now,self.next)
            self.next=start+self.interval
        if start>now:time.sleep(start-now)

META_PACE=Pace(0.8)
FILE_PACE=Pace(0.125)  # 8 file starts/sec for 8 independent download workers


def stream_original_to_verified_ledger(url,ledger,notice_key,closes_on,
                                       rate_gate=None,progress=None,on_retry=None):
    """Bounded-memory official GET -> temporary file -> verified compressed SQLite BLOB.

    The original is never held as a single Python bytes object. Previously
    verified archives are checked with incremental BLOB reads and reused.
    """
    reqkey=cache_key('official_attachment',url)
    reusable=ledger.verified_bytes_info(reqkey)
    if reusable is not None:
        ledger.link_attachment(reqkey,notice_key,closes_on)
        ledger.record('attachment_reuse',reqkey,'verified_bytes_reused',
                      notice_key=notice_key,response_sha256=reusable['sha256'])
        if progress:progress(reusable['bytes'],reusable['bytes'],True)
        return reusable
    request=urllib.request.Request(url,headers={
        'User-Agent':'Mozilla/5.0','Referer':'https://www.g2b.go.kr/'})
    for attempt in range(3):
        if rate_gate is not None:rate_gate.acquire()
        raw_path=None
        try:
            with reader.OPENER.open(request,timeout=35) as response:
                status=getattr(response,'status',200)
                raw_length=int(response.headers.get('Content-Length') or '0')
                if raw_length>reader.MAX_FILE:
                    raise ValueError('large_file: content_length='+str(raw_length))
                bytes_received=0
                digest=hashlib.sha256()
                last_progress=0.0
                with tempfile.NamedTemporaryFile(
                        dir=ledger.path.parent,prefix='.rfp-download-',
                        suffix='.part',delete=False) as original:
                    raw_path=Path(original.name)
                    if progress:progress(0,raw_length,False)
                    while True:
                        chunk=response.read(min(256*1024,reader.MAX_FILE+1-bytes_received))
                        if not chunk:break
                        bytes_received+=len(chunk)
                        if bytes_received>reader.MAX_FILE:
                            raise ValueError('large_file: received='+str(bytes_received))
                        digest.update(chunk)
                        original.write(chunk)
                        tick=time.monotonic()
                        if progress and (tick-last_progress>=0.4 or
                                (raw_length and bytes_received>=raw_length)):
                            progress(bytes_received,raw_length,False)
                            last_progress=tick
                if raw_length and bytes_received!=raw_length:
                    raise ValueError('download_length_mismatch')
            ledger.record('attachment_http',reqkey,'http_ok',
                          http_status=status,notice_key=notice_key,
                          response_sha256=digest.hexdigest(),
                          detail='bytes='+str(bytes_received))
            archived=ledger.save_file(reqkey,raw_path,max_bytes=reader.MAX_FILE,
                                      notice_key=notice_key,closes_on=closes_on)
            if (archived is None or archived['sha256']!=digest.hexdigest() or
                    archived['bytes']!=bytes_received):
                raise RuntimeError('original_archive_not_verified_or_storage_quota')
            if progress:progress(bytes_received,raw_length or bytes_received,True)
            return archived
        except (urllib.error.HTTPError,urllib.error.URLError,
                TimeoutError,ConnectionError,ValueError) as exc:
            ledger.record('attachment_http',reqkey,'http_failed',
                          notice_key=notice_key,
                          http_status=getattr(exc,'code',None),
                          error_class=type(exc).__name__,detail=str(exc)[:160])
            if isinstance(exc,urllib.error.HTTPError):
                if reader.official_missing_reference(exc):
                    raise reader.OfficialAttachmentReferenceMissing(
                        'official_attachment_reference_missing_422') from exc
                retry=exc.code in (429,500,502,503,504)
            else:
                retry=isinstance(exc,(TimeoutError,ConnectionError,urllib.error.URLError))
            if not retry or attempt==2:raise
            if on_retry:on_retry(exc,1.5*(attempt+1))
            time.sleep(1.5*(attempt+1))
        finally:
            if raw_path is not None:
                try:raw_path.unlink()
                except FileNotFoundError:pass
    raise RuntimeError('unexpected_original_download_retry_exhausted')

def configure_reader():
    # Reuse the current approved official-source client and file hash ledger.
    reader.ROOT=DATA
    reader.DEST=SEEDS/'rfp-clauses.json'
    reader.COVERAGE_DEST=SEEDS/'rfp-coverage-index.json'
    reader.CHANGCOM_SOURCE=SEEDS/'changcom-actionable.json'
    reader.CHANGCOM_BACKFILL60=SEEDS/'audits/changcom-rfp-backfill-60-20261110.json'
    reader.CHANGCOM_URGENT_RECOVERY=SEEDS/'audits/changcom-priority-rfp-recovery-20261111.json'

def reader_fingerprint():
    return ':'.join(str(x) for x in (reader.CLASSIFICATION_VERSION,
            reader.HWPX_READER_VERSION,reader.STAFFING_ROLE_SCAN_VERSION,
            reader.STAFFING_FACT_SCAN_VERSION))

def discover_all(queue):
    previous={}
    for path in (SEEDS/'rfp-coverage-index.json',SEEDS/'rfp-clauses.json'):
        try:
            obj=json.loads(path.read_text(encoding='utf-8')).get('byNotice') or {}
            previous.update(obj)
        except (OSError,ValueError,TypeError):pass
    # Explicit 'upgrade' selector already includes legacy + first-time open
    # notices. NO 8-bid limit here: the full backlog is made durable first.
    selected=reader.discover(100000,prior=previous,targets=set(),
                             manifest_probe_out=[],priority=set())
    # Direct/letter tenders often have no electronic close in A02/B1.
    # Preserve unknown dates in the dual queue; the existing bulk manifest
    # gate never falls back to one government API request per notice.
    selected=[(no,order,closes) for no,order,closes in selected]
    added=queue.enqueue(selected,reader_fingerprint())
    retired=queue.retire_expired()
    print('RFP_DUAL_QUEUE_DISCOVERY',json.dumps({
        'allEligible':len(selected),'new':added,'expiredRetired':retired,
        'queue':queue.stats()},separators=(',',':')),flush=True)
    return len(selected)

def detects_upstream_limit(text):
    raw=str(text).lower()
    return ('upstream_result_22' in raw or 'daily_quota' in raw or
            'limited_number_of_service_requests_exceeds_error' in raw or
            'upstream_result_23' in raw or 'upstream_http_429' in raw or
            'temporarily_rate_limited' in raw)

def source_retry_seconds(error):
    """Read local A02 gateway cooldown (zero official HTTP calls).

    The proxy already tracks exact remaining time of its circuit breaker.
    A past failure cannot justify an unrelated fixed one-hour sleep.
    """
    try:
        status=reader.fetch_json(reader.BASE+'upstream-rate-status')
        bids=(status.get('services') or {}).get('bids') or {}
        remaining=int(bids.get('cooldownRemainingSeconds') or 0)
        if remaining>0:
            return remaining+2
    except Exception:
        pass
    # A non-active local cooldown should be checked again soon; the durable
    # quota budget will still prevent excessive official calls.
    return 30 if detects_upstream_limit(str(error)) else 30

def download_one(queue,claim,halt):
    key,closes=claim
    bid,ordinal=key.split(':',1)
    live.record('download',key,phase='첨부파일 준비',status='working')
    active_file_key=''
    active_file_name=''
    active_files_done=0
    active_files_total=0
    if halt.is_set():
        queue.download_failed(key,'upstream_paused',retry_seconds=600)
        live.record('download',key,phase='공식 API 제한',status='retry',
                    retry_epoch=time.time()+600,error='upstream_paused')
        return False
    try:
        if BULK_ENABLED:
            # No per-bid official API in the bulk downloader, including
            # region information. The whole-day 3-source manifest is durable.
            meta=queue.bulk_manifest(key)
            if meta is None:
                raise RuntimeError('complete_bulk_manifest_missing')
        else:
            META_PACE.acquire()
            meta=reader.fetch_json(reader.BASE+'bid-evidence?'+urllib.parse.urlencode(
                {'bidNo':bid,'order':ordinal}))
        docs=meta.get('attachments') or {}
        errors=' '.join(str(x or '') for x in
          (docs.get('error'),(meta.get('noticeDocuments') or {}).get('error'),
           meta.get('error')))
        if detects_upstream_limit(errors):
            halt.set()
            raise ProviderBackoff(errors[:140])
        if docs.get('ok') is not True or docs.get('complete') is not True:
            raise ValueError('official_attachment_manifest_not_confirmed:'+errors[:80])
        manifest=(docs.get('items') or [])[:reader.MAX_DOCUMENTS]
        if not manifest:
            # A verified empty official list is a finished no-file notice,
            # not a scan failure and never eligible for scanner retry.
            queue.no_attachments(key,meta)
            live.record('download',key,phase='첨부파일 없음 · 정상 종료',
                        status='done',files_done=0,files_total=0)
            return True
        # No scanner or extractor is called anywhere in this process.
        seen=set()
        urls=[]
        for item in manifest:
            approved=reader.legal_file(item)
            if not approved:continue
            name,url=approved
            if url not in seen:seen.add(url);urls.append(url)
        if not urls:
            raise ValueError('nonempty_official_manifest_has_no_downloadable_url')
        verified_files=[]
        live.record('download',key,phase='파일 다운로드',status='working',files_total=len(urls))
        reader._NOTICE_CONTEXT.notice_key=key
        reader._NOTICE_CONTEXT.closes_on=closes
        ledger=reader.active_rfp_ledger()
        if ledger is None:raise RuntimeError('durable_binary_ledger_not_configured')
        for index,url in enumerate(urls):
            if halt.is_set():raise ProviderBackoff('provider_paused')
            active_files_done=index
            active_files_total=len(urls)
            # The approved download() reuses compressed originals by hash;
            # it only opens official HTTPS when the verified bytes are absent.
            file_name=next((approved[0] for item in manifest
                for approved in [reader.legal_file(item)]
                if approved and approved[1]==url),'공식 첨부파일')
            file_key=hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]
            active_file_key=file_key
            active_file_name=file_name
            last_network_error=''
            def progress(received,total,complete):
                live.record('download',key,file_key=file_key,file_name=file_name,
                    phase='원본 검증 중' if complete else '전송 중',
                    status='working',bytes_done=received,
                    bytes_total=total,files_done=index,
                    files_total=len(urls),error=last_network_error)
            def on_retry(error,seconds):
                nonlocal last_network_error
                last_network_error=type(error).__name__+': '+str(error)[:95]
                live.record('download',key,file_key=file_key,file_name=file_name,
                    phase='전송 오류 · 재연결 예정',status='retry',
                    files_done=index,files_total=len(urls),
                    retry_epoch=time.time()+seconds,error=last_network_error)
            progress(0,0,False)
            stored=stream_original_to_verified_ledger(
                url,ledger,key,closes,rate_gate=FILE_PACE,
                progress=progress,on_retry=on_retry)
            verified_files.append({'name':file_name,'url':url,
                                   'sha256':stored['sha256'],
                                   'bytes':stored['bytes']})
            live.record('download',key,file_key=file_key,file_name=file_name,
                        phase='저장 검증 완료',status='done',
                        bytes_done=stored['bytes'],bytes_total=stored['bytes'],
                        files_done=index+1,files_total=len(urls))
            active_file_key=''
            active_file_name=''
            live.record('download',key,phase='파일 다운로드',status='working',
                        files_done=index+1,files_total=len(urls))
        meta=dict(meta,downloadVerifiedFiles=verified_files)
        queue.downloaded(key,meta,len(urls),len(urls))
        live.record('download',key,phase='다운로드 완료',status='done',files_done=len(urls),files_total=len(urls))
        return True
    except ProviderBackoff as exc:
        # Old metadata quota errors do not block a downloaded, verified
        # bulk-manifest notice for six hours. Binary 429 still backs off.
        is_manifest_metadata=BULK_ENABLED and detects_upstream_limit(str(exc))
        queue.download_failed(key,str(exc),
                              retry_seconds=(60 if is_manifest_metadata else 21600))
        retry_at=time.time()+(60 if is_manifest_metadata else 21600)
        live.record('download',key,phase='API 제한',status='retry',retry_epoch=retry_at,error=str(exc))
        if active_file_key:
            live.record('download',key,file_key=active_file_key,file_name=active_file_name,
                        phase='API 제한 · 재시도 예정',status='retry',
                        files_done=active_files_done,files_total=active_files_total,
                        retry_epoch=retry_at,error=str(exc))
        return False
    except Exception as exc:
        if isinstance(exc,reader.OfficialAttachmentReferenceMissing):
            # A verified missing official file ID is not a transient network
            # failure; retain the error for inspection instead of 5-minute abuse.
            delay=86400
        elif str(exc).startswith('large_file:'):
            delay=86400
        else:
            delay=21600 if detects_upstream_limit(str(exc)) else 300
        if delay==21600:halt.set()
        queue.download_failed(key,type(exc).__name__+': '+str(exc)[:110],
                              retry_seconds=delay)
        retry_at=time.time()+delay
        live.record('download',key,phase='다운로드 실패',status='retry',retry_epoch=retry_at,error=str(exc))
        if active_file_key:
            live.record('download',key,file_key=active_file_key,file_name=active_file_name,
                        phase='파일 전송 실패 · 자동 재시도',status='retry',
                        files_done=active_files_done,files_total=active_files_total,
                        retry_epoch=retry_at,error=type(exc).__name__+': '+str(exc)[:110])
        return False
    finally:
        reader._NOTICE_CONTEXT.notice_key=None
        reader._NOTICE_CONTEXT.closes_on=''

def run_manifest_forever(queue,planner):
    """Independent source-discovery and date-batch manifest supply lane."""
    last_refresh=-REFRESH_SECONDS
    planner_pause_until=0.0
    last_planner_pass=-100.0
    live.worker('manifest','running')
    while True:
        now=time.monotonic()
        if now-last_refresh>=REFRESH_SECONDS:
            last_refresh=now
            try:
                discover_all(queue)
            except Exception as exc:
                print('RFP_DUAL_QUEUE_DISCOVERY_ERROR',
                      type(exc).__name__,str(exc)[:140],flush=True)
        if planner is not None and time.time()>=planner_pause_until and (
                now-last_planner_pass>=3):
            last_planner_pass=now
            try:
                live.worker('manifest','running')
                result=planner.populate_one_day()
                if result.get('calls') or result.get('new'):
                    print('RFP_BULK_MANIFEST_PROGRESS',
                          json.dumps(result,separators=(',',':')),flush=True)
                if result.get('new')==0 and result.get('calls')==0:
                    planner_pause_until=time.time()+60
            except BulkManifestQuota as exc:
                seconds=int(exc.retry_after_seconds)
                planner_pause_until=time.time()+seconds
                live.worker('manifest','retry',str(exc),planner_pause_until)
                print('RFP_BULK_LOCAL_CALL_BUDGET_PAUSE',
                      str(exc),'retrySeconds',seconds,flush=True)
            except Exception as exc:
                problem=str(exc)
                seconds=source_retry_seconds(problem)
                planner_pause_until=time.time()+seconds
                live.worker('manifest','retry',problem,planner_pause_until)
                print('RFP_BULK_OFFICIAL_SOURCE_UNAVAILABLE',
                      type(exc).__name__,problem[:140],
                      'retryAfterEpoch',round(planner_pause_until),
                      'retrySeconds',seconds,flush=True)
        time.sleep(1)


def refill_download_slots(queue,pool,inflight,halt):
    """Fill each free slot independently; callers never wait for whole batches."""
    added=0
    while len(inflight)<WORKERS and not halt.is_set():
        claim=queue.claim_download(ready_manifest=BULK_ENABLED)
        if claim is None:break
        future=pool.submit(download_one,queue,claim,halt)
        inflight[future]=claim
        added+=1
    return added


def run_download_forever(queue,halt):
    """Eight continuous download slots; refill on EACH completion."""
    halted_until=0.0
    last_report=time.monotonic()
    last_watchdog=time.monotonic()
    subprocess_started_epoch=time.time()
    started=0
    downloaded=0
    live.worker('download','running')
    with ThreadPoolExecutor(max_workers=WORKERS,
                            thread_name_prefix='rfp-original-fetch') as pool:
        inflight={}
        while True:
            if BULK_ENABLED:
                revived=queue.release_old_metadata_quota_retries()
                if revived:
                    print('RFP_OBSOLETE_QUOTA_RETRIES_RELEASED',
                          json.dumps({'notices':revived,
                                      'basis':'verified_bulk_manifest'}),flush=True)
            if time.time()>=halted_until and not halt.is_set():
                started+=refill_download_slots(queue,pool,inflight,halt)
            if inflight:
                finished,_=wait(tuple(inflight),timeout=POLL_SECONDS,
                                return_when=FIRST_COMPLETED)
                for future in finished:
                    claim=inflight.pop(future)
                    try:
                        succeeded=future.result()
                    except Exception as exc:
                        queue.download_failed(claim[0],
                              'unexpected_worker_failure_'+type(exc).__name__,
                              retry_seconds=300)
                        print('RFP_DOWNLOAD_WORKER_UNEXPECTED_ERROR',
                              type(exc).__name__,str(exc)[:140],flush=True)
                        succeeded=False
                    downloaded+=int(succeeded is True)
            else:time.sleep(POLL_SECONDS)
            # Last-resort recovery only if a claimed network stream has made
            # NO byte progress for three minutes. Typical slow-but-progressing
            # downloads are never reset merely because their timer is long.
            if inflight and time.monotonic()-last_watchdog>=5:
                last_watchdog=time.monotonic()
                claimed_keys={claim[0] for claim in inflight.values()}
                stuck=live.stalled_downloads(claimed_keys,idle_seconds=180,
                                             min_updated_epoch=subprocess_started_epoch)
                if stuck:
                    item=stuck[0]
                    reason='file_no_byte_progress_'+str(item['idleSeconds'])+'s'
                    retry_at=time.time()+30
                    queue.download_failed(item['noticeKey'],reason,retry_seconds=30)
                    live.record('download',item['noticeKey'],
                        file_key=item['fileKey'],file_name=item['fileName'],
                        phase='전송 정체 · 작업자 자동 복구',status='retry',
                        retry_epoch=retry_at,error=reason)
                    live.worker('download','retry',reason,retry_at)
                    print('RFP_DOWNLOAD_HARD_STALL_RESTART',json.dumps({
                        'notice':item['noticeKey'],'idleSeconds':item['idleSeconds'],
                        'recovery':'isolated_downloader_subprocess_relaunch',
                        'retryEpoch':retry_at},separators=(',',':')),flush=True)
                    # Threads blocked inside a platform socket cannot safely
                    # be interrupted. The separate parent process detects
                    # this exit, restarts in >=10 seconds, and reset_stale()
                    # requeues unaffected in-flight notices. Scanner stays up.
                    os._exit(72)
            if halt.is_set() and not inflight:
                # Do not hold all file workers for half an hour for
                # one old metadata provider error.
                halted_until=time.time()+30
                halt.clear()
                live.worker('download','retry','provider rate limit',halted_until)
                print('RFP_DOWNLOAD_PROVIDER_PAUSE',
                      json.dumps({'seconds':30},separators=(',',':')),flush=True)
            elif not halt.is_set() and time.time()>=halted_until:
                live.worker('download','running')
            if time.monotonic()-last_report>=10:
                print('RFP_DUAL_DOWNLOAD_BATCH',json.dumps({
                    'started':started,'downloaded':downloaded,
                    'active':len(inflight),'workers':WORKERS,
                    'queue':queue.stats()},separators=(',',':')),flush=True)
                started=downloaded=0
                last_report=time.monotonic()


def run_forever():
    configure_reader()
    os.environ.setdefault('WORKLINKS_RFP_UPGRADE_ONLY','1')
    os.environ.setdefault('WORKLINKS_RFP_DEFER_OCR','1')
    queue=RfpDualQueue(QUEUE)
    queue.reset_stale()
    migration=queue.reconcile_legacy_ready()
    print('RFP_VERIFIED_RECEIPT_MIGRATION',json.dumps(migration,separators=(',',':')),flush=True)
    live.recover_interrupted_downloads()
    planner=(BulkManifestPlanner(queue,DATA/'bids.sqlite3',
                                  reader.fetch_json,META_PACE,
                                  allow_exceptions=True)
             if BULK_ENABLED else None)
    halt=threading.Event()
    manifest_thread=threading.Thread(
        target=run_manifest_forever,args=(queue,planner),
        name='rfp-manifest-supply',daemon=True)
    manifest_thread.start()
    print('RFP_INDEPENDENT_8_SLOT_WORKERS_STARTED',
          json.dumps({'downloads':WORKERS,'manifestThread':True,
                      'scanProcess':'separate'}),flush=True)
    run_download_forever(queue,halt)


if __name__=='__main__':
    run_forever()
