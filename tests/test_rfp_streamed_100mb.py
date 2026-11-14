#!/usr/bin/env python3
"""No-network regression: 100 MB originals stream to verified SQLite BLOB.

Tests a real compressed ledger write/read without a 30-80 MB Python response.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.error
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rfp_call_ledger import CallLedger,cache_key
import refresh_worklinks_rfp as reader
import rfp_download_worker as worker

URL='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01826833'
assert reader.MAX_FILE==100_000_000
assert worker.WORKERS<=8

class StreamingResponse:
    status=200
    def __init__(self,length):
        self.length=length
        self.pos=0
        self.headers={'Content-Length':str(length)}
        self.max_read=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):
        assert isinstance(n,int) and n<=256*1024,(n,'not chunk-bounded')
        self.max_read=max(self.max_read,n)
        count=min(n,self.length-self.pos)
        self.pos+=count
        return b'W'*count

class MockOpener:
    def __init__(self,source):
        self.source=source
        self.calls=0
    def open(self,request,timeout=0):
        self.calls+=1
        return self.source()

with tempfile.TemporaryDirectory() as tmp:
    ledger=CallLedger(Path(tmp)/'ledger.sqlite3')
    length=81_327_152  # Previously failed official HWPX, below the new 100MB cap.
    response=StreamingResponse(length)
    source=MockOpener(lambda:response)
    with patch.object(reader,'OPENER',source):
        new=worker.stream_original_to_verified_ledger(
            URL,ledger,'R26BK01800763:000','2099-12-31')
        assert new['bytes']==length,new
        expected=hashlib.sha256()
        for i in range(0,length,1024*1024):
            expected.update(b'W'*min(1024*1024,length-i))
        assert new['sha256']==expected.hexdigest()
        assert response.pos==length and response.max_read<=256*1024
        with ledger._connect() as db:
            row=db.execute('SELECT media_type,length(payload) FROM verified_cache WHERE request_key=?',
                (cache_key('official_attachment',URL),)).fetchone()
        assert row and row[0]=='bytes' and row[1]>0
        again=worker.stream_original_to_verified_ledger(
            URL,ledger,'R26BK01800763:000','2099-12-31')
        assert again==new
        assert source.calls==1,'cached original was fetched again'

    # File larger than 100MB must be rejected before any body allocation.
    oversize=MockOpener(lambda:StreamingResponse(100_000_001))
    with patch.object(reader,'OPENER',oversize):
        try:worker.stream_original_to_verified_ledger(
            URL+'-over',ledger,'R26BK01800763:000','2099-12-31')
        except ValueError as exc:
            assert 'large_file' in str(exc)
            assert '100000001' in str(exc)
        else:raise AssertionError('oversize official file was accepted')

    # Verified official 422 is a permanent source-reference failure, not a
    # temporary 5-minute socket retry, and no raw file is read or archived.
    error_json=json.dumps({'ErrorCode':-1,
        'ErrorMsg':'파일이 존재하지 않습니다.'}).encode()
    def missing():
        raise urllib.error.HTTPError(URL,422,'missing',
                {'Content-Type':'application/json'},io.BytesIO(error_json))
    with patch.object(reader,'OPENER',MockOpener(missing)):
        try:worker.stream_original_to_verified_ledger(
            URL+'-missing',ledger,'R26BK01823630:000','2099-12-31')
        except reader.OfficialAttachmentReferenceMissing:pass
        else:raise AssertionError('official 422 was treated as a retryable success')

    assert not list(Path(tmp).glob('.rfp-download-*.part'))
    assert not list(Path(tmp).glob('.rfp-compressed-*.part'))
    errors=[v for v in ledger.stats()['counts'] if v=='attachment_http:http_failed']
    assert errors
print('RFP_100MB_STREAMED_ORIGINAL_VERIFIED_AND_422_CLASSIFIED=PASS',flush=True)
