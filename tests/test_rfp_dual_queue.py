#!/usr/bin/env python3
"""No-network regression: 1,000 downloads drain without scans, scan drains later."""
import datetime as dt
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rfp_dual_queue import RfpDualQueue
from rfp_call_ledger import CallLedger,cache_key
import refresh_worklinks_rfp as reader

# The regression commits 2,000+ tiny SQLite transactions. Test-only data
# belongs in tmpfs, not the slow Docker overlay on CentOS server123.
if Path('/dev/shm').is_dir() and os.access('/dev/shm',os.W_OK):
    tempfile.tempdir='/dev/shm'

with tempfile.TemporaryDirectory() as tmp:
    db=Path(tmp)/'rfp-dual-queue.sqlite3'
    queue=RfpDualQueue(db)
    rows=[('R26BK'+str(i).zfill(8),'000','2099-12-31') for i in range(1000)]
    assert queue.enqueue(rows,'reader-v1')==1000
    assert queue.enqueue(rows,'reader-v1')==0
    stats=queue.stats()
    assert stats['download']['total']==1000 and stats['scan']['total']==1000,stats
    meta={'attachments':{'ok':True,'complete':True,
                         'items':[{'name':'rfp.pdf','url':'https://www.g2b.go.kr/UntyAtchFile/rfp.pdf'}]},
          'noticeDocuments':{'ok':True,'complete':True},
          'downloadVerifiedFiles':[{'name':'rfp.pdf',
              'url':'https://www.g2b.go.kr/UntyAtchFile/rfp.pdf',
              'sha256':'a'*64,'bytes':100}]}
    # Original downloading never depends on scan claims.
    for i in range(1000):
        claim=queue.claim_download()
        assert claim is not None,(i,queue.stats())
        queue.downloaded(claim[0],meta,1,1)
    assert queue.claim_download() is None
    stats=queue.stats()
    assert stats['download']['done']==1000 and stats['scan']['done']==0,stats
    # Scanning starts independently and only after a particular notice is ready.
    seen=set()
    while len(seen)<1000:
        batch=queue.claim_ready(8)
        assert 0<len(batch)<=8,batch
        for key,_,loaded in batch:
            assert loaded==meta
            assert key not in seen
            seen.add(key)
            queue.scan_finished(key,True)
    stats=queue.stats()
    assert stats['download']['done']==stats['scan']['done']==1000,stats
    assert not queue.claim_ready(8)
    queue.enqueue(rows,'reader-v2')
    stats=queue.stats()
    assert stats['download']['done']==1000 and stats['scan']['done']==0,stats
    assert queue.ready_count()==1000,stats

    # Simulated missing compressed original: scanner must NEVER download over
    # the network; the notice is returned to the download lane.
    source='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK00000001'
    key='R26BK00000001:000'
    q=queue.claim_ready(8)
    assert any(row[0]==key for row in q)
    reader._NOTICE_CONTEXT.notice_key=key
    reader._NOTICE_CONTEXT.closes_on='2099-12-31'
    class Forbidden:
        def open(self,*args,**kwargs):raise AssertionError('scanner called official server')
    ledger=CallLedger(Path(tmp)/'rfp-request-ledger.sqlite3')
    try:
        with patch.dict(os.environ,{
            'WORKLINKS_RFP_DUAL_SCAN_ONLY':'1',
            'WORKLINKS_RFP_DUAL_QUEUE_DB':str(db),
            'WORKLINKS_RFP_LEDGER_DB':str(ledger.path)
        }):
            with patch.object(reader,'OPENER',Forbidden()):
                try:reader.download(source)
                except RuntimeError as e:
                    assert str(e)=='queued_original_missing'
                else:raise AssertionError('missed archive did not fail closed')
    finally:
        reader._NOTICE_CONTEXT.notice_key=None
        reader._NOTICE_CONTEXT.closes_on=''
    assert queue.stats()['download']['done']==999
    assert queue.ready_count()>=0

    # 1000 notices, queue facts are read-only from the existing API module.
    proxy=runpy.run_path(str(ROOT/'server/g2b-proxy.py'),run_name='dual_queue_test')
    live=proxy['rfp_dual_lane_progress'](str(db))
    assert live['available'] is True and live['download']['total']==1000,live
    assert live['download']['done']==999,live
    assert proxy['rfp_dual_lane_progress'](str(Path(tmp)/'missing.sqlite3'))=={'available':False}

    # Expired notices stop counting, while their archive retention is managed
    # separately by the existing compressed-byte cleanup.
    queue.enqueue([('R26BK99999999','000','2026-10-31')],'reader-v2')
    assert queue.retire_expired(today=dt.date(2026,11,14))==1
    assert queue.stats()['total']==1000
    # No electronic close is common for direct/letter bids and must not
    # disappear from the download lane; confirmed expired bids still retire.
    assert queue.enqueue([('R26BK99990001','000','')],'reader-v2')==1
    assert queue.retire_expired(today=dt.date(2026,11,14))==0
    assert queue.stats()['total']==1001
    with queue.connect() as connection:
        keys={row[0] for row in connection.execute(
            'SELECT notice_key FROM rfp_dual_notices').fetchall()}
    assert 'R26BK99990001:000' in keys
# A verified empty official manifest never enters the scan lane.
with tempfile.TemporaryDirectory() as tmp:
    q=RfpDualQueue(Path(tmp)/'empty.sqlite3')
    q.enqueue([('R26BK01234567','000','2099-12-31')],'reader-v1')
    key,_=q.claim_download()
    empty={'attachments':{'ok':True,'complete':True,'items':[]},
           'noticeDocuments':{'ok':True,'complete':True,'items':[]},
           'manifestOrigin':'verified_full_day_batch'}
    q.no_attachments(key,empty)
    assert q.claim_ready(8)==[]
    assert q.stats()['scan']['skipped']==1
    assert q.stats()['scan']['failed']==0
    assert q.stats()['scan']['done']==1
    assert q.stats()['download']['done']==1
    # Legacy ready rows are migrated to skip or back to verified download.
    q.enqueue([('R26BK01234568','000','2099-12-31')],'reader-v1')
    legacy,_=q.claim_download()
    with q.connect() as db:
        db.execute("UPDATE rfp_dual_notices SET download_status='ready', scan_status='retry',metadata_json=? WHERE notice_key=?",
                   (json.dumps(empty),legacy))
    q.enqueue([('R26BK01234569','000','2099-12-31')],'reader-v1')
    legacy_file,_=q.claim_download()
    with q.connect() as db:
        db.execute("UPDATE rfp_dual_notices SET download_status='ready',scan_status='retry',metadata_json=? WHERE notice_key=?",
                   (json.dumps({'attachments':{'ok':True,'complete':True,'items':[{'name':'a.pdf','url':'https://www.g2b.go.kr/UntyAtchFile/a.pdf'}]},
                   'noticeDocuments':{'ok':True,'complete':True}}),legacy_file))
    fix=q.reconcile_legacy_ready()
    assert fix=={'requeuedForVerifiedDownload':1,'verifiedEmptyManifestsSkipped':1},fix
    assert q.stats()['scan']['skipped']==2
    assert q.stats()['scan']['failed']==0
    assert q.claim_ready(8)==[]
    assert q.claim_download()[0]==legacy_file

print('RFP_DUAL_QUEUE_1000_FULL_DOWNLOAD_INDEPENDENT_SCAN=PASS')
