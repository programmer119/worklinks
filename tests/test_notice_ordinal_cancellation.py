#!/usr/bin/env python3
"""No-network integration: official cancellation, latest ordinal and raw cleanup."""
import datetime as dt
import json
import os
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
from rfp_dual_queue import RfpDualQueue
from rfp_call_ledger import CallLedger,cache_key

crawler=runpy.run_path(str(ROOT/'server/g2b-full-crawler.py'),run_name='test_notice_source')
proxy=runpy.run_path(str(ROOT/'server/g2b-proxy.py'),run_name='test_notice_api')
raw={'bidNtceNo':'R26BK01817648','bidNtceOrd':'002',
     'ntceKindNm':'취소공고','bidNtceNm':'푸드테크 조리 자동화 시스템 구매',
     'bidNtceDt':'2026-11-12 16:40:30','bidClseDt':'2026-11-20 17:00:00'}
assert crawler['compact'](raw,'thng')['noticeKind']=='취소공고'
assert crawler['compact'](raw,'thng')['state']=='취소공고'
assert proxy['format_bid'](raw,'thng')['state']=='취소공고'
assert crawler['compact']({**raw,'ntceKindNm':'변경공고'},'thng')['state']=='변경공고'

with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    bids_db=folder/'bids.sqlite3'
    with sqlite3.connect(bids_db) as db:
        db.execute("""CREATE TABLE bid_notices(
          kind TEXT NOT NULL,bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,
          payload TEXT NOT NULL,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
          sw_candidate INTEGER NOT NULL DEFAULT 0,changed_at TEXT NOT NULL DEFAULT '',
          PRIMARY KEY(kind,bid_no,bid_ord))""")
        db.execute("""CREATE TABLE crawl_windows(
          kind TEXT,day TEXT,expected INTEGER,received INTEGER,pages INTEGER,
          checked_at TEXT,PRIMARY KEY(kind,day))""")
        db.execute("""INSERT INTO crawl_windows
          VALUES('thng','20261112',3,3,1,'2026-11-15')""")
        for no,ordinal,kind,sw in [
           ('R26BK01817648','000','',1),
           ('R26BK01817648','001','',1),
           ('R26BK01817648','002','',1),
           ('R26BK01817649','000','등록공고',1),
           ('R26BK01817649','001','등록공고',0)]:
            saved={'kind':'thng','bidNo':no,'order':ordinal,
                   'title':'시스템 구축','posted':'2026-11-12',
                   'closes':'2026-11-20 17:00:00','state':kind}
            db.execute("""INSERT INTO bid_notices
              (kind,bid_no,bid_ord,payload,first_seen,last_seen,sw_candidate)
              VALUES(?,?,?,?,?,?,?)""",
              ('thng',no,ordinal,json.dumps(saved,ensure_ascii=False),
               '2026-11-12','2026-11-15',sw))
    # Reconstruct the official kind using ONLY a verified, already-saved
    # crawler page. The operation cannot make government HTTP calls.
    source=[]
    for ordinal,state in [('000','등록공고'),('001','변경공고'),('002','취소공고')]:
        source.append({**raw,'bidNtceOrd':ordinal,'ntceKindNm':state})
    with patch.dict(os.environ,{'WORKLINKS_RFP_DISK_RESERVE_MB':'512',
                                'WORKLINKS_RFP_LEDGER_MAX_MB':'256'}):
        ledger=CallLedger(folder/'rfp-request-ledger.sqlite3')
        assert ledger.save_json(
            cache_key('crawler_v1','thng','20261112',1,999),
            {'total':3,'items':source}) is not None
        with patch.dict(os.environ,{'WORKLINKS_RFP_LEDGER_DB':str(ledger.path)}):
            with sqlite3.connect(bids_db) as db:
                assert crawler['recover_cached_notice_kind'](db)==3
            with patch.object(reader,'ROOT',folder):
                latest=reader.latest_notice_versions()
                selected=[o for page in reader.iter_saved_sw_pages() for o in page]
            assert latest['R26BK01817648']=={
                'order':2,'sw':True,'cancelled':True},latest
            assert latest['R26BK01817649']['sw'] is False
            assert not selected,selected
            with patch.dict(proxy,{'G2B_DB_PATH':str(bids_db)}):
                # SQL must not revive any old SW ordinal when latest is a
                # cancellation or a newer non-SW procurement notice.
                found=proxy['query_saved_bids'](50,0,only_sw=True)
                assert found['totalCount']==0 and not found['items'],found
                inventory=proxy['query_saved_open_inventory']()
                assert not inventory['items'],inventory
            queue=RfpDualQueue(folder/'rfp-dual-queue.sqlite3')
            queue.enqueue([(raw['bidNtceNo'],x,'2099-12-31') for x in
                           ('000','001','002')],'v1')
            assert queue.retire_superseded(latest)==3
            assert queue.stats()['total']==0
            # 003 is a newly verified revision, not a permanent blacklist.
            with sqlite3.connect(bids_db) as db:
                after={'kind':'thng','bidNo':raw['bidNtceNo'],
                       'order':'003','state':'변경공고','noticeKind':'변경공고',
                       'title':'시스템 구축','closes':'2099-12-31'}
                db.execute("""INSERT INTO bid_notices
                    (kind,bid_no,bid_ord,payload,first_seen,last_seen,sw_candidate)
                    VALUES(?,?,?,?,?,?,1)""",
                    ('thng',raw['bidNtceNo'],'003',
                     json.dumps(after,ensure_ascii=False),'2026-11-15','2026-11-15'))
            with patch.object(reader,'ROOT',folder):
                latest=reader.latest_notice_versions()
                selected=[o for page in reader.iter_saved_sw_pages() for o in page]
            assert latest[raw['bidNtceNo']]=={
                 'order':3,'sw':True,'cancelled':False}
            assert len(selected)==1 and selected[0]['order']=='003',selected
            queue.enqueue([(raw['bidNtceNo'],'003','2099-12-31')],'v1')
            assert queue.retire_superseded(latest)==0
            assert queue.claim_download()[0]==raw['bidNtceNo']+':003'
        # Standalone physical-byte retention: canceled-only payload pruned,
        # but any bytes shared with a valid, different bid must be preserved.
        cancel_key=cache_key('official_attachment','https://example.com/only-cancelled')
        shared_key=cache_key('official_attachment','https://example.com/shared')
        with patch.dict(os.environ,{'WORKLINKS_RFP_DISK_RESERVE_MB':'512'}):
            assert ledger.save_bytes(cancel_key,b'CANCELLED_BYTES',
                 notice_key='R26BK01817648:002',closes_on='2099-12-31')
            assert ledger.save_bytes(shared_key,b'SHARED_BYTES',
                 notice_key='R26BK01817648:001',closes_on='2099-12-31')
            ledger.link_attachment(shared_key,'R26BK01817651:000','2099-12-31')
            report=ledger.prune_expired(
                today=dt.date(2026,11,15),compact=False,
                cancelled_notice_numbers={'R26BK01817648'})
            assert report['attachmentsDeleted']>=1,report
            assert ledger.get_bytes(cancel_key) is None
            assert ledger.get_bytes(shared_key)==b'SHARED_BYTES'

now=dt.datetime(2026,11,15,tzinfo=dt.timezone(dt.timedelta(hours=9)))
versions=[
  ('R26BK01700001','000',{'closes':'2026-11-30','state':'등록공고'}),
  ('R26BK01700001','001',{'closes':'2026-11-30','state':'변경공고'}),
  ('R26BK01700002','000',{'closes':'2026-11-30','state':'등록공고'}),
  ('R26BK01700002','002',{'closes':'2026-11-30','noticeKind':'취소공고'})]
versions_manifest=dict(classificationVersion=23,staffingRoleScanVersion=4,
                       staffingFactScanVersion=2,hwpxReaderVersion=3)
report=proxy['rfp_progress_from_rows'](versions,{},versions_manifest,asof=now)
assert report['counts']['total']==1,report
print('WORKLINKS_NOTICE_LATEST_ORDINAL_CANCEL_ARCHIVE_INTEGRATION=PASS')
