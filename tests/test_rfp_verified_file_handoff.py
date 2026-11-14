#!/usr/bin/env python3
"""Downloader verified-file receipts, not official manifest entries, determine scanner work."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
import rfp_live_activity as live
from rfp_call_ledger import cache_key
from rfp_dual_queue import RfpDualQueue

KEY='R26BK05553333:000'
GOOD='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/verified.pdf'
WRONG='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/manifest-only.pdf'
RAW=b'stored verified source bytes for scanner'
SHA=hashlib.sha256(RAW).hexdigest()
BASE={'attachments':{'ok':True,'complete':True,'count':1,
                     'items':[{'name':'manifest-only.pdf','url':WRONG}]},
      'noticeDocuments':{'ok':True,'complete':True},
      'downloadVerifiedFiles':[{'name':'verified.pdf','url':GOOD,
                                'sha256':SHA,'bytes':len(RAW)}]}

class FakeLedger:
    def __init__(self,present=True):
        self.present=present
        self.reads=[]
    def get_bytes(self,key,**kw):
        self.reads.append(key)
        return RAW if self.present and key==cache_key('official_attachment',GOOD) else None
    def link_attachment(self,*args,**kw):pass
    def record(self,*args,**kw):pass

class Forbidden:
    def open(self,*args,**kw):
        raise AssertionError('scanner must NEVER access official URL')

with tempfile.TemporaryDirectory() as tmp:
    q=RfpDualQueue(Path(tmp)/'queue.sqlite3')
    q.enqueue([('R26BK05553333','000','2099-12-31')],'fp')
    key,_=q.claim_download()
    q.downloaded(key,BASE,1,1)
    claimed=q.claim_ready(1)
    assert len(claimed)==1
    def fixed_text(name,raw):
        assert name=='verified.pdf' and raw==RAW
        return ('입찰공고 업무와 계약조건 및 인력요건을 확인합니다. ' * 5,
                {'sourceComplete':True},True)
    with patch.dict(os.environ,{'WORKLINKS_RFP_DUAL_SCAN_ONLY':'1',
                                 'WORKLINKS_RFP_DUAL_QUEUE_DB':str(q.path)}), \
         patch.object(reader,'active_rfp_ledger',return_value=FakeLedger()), \
         patch.object(reader,'OPENER',Forbidden()), \
         patch.object(reader,'extract_cached_text',side_effect=fixed_text), \
         patch.object(reader,'extract_staffing_roles',return_value=[]), \
         patch.object(reader,'extract_staffing_facts',return_value=[]), \
         patch.object(reader,'preserve_unclassified_qualification',
                      return_value={'sourceTextScanComplete':True}), \
         patch.object(live,'record',return_value=None):
        result=reader.process(KEY.split(':')[0],KEY.split(':')[1],metadata=BASE)
    assert result['status']=='text_extracted_requires_review',result
    assert [x['name'] for x in result['files']]==['verified.pdf'],result['files']
    assert result['files'][0]['sourceSha256']==SHA,result['files']
    assert not any(x.get('sourceUrl')==WRONG for x in result['files'])
    q.scan_finished(key,True)
    assert q.stats()['scan']['done']==1

# Missing/changed archived bytes cannot be treated as successfully scanned:
# scanner explicitly returns the notice to the download lane without HTTP.
with tempfile.TemporaryDirectory() as tmp:
    q=RfpDualQueue(Path(tmp)/'queue.sqlite3')
    q.enqueue([('R26BK05553333','000','2099-12-31')],'fp')
    key,_=q.claim_download()
    q.downloaded(key,BASE,1,1)
    q.claim_ready(1)
    ledger=FakeLedger(present=False)
    with patch.dict(os.environ,{'WORKLINKS_RFP_DUAL_SCAN_ONLY':'1',
                                 'WORKLINKS_RFP_DUAL_QUEUE_DB':str(q.path)}), \
         patch.object(reader,'active_rfp_ledger',return_value=ledger), \
         patch.object(reader,'OPENER',Forbidden()), \
         patch.object(live,'record',return_value=None):
        result=reader.process(KEY.split(':')[0],KEY.split(':')[1],metadata=BASE)
    assert result['status']=='download_not_verified',result
    assert result['sourceOriginalMissing'] is True
    with q.connect() as db:
        state=db.execute('SELECT download_status,scan_status FROM rfp_dual_notices WHERE notice_key=?',(key,)).fetchone()
    assert state==('pending','pending'),state

print('RFP_VERIFIED_DOWNLOADER_HANDOFF_AND_NO_NETWORK_SCAN=PASS')
