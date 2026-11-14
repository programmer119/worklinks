#!/usr/bin/env python3
"""No-network regression: independently refill 8 slots and pass real scan metadata."""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import os,sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rfp_download_worker as worker
import refresh_worklinks_rfp as reader

class FakeQueue:
    def __init__(self,rows):
        self.pending=list(rows)
        self.lock=threading.Lock()
    def claim_download(self,ready_manifest=False):
        assert ready_manifest
        with self.lock:
            return self.pending.pop(0) if self.pending else None

with patch.object(worker,'WORKERS',2),patch.object(worker,'BULK_ENABLED',True):
    slow_release=threading.Event()
    fast_done=threading.Event()
    next_started=threading.Event()
    def fake_download(queue,claim,halt):
        if claim[0]=='slow':
            assert slow_release.wait(4),'slow worker deliberately blocked too long'
        elif claim[0]=='fast':
            fast_done.set()
        elif claim[0]=='next':
            next_started.set()
        return True
    queue=FakeQueue([('slow',''),('fast',''),('next','')])
    halt=threading.Event()
    with patch.object(worker,'download_one',side_effect=fake_download):
        with ThreadPoolExecutor(max_workers=2) as pool:
            inflight={}
            assert worker.refill_download_slots(queue,pool,inflight,halt)==2
            finished,_=wait(tuple(inflight),timeout=3,return_when=FIRST_COMPLETED)
            assert fast_done.is_set()
            assert len(finished)==1
            for future in finished:
                assert inflight.pop(future)[0]=='fast'
                assert future.result() is True
            assert worker.refill_download_slots(queue,pool,inflight,halt)==1
            assert next_started.wait(2),'new notice did not start with old notice running'
            assert not slow_release.is_set(),'barrier waited for slowest notice'
            slow_release.set()
            for future in inflight:
                assert future.result(timeout=3) is True

no,ordinal='R26BK01800329','000'
meta={'ok':True,'attachments':{'ok':True,'complete':True,
       'items':[{'name':'terms.pdf',
        'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/terms.pdf'}]},
       'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
claims=[(no+':'+ordinal,'2099-12-31',meta)]
index=reader.dual_scan_metadata_by_notice(claims)
assert index[(no,ordinal)] is meta
assert index.get(no+':'+ordinal) is None
text=('입찰 참가 자격과 개발자 근무 계획을 확인한다. ' * 12)
with tempfile.TemporaryDirectory() as root:
  with patch.dict(os.environ,{'WORKLINKS_RFP_DUAL_SCAN_ONLY':'1',
               'WORKLINKS_RFP_DUAL_QUEUE_DB':str(Path(root)/'status.sqlite3')}),\
       patch.object(reader,'download',return_value=b'verified-official-file'),\
       patch.object(reader,'extract_cached_text',
                    return_value=(text,{'sourceComplete':True},False)),\
       patch.object(reader,'parse_clauses',return_value=([],[])),\
       patch.object(reader,'extract_rule_candidates',return_value=[]),\
       patch.object(reader,'extract_staffing_roles',return_value=[]),\
       patch.object(reader,'extract_staffing_facts',return_value=[]):
      result=reader.process(no,ordinal,metadata=index[(no,ordinal)])
      assert result['status']=='text_extracted_requires_review',result
      assert result['files'][0]['readable'] is True,result
print('RFP_EIGHT_SLOTS_INDEPENDENT_AND_SCANNER_METADATA_VERIFIED=PASS',flush=True)
