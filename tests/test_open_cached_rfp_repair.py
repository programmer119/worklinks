#!/usr/bin/env python3
"""Stage 3 must never download files or scan before stage 2 has verified originals."""
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import repair_open_rfp_cached_attachments as task
from rfp_call_ledger import CallLedger,cache_key
from rfp_dual_queue import RfpDualQueue

kst=dt.timezone(dt.timedelta(hours=9))
now=dt.datetime.now(kst)
ahead=(now+dt.timedelta(hours=50)).isoformat()
too_soon=(now+dt.timedelta(hours=5)).isoformat()
source_url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01234567&fileSeq=2'
good_url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01234567&fileSeq=1'
file1='already_good.pdf'
file2='mislabeled.pdf'
report_key='R26BK01234567:000'
zipbuf=io.BytesIO()
with zipfile.ZipFile(zipbuf,'w') as z:
    for i in (1,2):
        z.writestr('inside'+str(i)+'.pdf',b'%PDF-'+b'Official text '*15)
bytes_=zipbuf.getvalue()
sha=hashlib.sha256(bytes_).hexdigest()

class PDF:
    def __init__(self,b):
        assert b.read().startswith(b'%PDF-')
        self.pages=[SimpleNamespace(extract_text=lambda:'This is an official text without entry requirements. '*6)]
class ForbiddenOpener:
    def open(self,*args,**kwargs):
        raise AssertionError('stage 3 must never download directly from G2B')

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    snap=root/'snapshots'
    snap.mkdir()
    db=sqlite3.connect(root/'bids.sqlite3')
    db.execute('CREATE TABLE bid_notices(bid_no TEXT,bid_ord TEXT,payload TEXT,sw_candidate INTEGER)')
    for bid,closes in [('R26BK01234567',ahead),('R26BK01234568',too_soon)]:
        db.execute('INSERT INTO bid_notices VALUES(?,?,?,?)',
                   (bid,'000',json.dumps({'closes':closes}),1))
    db.commit()
    db.close()
    source={'attachments':{'ok':True,'complete':True,
                'items':[{'name':file1,'url':good_url},{'name':file2,'url':source_url}]},
            'noticeDocuments':{'ok':True,'complete':True}}
    (snap/'rfp-top500-batch-metadata-20261111.json').write_text(
        json.dumps({'byNotice':{report_key:source}}))
    base={'manifestComplete':True,'status':'text_extracted_requires_review',
          'reviewComplete':False,
          'files':[{'name':file1,'readable':True,'sourceTextScanComplete':True,
             'sourceSha256':'a'*64},
           {'name':file2,'readable':False,'sourceTextScanComplete':False,
             'errorCategory':'file_extract_failure'}]}
    (snap/'rfp-coverage-index.json').write_text(json.dumps({'byNotice':{
        report_key:base,'R26BK01234568:000':base}}))
    archive=CallLedger(root/'rfp-request-ledger.sqlite3')
    # The real scheduler stages OCR in a temporary folder: the live queue lives elsewhere.
    q=RfpDualQueue(root/'live-downloader'/'rfp-dual-queue.sqlite3')
    receipts=[{'name':file1,'url':good_url,'sha256':'a'*64,'bytes':100},
              {'name':file2,'url':source_url,'sha256':sha,'bytes':len(bytes_)}]
    completed={**source,'downloadVerifiedFiles':receipts}
    with patch.dict(os.environ,{'WORKLINKS_RFP_DUAL_QUEUE_DB':str(q.path)}),\
         patch.object(task.rfp,'OPENER',ForbiddenOpener()),\
         patch.object(task.rfp,'fetch_json',side_effect=AssertionError('stage 3 cannot call metadata API')),\
         patch.dict(sys.modules,{'pypdf':SimpleNamespace(PdfReader=PDF)}):
        # Existing snapshot and official URLs do NOT authorize third-stage work.
        assert task.run(root,limit=40,execute=False,max_files=80)['selected']==0
        assert task.run(root,limit=40,execute=True,max_files=80)['result']=='no_eligible_verified_download'
        q.enqueue([('R26BK01234567','000','2099-12-31')],'fp')
        assert task.run(root,limit=40,execute=False,max_files=80)['selected']==0

        # Completed stage 2 receipt alone is not sufficient if its bytes disappeared.
        key,_=q.claim_download()
        assert key==report_key
        q.downloaded(key,completed,2,2)
        assert task.run(root,limit=40,execute=False,max_files=80)['selected']==1
        task.run(root,limit=40,execute=True,max_files=80)
        with q.connect() as conn:
            state=conn.execute('SELECT download_status,scan_status FROM rfp_dual_notices WHERE notice_key=?',(report_key,)).fetchone()
        assert state==('pending','pending'),state
        assert json.loads((snap/'rfp-coverage-index.json').read_text())['byNotice'][report_key]==base

        # Stage 2 restores the downloaded and SHA-verified original; stage 3 can now scan.
        archive.save_bytes(cache_key('official_attachment',source_url),bytes_,
                           notice_key=report_key,closes_on=ahead)
        key,_=q.claim_download()
        q.downloaded(key,completed,2,2)
        task.run(root,limit=40,execute=True,max_files=80)
        task.run(root,limit=40,execute=True,max_files=80)

    payload=(snap/'rfp-coverage-index.json').read_bytes()
    stored=json.loads(payload)
    recovered=stored['byNotice'][report_key]
    assert recovered['readableDocumentCount']==2,recovered
    assert recovered['unreadableDocumentCount']==0
    assert all(f.get('readable') and f.get('sourceTextScanComplete') for f in recovered['files'])
    assert recovered['files'][0]['sourceSha256']=='a'*64
    assert recovered['files'][1]['sourceSha256']==sha
    assert 'errorCategory' not in recovered['files'][1],recovered['files'][1]
    assert recovered['reviewComplete'] is False
    assert stored['byNotice']['R26BK01234568:000']==base
    assert gzip.decompress((snap/'rfp-coverage-index.json.gz').read_bytes())==payload

# Historical URLs may be retained as provenance, but do not grant stage-3 eligibility.
lost={'manifestComplete':True,'files':[
    {'name':file1,'readable':True,'sourceTextScanComplete':True,'sourceUrl':good_url},
    {'name':file2,'readable':False,'sourceTextScanComplete':False,'sourceUrl':source_url}]}
meta,origin=task.metadata_for(report_key,lost,{},Path('/nonexistent/ledger.sqlite3'),
                               [({report_key:lost},'archived_full_scan')])
assert origin=='archived_full_scan'
assert task.metadata_valid(meta,lost)
changed={**lost,'manifestChangePending':True}
assert task.metadata_for(report_key,changed,{},Path('/nonexistent/ledger.sqlite3'),
                         [({report_key:lost},'archive')])[0] is None

print('WORKLINKS_OPEN_RFP_VERIFIED_DOWNLOAD_ONLY_TEST=PASS')
