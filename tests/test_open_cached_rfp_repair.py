#!/usr/bin/env python3
"""Offline end-to-end: 24-hour cutoff, no metadata API and no good-file GET."""
import datetime as dt
import gzip
import io
import json
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

kst=dt.timezone(dt.timedelta(hours=9))
now=dt.datetime.now(kst)
ahead=(now+dt.timedelta(hours=50)).isoformat()
too_soon=(now+dt.timedelta(hours=5)).isoformat()
source_url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01234567&fileSeq=2'
good_url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01234567&fileSeq=1'
file1='already_good.pdf';file2='mislabeled.pdf'
report_key='R26BK01234567:000'
zipbuf=io.BytesIO()
with zipfile.ZipFile(zipbuf,'w') as z:
    for i in (1,2):z.writestr('inside'+str(i)+'.pdf',b'%PDF-'+b'Official text '*15)
bytes_=zipbuf.getvalue()

class PDF:
    def __init__(self,b):
        assert b.read().startswith(b'%PDF-')
        self.pages=[SimpleNamespace(extract_text=lambda:'This is an official text without entry requirements. '*6)]
class Resp(io.BytesIO):
    status=200
    headers={'Content-Length':str(len(bytes_))}
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
class Opener:
    def __init__(self):self.calls=0
    def open(self,request,timeout):
        assert request.full_url==source_url,request.full_url
        self.calls+=1
        return Resp(bytes_)

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);snap=root/'snapshots';snap.mkdir()
    db=sqlite3.connect(root/'bids.sqlite3')
    db.execute('CREATE TABLE bid_notices(bid_no TEXT,bid_ord TEXT,payload TEXT,sw_candidate INTEGER)')
    for bid,closes in [('R26BK01234567',ahead),('R26BK01234568',too_soon)]:
        db.execute('INSERT INTO bid_notices VALUES(?,?,?,?)',
                   (bid,'000',json.dumps({'closes':closes}),1))
    db.commit();db.close()
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
    opened=Opener()
    with patch.object(task.rfp,'OPENER',opened),\
         patch.object(task.rfp,'fetch_json',side_effect=AssertionError('new upstream API called')),\
         patch.dict(sys.modules,{'pypdf':SimpleNamespace(PdfReader=PDF)}):
        dry=task.run(root,limit=40,execute=False,max_files=80)
        assert dry['selected']==1,dry
        task.run(root,limit=40,execute=True,max_files=80)
        task.run(root,limit=40,execute=True,max_files=80)
    assert opened.calls==1,'existing successes must never be redownloaded'
    payload=(snap/'rfp-coverage-index.json').read_bytes()
    stored=json.loads(payload)
    recovered=stored['byNotice'][report_key]
    assert recovered['readableDocumentCount']==2,recovered
    assert recovered['unreadableDocumentCount']==0
    assert all(f.get('readable') and f.get('sourceTextScanComplete') for f in recovered['files'])
    assert recovered['files'][0]['sourceSha256']=='a'*64
    assert recovered['reviewComplete'] is False
    assert stored['byNotice']['R26BK01234568:000']==base
    assert gzip.decompress((snap/'rfp-coverage-index.json.gz').read_bytes())==payload

# When the snapshot metadata index lacks a notice, archived official source URLs
# are sufficient; the government metadata endpoint must NOT be called.
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

print('WORKLINKS_OPEN_RFP_CACHED_REPAIR_TEST=PASS')
