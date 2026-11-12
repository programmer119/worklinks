#!/usr/bin/env python3
"""No-network proof that received API/file bytes are never fetched twice."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rfp_call_ledger import CallLedger, cache_key, ledger_path
import batch_backfill_changcom_top500_rfp as batch
import refresh_worklinks_rfp as reader

with tempfile.TemporaryDirectory() as tmp:
    dest=Path(tmp)/'rfp-request-ledger.sqlite3'
    ledger=CallLedger(dest)
    k=cache_key('bid_evidence','R26BK01811411:000')
    document={'attachments':{'ok':True,'complete':True,'items':[{'name':'abc.hwp'}]},
              'noticeDocuments':{'ok':True,'complete':True}}
    ledger.save_json(k,document)
    assert ledger.get_json(k)==document
    assert ledger.get_json(k,source_revision='NEWER_NOTICE') is None
    assert ledger.get_json(k,max_age_seconds=-1) is None
    # Nothing with a corrupt or incomplete hash can be replayed.
    with sqlite3.connect(dest) as db:
        db.execute("UPDATE verified_cache SET sha256=? WHERE request_key=?",('0'*64,k))
    assert ledger.get_json(k) is None
    ledger.save_json(k,document)
    assert ledger.get_json(k)==document
    # A 2MB+ permitted official attachment must be reusable without HTTP.
    large=bytes((i % 251 for i in range(2_100_123)))
    large_key=cache_key('official_attachment','large-verified-test')
    assert ledger.save_bytes(large_key,large)
    assert ledger.get_bytes(large_key)==large
    ledger.record('notice_metadata',k,'metadata_unconfirmed',
                  notice_key='R26BK01811411:000')
    assert ledger.get_json(k)==document

    raw={'response':{'header':{'resultCode':'00'},'body':{
         'totalCount':1,'items':[{'bidNtceNo':'R26BK01811411','bidNtceOrd':'000'}]}}}
    encoded=json.dumps(raw).encode()
    class Response:
        status=200
        headers={}
        def __init__(self,body):self.body=body
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,n=None):return self.body
    physically_called=[]
    def official_fetch(req,timeout=0):
        physically_called.append(req.full_url)
        return Response(encoded)
    p=batch.Provider('a-private-service-key',ledger=ledger)
    with patch.object(batch.urllib.request,'urlopen',official_fetch):
        original=p.request('ordinary','20261109','20261110',1)
        assert p.request('ordinary','20261109','20261110',1)==original
        assert batch.Provider('a-different-key',ledger=ledger).request(
               'ordinary','20261109','20261110',1)==original
    assert len(physically_called)==1,physically_called

    # 404 failure must be logged, NOT converted into an empty success.
    import urllib.error
    def failed_fetch(req,timeout=0):
        raise urllib.error.HTTPError(req.full_url,404,'missing',{},None)
    with patch.object(batch.urllib.request,'urlopen',failed_fetch):
        try:p.request('detail','20261109','20261110',1)
        except RuntimeError:pass
        else:raise AssertionError('failed official API treated as success')
    key_failed=cache_key('official_batch_v1','detail','20261109','20261110',1,999)
    assert ledger.get_json(key_failed) is None

    # A binary was received but extraction could fail. Cache its verified
    # bytes, then retry parsing from the SAME bytes without another download.
    old=os.environ.get('WORKLINKS_RFP_LEDGER_DB')
    os.environ['WORKLINKS_RFP_LEDGER_DB']=str(dest)
    source_url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01811411'
    from_mock=[]
    class FileOpener:
        def open(self,req,timeout=0):
            from_mock.append(req.full_url)
            return Response(b'D0CF test binary identical after restart')
    opener=reader.OPENER
    try:
        reader.OPENER=FileOpener()
        reader._NOTICE_CONTEXT.notice_key='R26BK01811411:000'
        first=reader.download(source_url)
        second=reader.download(source_url)
        reader._NOTICE_CONTEXT.notice_key=None
        assert first==second
        assert len(from_mock)==1,from_mock
        class ProxyOpener:
            def open(self,req,timeout=0):
                return Response(json.dumps({'ok':True}).encode())
        reader.OPENER=ProxyOpener()
        assert reader.fetch_json(
            'http://127.0.0.1:18192/api/g2b/bid-evidence?bidNo=R26BK01811411&order=000')['ok'] is True
        # The actual low-level response/request attempts are separately logged.
    finally:
        reader.OPENER=opener
        if old is None:os.environ.pop('WORKLINKS_RFP_LEDGER_DB',None)
        else:os.environ['WORKLINKS_RFP_LEDGER_DB']=old

    stat=ledger.stats()
    assert stat['counts']['official_batch_http:http_ok']==1
    assert stat['counts']['official_batch_http:http_failed']==1
    assert stat['counts']['attachment_http:http_ok']==1
    assert stat['counts']['proxy_http:http_ok']==1
    assert stat['counts']['attachment_reuse:verified_bytes_reused']==1
    assert stat['counts']['cache:cache_hit']>=4
    assert stat['events']>=9
    con=sqlite3.connect(dest)
    # Secrets MUST NOT be recorded even though they are used in the request.
    rows=con.execute("SELECT request_key,detail FROM call_events").fetchall()
    assert all('a-private-service-key' not in str(x) for x in rows)
    mapped=con.execute("SELECT kind,notice_key FROM call_events WHERE kind IN ('attachment_http','attachment_reuse','proxy_http')").fetchall()
    assert all(k=='R26BK01811411:000' for kind,k in mapped),mapped
    con.close()

print('RFP_PERSISTENT_CALL_LEDGER_NO_DUPLICATE_HTTP=PASS')
