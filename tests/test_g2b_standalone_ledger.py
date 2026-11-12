#!/usr/bin/env python3
"""Offline evidence that SME/direct-production scheduled calls use the shared audit ledger."""
import importlib.util,json,os,pathlib,sqlite3,sys,tempfile
from unittest.mock import patch

root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
from rfp_call_ledger import CallLedger

def load(name):
    file=root/'scripts'/name
    spec=importlib.util.spec_from_file_location(name.replace('.py',''),file)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Response:
    status=200
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.raw[:n] if n>=0 else self.raw

with tempfile.TemporaryDirectory() as folder:
    db=pathlib.Path(folder)/'ledger.sqlite3'
    with patch.dict(os.environ,{'WORKLINKS_RFP_LEDGER_DB':str(db)}):
        smpp=load('worklinks_sme_cert_snapshot.py')
        calls=[]
        html=('<div class="board list pc_tbl"><table><tbody><tr>'
              '<td>1</td><td>중소벤처기업부</td><td>2026-11-01</td>'
              '<td>테스트기업</td><td>소기업</td>'
              '</tr></tbody></table></div>').encode('utf-8')
        def official(req,timeout=0):
            calls.append(req.full_url)
            return Response(html)
        with patch.object(smpp,'urlopen',official):
            a=smpp.official_lookup('1308185973')
            b=smpp.official_lookup('1308185973')
        assert a==b and a['validState']=='valid'
        assert len(calls)==1,calls

        direct=load('worklinks_direct_production_snapshot.py')
        docs=[]
        def file_fetch(req,timeout=0):
            docs.append(req.full_url)
            return Response(b'<html>official download references</html>')
        with patch.object(direct,'urlopen',file_fetch):
            r1=direct.read(direct.PAGE)
            r2=direct.read(direct.PAGE)
        assert r1==r2 and len(docs)==1,docs
        ledger=CallLedger(db)
        counts=ledger.stats()['counts']
        assert counts['smpp_http:http_verified']==1,counts
        assert counts['smpp:verified_snapshot_reused']==1,counts
        assert counts['direct_production_http:http_received']==1,counts
        assert counts['direct_production:verified_page_reused']==1,counts
        with sqlite3.connect(db) as conn:
            assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
            events=json.dumps(conn.execute('SELECT kind,request_key FROM call_events').fetchall())
            assert '1308185973' not in events  # identities are keyed by digest, not plaintext
        print('G2B_SME_DIRECT_PRODUCTION_SHARED_LEDGER_NO_DUPLICATE_HTTP=PASS',counts)
