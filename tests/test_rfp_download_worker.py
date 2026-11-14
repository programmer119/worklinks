#!/usr/bin/env python3
"""No-network worker proof: download all original notices without calling scanner."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rfp_download_worker as worker
from rfp_dual_queue import RfpDualQueue

with tempfile.TemporaryDirectory() as root:
    queue=RfpDualQueue(Path(root)/'work.sqlite3')
    notices=[('R26BK'+str(i).zfill(8),'000','2099-12-31') for i in range(32)]
    queue.enqueue(notices,'r1')
    meta={
      'attachments':{'ok':True,'complete':True,
        'items':[{'name':'notice.pdf','url':
          'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?src=1'}]},
      'noticeDocuments':{'ok':True,'complete':True}}
    lock=threading.Lock()
    max_parallel=0
    active=0
    downloaded=0
    class FakeLedger:
        def get_bytes(self,key):return b'archive raw'
    def fake_get(url):
        assert 'bid-evidence?' in url
        return meta
    def fake_download(url,*,rate_gate=None,progress=None,on_retry=None):
        nonlocal_var=None
        global active,max_parallel,downloaded
        with lock:
            active+=1
            max_parallel=max(max_parallel,active)
            downloaded+=1
        if progress:progress(4,11,False)
        time.sleep(.04)
        if progress:progress(11,11,True)
        with lock:active-=1
        return b'archive raw'
    halt=threading.Event()
    with patch.object(worker.reader,'fetch_json',side_effect=fake_get),\
         patch.object(worker.reader,'download',side_effect=fake_download),\
         patch.object(worker.reader,'active_rfp_ledger',return_value=FakeLedger()),\
         patch.object(worker.META_PACE,'acquire',return_value=None):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures=[]
            for _ in range(32):
                claimed=queue.claim_download()
                assert claimed is not None
                futures.append(pool.submit(worker.download_one,queue,claimed,halt))
            assert all(f.result() for f in as_completed(futures))
    stats=queue.stats()
    assert stats['download']['done']==32 and stats['scan']['done']==0,stats
    assert max_parallel>=2,max_parallel
    assert downloaded==32,downloaded
    assert queue.ready_count()==32,stats
    ready=queue.claim_ready(1)
    assert len(ready)==1
    verify=ready[0][2]['downloadVerifiedFiles']
    assert len(verify)==1 and verify[0]['sha256']==__import__('hashlib').sha256(b'archive raw').hexdigest()
    assert verify[0]['url']==meta['attachments']['items'][0]['url']
    queue.scan_release([ready[0][0]])
    # No file means no downloader work and no scanner invocation.
    empty_key='R26BK88888888:000'
    queue.enqueue([('R26BK88888888','000','2099-12-31')],'r1')
    empty={'attachments':{'ok':True,'complete':True,'items':[]},
           'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
    with patch.object(worker.reader,'fetch_json',return_value=empty),\
         patch.object(worker.reader,'download',side_effect=AssertionError('must not download')),\
         patch.object(worker.META_PACE,'acquire',return_value=None):
        chosen=queue.claim_download()
        assert chosen[0]==empty_key,chosen
        assert worker.download_one(queue,chosen,halt)
    with queue.connect() as conn:
        assert conn.execute('SELECT download_status,scan_status FROM rfp_dual_notices WHERE notice_key=?',(empty_key,)).fetchone()==('no_attachments','skipped')
    assert queue.stats()['scan']['failed']==0
    # Retriable metadata failures do not consume the scan queue or pretend
    # work is finished.
    another=('R26BK99999998','000','2099-12-31')
    queue.enqueue([another],'r1')
    def fail_fetch(url):return {'attachments':{'ok':False,'complete':False,
                                      'error':'upstream_result_22 DAILY_QUOTA'}}
    halt.clear()
    with patch.object(worker.reader,'fetch_json',side_effect=fail_fetch),\
         patch.object(worker.META_PACE,'acquire',return_value=None):
        row=queue.claim_download()
        assert worker.download_one(queue,row,halt) is False
    assert halt.is_set()
    stats=queue.stats()
    assert stats['download']['failed']==1
    assert stats['scan']['done']==1
    print('RFP_SEPARATE_DOWNLOAD_WORKER_8_LANES_NO_SCANNER=PASS',
          {'downloaded':downloaded,'maximumConcurrent':max_parallel,
           'queuedForScan':stats['download']['done']},flush=True)
