#!/usr/bin/env python3
"""Server123's dedicated RFP download process: no text extraction or scan waits.

In one persistent run it discovers the ENTIRE current unexpired backlog,
then fills the durable download queue with at most eight in-flight notices.
The independent scan process only consumes already-downloaded originals.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.parse

import refresh_worklinks_rfp as reader
from rfp_call_ledger import cache_key
from rfp_dual_queue import RfpDualQueue
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
FILE_PACE=Pace(0.25)

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
    selected=[(no,order,closes) for no,order,closes in selected if closes]
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

def download_one(queue,claim,halt):
    key,closes=claim
    bid,ordinal=key.split(':',1)
    if halt.is_set():
        queue.download_failed(key,'upstream_paused',retry_seconds=600)
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
        # No scanner or extractor is called anywhere in this process.
        seen=set()
        urls=[]
        for item in manifest:
            approved=reader.legal_file(item)
            if not approved:continue
            name,url=approved
            if os.environ.get('WORKLINKS_RFP_DEFER_OCR')=='1' and name.lower().endswith(
                ('.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp')):
                continue
            if url not in seen:seen.add(url);urls.append(url)
        reader._NOTICE_CONTEXT.notice_key=key
        reader._NOTICE_CONTEXT.closes_on=closes
        ledger=reader.active_rfp_ledger()
        if ledger is None:raise RuntimeError('durable_binary_ledger_not_configured')
        for url in urls:
            if halt.is_set():raise ProviderBackoff('provider_paused')
            # The approved download() reuses compressed originals by hash;
            # it only opens official HTTPS when the verified bytes are absent.
            data=reader.download(url,rate_gate=FILE_PACE)
            stored=ledger.get_bytes(cache_key('official_attachment',url))
            if stored is None or hashlib.sha256(data).digest()!=hashlib.sha256(stored).digest():
                raise RuntimeError('original_archive_not_verified_or_storage_quota')
            del data,stored
        queue.downloaded(key,meta,len(urls),len(urls))
        return True
    except ProviderBackoff as exc:
        queue.download_failed(key,str(exc),retry_seconds=21600)
        return False
    except Exception as exc:
        delay=21600 if detects_upstream_limit(str(exc)) else 300
        if delay==21600:halt.set()
        queue.download_failed(key,type(exc).__name__+': '+str(exc)[:110],
                              retry_seconds=delay)
        return False
    finally:
        reader._NOTICE_CONTEXT.notice_key=None
        reader._NOTICE_CONTEXT.closes_on=''

def run_forever():
    configure_reader()
    os.environ.setdefault('WORKLINKS_RFP_UPGRADE_ONLY','1')
    os.environ.setdefault('WORKLINKS_RFP_DEFER_OCR','1')
    queue=RfpDualQueue(QUEUE)
    queue.reset_stale()
    planner=(BulkManifestPlanner(queue,DATA/'bids.sqlite3',
                                  reader.fetch_json,META_PACE)
             if BULK_ENABLED else None)
    last_refresh=0
    halted_until=0
    planner_pause_until=0
    last_planner_pass=-100.0
    while True:
        now=time.monotonic()
        if now-last_refresh>=REFRESH_SECONDS:
            discover_all(queue)
            last_refresh=now
        if planner is not None and time.time()>=planner_pause_until and (
                now-last_planner_pass>=3):
            last_planner_pass=now
            try:
                result=planner.populate_one_day()
                if result.get('calls') or result.get('new'):
                    print('RFP_BULK_MANIFEST_PROGRESS',
                          json.dumps(result,separators=(',',':')),flush=True)
                if result.get('new')==0 and result.get('calls')==0:
                    planner_pause_until=time.time()+60
            except BulkManifestQuota as exc:
                planner_pause_until=time.time()+3600
                print('RFP_BULK_LOCAL_CALL_BUDGET_PAUSE',
                      str(exc),flush=True)
            except Exception as exc:
                # Never replace an incomplete multi-page response with an
                # invented empty source, and never flood the API with retries.
                problem=str(exc)
                planner_pause_until=time.time()+(3600 if
                    detects_upstream_limit(problem) or
                    getattr(exc,'code',0) in (429,502,503)
                    else 600)
                print('RFP_BULK_OFFICIAL_SOURCE_UNAVAILABLE',
                    type(exc).__name__,problem[:140],
                    'retryAfterEpoch',round(planner_pause_until),flush=True)
        if time.time()<halted_until:
            time.sleep(min(30,halted_until-time.time()))
            continue
        halt=threading.Event()
        claimed=[]
        for i in range(WORKERS):
            row=queue.claim_download(ready_manifest=BULK_ENABLED)
            if row:claimed.append(row)
            else:break
        if not claimed:
            time.sleep(POLL_SECONDS)
            continue
        good=0
        with ThreadPoolExecutor(max_workers=WORKERS,
                                thread_name_prefix='rfp-original-fetch') as pool:
            tasks=[pool.submit(download_one,queue,row,halt) for row in claimed]
            for task in as_completed(tasks):
                good+=int(task.result() is True)
        if halt.is_set():
            halted_until=time.time()+1800
            print('RFP_DOWNLOAD_PROVIDER_PAUSE',json.dumps(
                {'seconds':1800,'claimed':len(claimed)},separators=(',',':')),flush=True)
        print('RFP_DUAL_DOWNLOAD_BATCH',json.dumps(
            {'started':len(claimed),'downloaded':good,'workers':WORKERS,
             'queue':queue.stats()},separators=(',',':')),flush=True)

if __name__=='__main__':
    run_forever()
