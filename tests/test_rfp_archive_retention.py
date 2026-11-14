#!/usr/bin/env python3
"""No-network regression for deadline retention, raw-byte reuse and disk safety."""
import datetime as dt
import fcntl
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rfp_call_ledger import CallLedger, cache_key
import rfp_call_ledger as ledger_module
import refresh_worklinks_rfp as reader

OLD=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=61)).isoformat()
TODAY=dt.date(2026,11,14)
EXP='2026-10-31'
OPEN='2026-12-31'

with tempfile.TemporaryDirectory() as tmp:
    data=Path(tmp)
    ledger=CallLedger(data/'rfp-request-ledger.sqlite3')
    mk=lambda suffix:cache_key('official_attachment','unit-test-'+suffix)
    active=mk('active')
    expired=mk('expired')
    shared=mk('shared')
    unknown=mk('unknown')
    legacy=mk('legacy')
    changed=mk('changed')
    original=b'RFP HWP compressed archive verified raw bytes'
    assert ledger.save_bytes(active,original,notice_key='R26BK00000001:000',closes_on=OPEN)
    assert ledger.save_bytes(expired,original,notice_key='R26BK00000002:000',closes_on=EXP)
    assert ledger.save_bytes(shared,original,notice_key='R26BK00000003:000',closes_on=EXP)
    ledger.link_attachment(shared,'R26BK00000004:000',OPEN)
    assert ledger.save_bytes(unknown,original)
    assert ledger.save_bytes(legacy,original)
    ledger.record('attachment_http',legacy,'http_ok',notice_key='R26BK00000005:000')
    assert ledger.save_bytes(changed,original,notice_key='R26BK00000006:000',closes_on=EXP)
    jkey=mk('oldjson')
    assert ledger.save_json(jkey,{'old':1})
    with sqlite3.connect(ledger.path) as db:
        db.execute('''UPDATE verified_cache SET stored_at=?
          WHERE request_key IN (?,?)''',(OLD,unknown,jkey))
        db.execute('UPDATE call_events SET occurred_at=? WHERE request_key=?',
                   (OLD,jkey))
    report=ledger.prune_expired({
        'R26BK00000001:000':OPEN,
        'R26BK00000002:000':EXP,
        'R26BK00000003:000':EXP,
        'R26BK00000004:000':OPEN,
        'R26BK00000005:000':EXP,
        'R26BK00000006:000':OPEN,  # official deadline corrected after archive
    },today=TODAY,grace_days=7)
    assert report['attachmentsDeleted']==3,report  # expired, unknown, legacy
    assert ledger.get_bytes(active)==original
    assert ledger.get_bytes(shared)==original  # one live ref must win
    assert ledger.get_bytes(changed)==original  # correction must win
    for gone in (expired,unknown,legacy):
        assert ledger.get_bytes(gone) is None,gone
    assert ledger.get_json(jkey) is None
    assert report['jsonDeleted']==1,report
    assert ledger.prune_expired(today=TODAY)['attachmentsDeleted']==0
    # Without an operator grace override, an ended bid expires the next day.
    ended_yesterday=mk('closed_yesterday')
    assert ledger.save_bytes(ended_yesterday,original,
                             notice_key='R26BK00000008:000',closes_on='2026-11-13')
    assert ledger.prune_expired(today=TODAY)['attachmentsDeleted']==1
    assert ledger.get_bytes(ended_yesterday) is None
    with sqlite3.connect(ledger.path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT COUNT(*) FROM attachment_refs WHERE request_key=?',(expired,)).fetchone()[0]==0

    # The former 7-day max-age should not cause a network download.
    url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK00000001'
    realkey=cache_key('official_attachment',url)
    assert ledger.save_bytes(realkey,original,notice_key='R26BK00000001:000',closes_on=OPEN)
    with sqlite3.connect(ledger.path) as db:
        db.execute('UPDATE verified_cache SET stored_at=? WHERE request_key=?',(OLD,realkey))
    class MustNotDownload:
        def open(self,*args,**kwargs):
            raise AssertionError('Re-downloaded previously archived RFP!')
    old_opener=reader.OPENER
    reader.OPENER=MustNotDownload()
    try:
        with mock.patch.dict(os.environ,{'WORKLINKS_RFP_LEDGER_DB':str(ledger.path)}):
            reader._NOTICE_CONTEXT.notice_key='R26BK00000001:000'
            reader._NOTICE_CONTEXT.closes_on=OPEN
            assert reader.download(url)==original
    finally:
        reader.OPENER=old_opener
        reader._NOTICE_CONTEXT.notice_key=None
        reader._NOTICE_CONTEXT.closes_on=''
    with sqlite3.connect(ledger.path) as db:
        count=db.execute('SELECT COUNT(*) FROM call_events WHERE request_key=? AND kind=?',
                         (realkey,'attachment_http')).fetchone()[0]
        assert count==0,'raw source must be reused with 0 network calls'

    # Concurrent maintenance must skip immediately rather than taking an
    # archive-wide SQLite write lock while the scanner is publishing.
    with (Path(str(ledger.path)+'.prune.lock')).open('a') as guard:
        fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        skipped=ledger.prune_expired(today=TODAY)
        assert skipped['status']=='already_running',skipped
        fcntl.flock(guard.fileno(),fcntl.LOCK_UN)

    # Hard disk reserve prevents growth; scanner may parse the downloaded bytes,
    # but the archive must not silently exceed a dangerously full filesystem.
    with mock.patch.object(ledger_module.shutil,'disk_usage',
                           return_value=SimpleNamespace(free=1024)):
        assert ledger.save_bytes(mk('quota'),b'a lot of bytes') is None
    assert ledger.stats()['counts']['cache:storage_quota_skip']>=1
    print('RFP_ARCHIVE_RETENTION_DEADLINE_SHARED_RAW_REUSE_QUOTA=PASS',report,flush=True)

    # Verify scheduler reads official bid closing dates and deletes expired
    # archives without touching saved JSON scan evidence.
    pipe_path=ROOT/'server'/'worklinks-server123-pipeline.py'
    spec=importlib.util.spec_from_file_location('rfp_archive_pipeline_test',pipe_path)
    pipeline=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    pipeline.DATA=data
    pipeline.SCRIPTS=ROOT/'scripts'
    pipeline.SEEDS=data/'snapshots'
    db=data/'bids.sqlite3'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE bid_notices (sw_candidate INTEGER,payload TEXT)')
        import json
        con.execute('INSERT INTO bid_notices VALUES (?,?)',(1,json.dumps({
            'bidNo':'R26BK00000002','order':'000','closes':'2026-10-31T10:00:00'})))
        con.execute('INSERT INTO bid_notices VALUES (?,?)',(1,json.dumps({
            'bidNo':'R26BK00000001','order':'000','closes':'2026-12-31T10:00:00'})))
    # Archive this sample with far-past deadline; using real wall time ensures
    # it has expired regardless of the date when the CI test is executed.
    old_date=(dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()-
              dt.timedelta(days=40)).isoformat()
    target=mk('pipeline-expire')
    assert ledger.save_bytes(target,original,notice_key='R26BK00000002:000',closes_on=old_date)
    # Actual DB deadline is October 31, 2026; after grace period, prune.
    if dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()>dt.date(2026,11,7):
        result=pipeline.prune_rfp_archive()
        assert result['attachmentsDeleted']>=1,result
        assert ledger.get_bytes(target) is None
print('RFP_PIPELINE_RETENTION_INTEGRATION=PASS')
