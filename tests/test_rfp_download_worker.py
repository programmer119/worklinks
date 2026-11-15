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
    def fake_download(url,ledger,notice_key,closes_on,*,rate_gate=None,progress=None,on_retry=None):
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
        return {'sha256':__import__('hashlib').sha256(b'archive raw').hexdigest(),
                'bytes':len(b'archive raw')}
    halt=threading.Event()
    with patch.object(worker.reader,'fetch_json',side_effect=fake_get),\
         patch.object(worker,'stream_original_to_verified_ledger',side_effect=fake_download),\
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
         patch.object(worker,'stream_original_to_verified_ledger',side_effect=AssertionError('must not download')),\
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
    # The official server's exact JSON 422 is terminal, not an infinite retry.
    # Successful originals are still SHA-receipted and never sent to the
    # scanner as a falsely complete bundle.
    missing_bid='R26BK01823630'
    missing_key=missing_bid+':000'
    queue.enqueue([(missing_bid,'000','2099-12-31')],'r1')
    good='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/success.pdf'
    bad='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/missing.pdf'
    partial={'attachments':{'ok':True,'complete':True,'items':[
        {'name':'available.pdf','url':good},
        {'name':'unavailable.pdf','url':bad}]},
        'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
    def partial_download(url,ledger,notice_key,closes_on,**kwargs):
        if url==bad:
            raise worker.reader.OfficialAttachmentReferenceMissing(
                'official_attachment_reference_missing_422')
        return {'sha256':'c'*64,'bytes':90}
    halt.clear()
    with patch.object(worker.reader,'fetch_json',return_value=partial),\\
         patch.object(worker.reader,'active_rfp_ledger',return_value=FakeLedger()),\\
         patch.object(worker,'stream_original_to_verified_ledger',side_effect=partial_download),\\
         patch.object(worker.META_PACE,'acquire',return_value=None):
        claim=queue.claim_download()
        assert claim[0]==missing_key
        assert worker.download_one(queue,claim,halt)
    with queue.connect() as conn:
        record=conn.execute('''SELECT download_status,download_retry_epoch,metadata_json
            FROM rfp_dual_notices WHERE notice_key=?''',(missing_key,)).fetchone()
    assert record[0]=='error_confirmed' and record[1]==0,record[:2]
    saved=__import__('json').loads(record[2])
    assert len(saved['downloadVerifiedFiles'])==1
    assert saved['downloadVerifiedFiles'][0]['url']==good
    assert saved['downloadErrorFiles']==[{'name':'unavailable.pdf','url':bad,
        'httpStatus':422,'reason':'official_attachment_reference_missing_422'}]
    assert queue.claim_download() is None,'terminal 422 must not requeue'
    assert missing_key not in [x[0] for x in queue.claim_ready(100)]
    assert queue.stats()['download']['errors']==1
    assert queue.stats()['download']['processed']==queue.stats()['download']['done']+1
    # Identical official references remain terminal across manifest refresh.
    queue.save_bulk_manifests({missing_key:partial})
    assert queue.claim_download() is None
    # A new authoritative file URL opens only the changed notice.
    changed=__import__('copy').deepcopy(partial)
    changed['attachments']['items'][1]['url']=bad+'?new=1'
    queue.save_bulk_manifests({missing_key:changed})
    assert queue.claim_download()[0]==missing_key

    print('RFP_SEPARATE_DOWNLOAD_WORKER_8_LANES_NO_SCANNER=PASS',
          {'downloaded':downloaded,'maximumConcurrent':max_parallel,
           'queuedForScan':stats['download']['done']},flush=True)
