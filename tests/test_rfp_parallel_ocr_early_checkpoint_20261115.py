#!/usr/bin/env python3
"""Offline: three OCR workers start together; first verified notice persists early."""
import datetime as dt
import json
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import repair_open_rfp_cached_attachments as repair

now=dt.datetime.now(dt.timezone.utc)
keys=['R26BK01825188:000','R26BK01813104:000','R26BK01815237:000']
source='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/file'
def make():
    scans={}
    meta={}
    for i,key in enumerate(keys):
        name='short-'+str(i)+'.pdf'
        scans[key]={'status':'text_extracted_requires_review',
                    'checkedAt':(now-dt.timedelta(days=1)).isoformat(),
                    'classificationVersion':1,'manifestComplete':True,
                    'readableDocumentCount':0,
                    'files':[{'name':name,'readable':False,
                              'sourceTextScanComplete':False,
                              'errorCategory':'pdf_ocr_incomplete'}]}
        meta[key]={'attachments':{'ok':True,'complete':True,
                    'items':[{'name':name,'url':source+str(i)}]},
                   'noticeDocuments':{'ok':True,'complete':True},
                   'downloadVerifiedFiles':[{'url':source+str(i),
                                             'sha256':chr(97+i)*64}]}
    return scans,meta

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    (root/'snapshots').mkdir()
    scans,metas=make()
    original={'ok':True,'byNotice':scans}
    (root/'snapshots/rfp-coverage-index.json').write_text(json.dumps(original),encoding='utf-8')
    barrier=threading.Barrier(3,timeout=6)
    completed=set()
    checkpoints=[]
    began=time.perf_counter()
    sleeps={keys[0]:.15,keys[1]:.35,keys[2]:.55}
    def work(key,row,meta,ledger,file_limit):
        barrier.wait()
        time.sleep(sleeps[key])
        f=row['files'][0]
        f.update(readable=True,sourceTextScanComplete=True,
                 sourceSha256=metas[key]['downloadVerifiedFiles'][0]['sha256'],
                 lastReaderAttemptVersion=repair.READER_ATTEMPT_VERSION,
                 lastReaderAttemptAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                 staffingRoleScanVersion=99,staffingFactScanVersion=99,
                 qualificationScanTruncated=False,staffingRoleScanTruncated=False)
        completed.add(key)
        return [{'name':f['name'],'sourceUrl':metas[key]['downloadVerifiedFiles'][0]['url'],
                 'readable':True,'clauseCandidates':[]}], Counter(
                 {'reader_attempt_recorded':1,'file_repaired':1,'cache_hit':1})
    def publish(key,row,fingerprint):
        checkpoints.append((key,len(completed),time.perf_counter()-began))
        assert row['files'][0]['readable'] is True
        assert row['staffingRoleScanComplete'] is True
        return True
    with patch.object(repair,'open_candidates',return_value=[
             (k,now+dt.timedelta(days=4)) for k in keys]),\
         patch.object(repair,'verified_download_queue',return_value=metas),\
         patch.object(repair,'current_verified_download_metadata',
                      side_effect=lambda p,k:metas[k]),\
         patch.object(repair,'process_one',side_effect=work),\
         patch.object(repair,'verified_complete_for_early_checkpoint',
                      return_value=True),\
         patch.object(repair.rfp,'publish_notice_checkpoint',side_effect=publish):
        result=repair.run(root,limit=3,execute=True,max_files=3,workers=3)
    elapsed=time.perf_counter()-began
    assert len(result)==3,result
    assert len(checkpoints)==3,checkpoints
    assert checkpoints[0][1]==1,checkpoints
    assert checkpoints[0][2]<.35,checkpoints
    assert elapsed<2.4,elapsed
    saved=json.loads((root/'snapshots/rfp-coverage-index.json').read_text())
    assert all(saved['byNotice'][key]['files'][0]['readable'] for key in keys)
    assert (root/'snapshots/rfp-coverage-index.json.gz').is_file()
    assert len(completed)==3
print('RFP_OCR_THREE_PARALLEL_WORKERS_IMMEDIATE_CHECKPOINT_AND_SINGLE_SNAPSHOT=PASS')
