#!/usr/bin/env python3
"""No-network proof: quota recovery resumes from durable verified manifests."""
import datetime as dt
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rfp_dual_queue import RfpDualQueue
import rfp_bulk_manifests as bulk
import rfp_download_worker as worker

def meta(name):
    return {'attachments':{'ok':True,'complete':True,
                           'items':[{'name':name,'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/'+name}]},
            'noticeDocuments':{'ok':True,'complete':True,'items':[]}}

with tempfile.TemporaryDirectory() as tmp:
    q=RfpDualQueue(Path(tmp)/'rfp-dual-queue.sqlite3')
    entries=[
       ('R26BK12345678','000','2099-12-31'),
       ('R26BK12345679','000','2099-12-31'),
       ('R26BK12345680','000','2099-12-31')]
    q.enqueue(entries,'test-v1')
    first,second,third=[e[0]+':'+e[1] for e in entries]
    q.save_bulk_manifests({first:meta('first.pdf'),second:meta('second.pdf')})
    a=q.claim_download(ready_manifest=True)
    assert a[0]==first,a
    q.download_failed(first,'upstream_temporarily_rate_limited_daily_quota',
                      retry_seconds=21600)
    b=q.claim_download(ready_manifest=True)
    assert b[0]==second,b
    q.download_failed(second,'HTTPError: official_file_https_429',
                      retry_seconds=21600)
    assert q.claim_download(ready_manifest=True) is None
    assert q.release_old_metadata_quota_retries()==1
    assert q.release_old_metadata_quota_retries()==0
    ready=q.claim_download(ready_manifest=True)
    assert ready[0]==first,ready
    q.downloaded(first,meta('first.pdf'),1,1)
    # Binary 429 is distinct: do not prematurely retry the original file.
    assert q.claim_download(ready_manifest=True) is None
    # An unverified, absent list is never a reason to advance a pending notice.
    assert q.bulk_manifest(third) is None
    assert q.stats()['download']['done']==1
    # Once a verified list arrives later, the stale metadata retry is released
    # immediately, even if its original 6-hour timer remains in the DB.
    third_claim=q.claim_download(ready_manifest=False)
    assert third_claim[0]==third
    q.download_failed(third,'upstream_temporarily_rate_limited_daily_quota',
                      retry_seconds=21600)
    assert q.release_old_metadata_quota_retries()==0
    q.save_bulk_manifests({third:meta('third.pdf')})
    assert q.release_old_metadata_quota_retries()==1
    assert q.claim_download(ready_manifest=True)[0]==third

with tempfile.TemporaryDirectory() as tmp:
    q=RfpDualQueue(Path(tmp)/'queue.sqlite3')
    class NoPace:
        def acquire(self): pass
    planner=bulk.BulkManifestPlanner(q,Path(tmp)/'bids.sqlite3',
                                     lambda url:{},NoPace())
    old_hour=bulk.HOURLY_LIMIT
    old_day=bulk.DAILY_LIMIT
    bulk.HOURLY_LIMIT=1
    bulk.DAILY_LIMIT=200
    try:
        planner._reserve_api_call('ordinary','2026-11-14',1)
        try:
            planner._reserve_api_call('ordinary','2026-11-14',2)
        except bulk.BulkManifestQuota as exc:
            assert 1<=exc.retry_after_seconds<=3602,exc.retry_after_seconds
        else:
            raise AssertionError('rolling hour budget not enforced')
        with q.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM rfp_bulk_request_budget').fetchone()[0]==1
    finally:
        bulk.HOURLY_LIMIT=old_hour
        bulk.DAILY_LIMIT=old_day

with patch.object(worker.reader,'fetch_json',
       return_value={'services':{'bids':{'cooldownRemainingSeconds':13}}}):
    assert worker.source_retry_seconds('upstream_temporarily_rate_limited_daily_quota')==15
with patch.object(worker.reader,'fetch_json',
       return_value={'services':{'bids':{'cooldownRemainingSeconds':0}}}):
    assert worker.source_retry_seconds('old_error')==30
assert worker.FILE_PACE.interval==.125
print('RFP_QUOTA_RECOVERY_VERIFIED_MANIFEST_AUTO_RESUME=PASS',flush=True)
