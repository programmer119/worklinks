#!/usr/bin/env python3
"""No-network regression: matching cohort, missing queue, stale done, empty originals."""
import datetime as dt
import json
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rfp_dual_queue import RfpDualQueue
from rfp_management_reconcile import management_scope,latest_complete

KST=dt.timezone(dt.timedelta(hours=9))
NOW=dt.datetime(2026,11,15,10,0,tzinfo=KST)
VERSIONS=dict(classificationVersion=23,staffingRoleScanVersion=4,
              staffingFactScanVersion=2,hwpxReaderVersion=3)
def evidence():
    return dict(status='text_extracted_requires_review',
        checkedAt='2026-11-15T00:00:00+00:00',classificationVersion=23,
        hwpxReaderVersion=3,manifestComplete=True,staffingRoleScanComplete=True,
        files=[dict(name='rfp.pdf',readable=True,sourceTextScanComplete=True,
           qualificationScanTruncated=False,staffingRoleScanTruncated=False,
           staffingRoleScanVersion=4,staffingFactScanVersion=2)])
def bid(no,closes,notice_kind='일반'):
    return (no,'000',json.dumps(dict(closes=closes,noticeKind=notice_kind)))
ids=['R26BK'+str(i).zfill(8) for i in range(1,8)]
keys=[no+':000' for no in ids]
with tempfile.TemporaryDirectory() as tmp:
    data=Path(tmp);snap=data/'snapshots';snap.mkdir()
    (snap/'rfp-scanner-versions.json').write_text(json.dumps(
        dict(ok=True,schemaVersion=1,latest=VERSIONS)),encoding='utf-8')
    valid=evidence()
    outdated={**valid,'classificationVersion':22}
    (snap/'rfp-coverage-index.json').write_text(json.dumps(
        dict(ok=True,byNotice={keys[0]:valid,keys[1]:outdated})),
        encoding='utf-8')
    with sqlite3.connect(data/'bids.sqlite3') as db:
        db.execute('CREATE TABLE bid_notices (bid_no TEXT,bid_ord TEXT,payload TEXT,sw_candidate INTEGER,last_seen TEXT)')
        rows=[bid(ids[i],'2099-12-31') for i in range(4)]+[
            bid(ids[4],''),bid(ids[5],'2026-11-13'),bid(ids[6],'2099-12-31','취소')]
        db.executemany('INSERT INTO bid_notices VALUES (?,?,?,?,?)',
            [(no,ordn,raw,1,'2026-11-15') for no,ordn,raw in rows])
    queue=RfpDualQueue(data/'rfp-dual-queue.sqlite3')
    queue.enqueue([(ids[i],'000','2099-12-31') for i in (1,2)],'v1')
    queue.enqueue([(ids[4],'000','')],'v1')
    with queue.connect() as db:
        db.execute("UPDATE rfp_dual_notices SET download_status='ready',scan_status='done' WHERE notice_key=?",(keys[1],))
        db.execute("UPDATE rfp_dual_notices SET download_status='no_attachments',scan_status='skipped' WHERE notice_key=?",(keys[2],))
    managed,done=management_scope(data,now=NOW)
    assert set(managed)==set(keys[:4]),managed
    assert done=={keys[0]},done
    assert latest_complete(valid,VERSIONS) and not latest_complete(outdated,VERSIONS)
    first=queue.reconcile_management(managed,done,'v1')
    assert first['managed']==4 and first['latestValid']==1,first
    assert first['previouslyValidAdded']==1,first
    assert first['missingAdded']==1,first
    assert first['obsoleteDoneRequeued']==1,first
    assert first['verifiedEmptyBlocked']==1,first
    with queue.connect() as db:
        q={row[0]:row[1:] for row in db.execute(
            'SELECT notice_key,download_status,scan_status FROM rfp_dual_notices')}
    assert len(q)==5 and q[keys[4]]==('pending','pending'),q
    assert q[keys[0]]==('evidence_complete','done'),q
    assert q[keys[1]]==('ready','pending'),q
    assert q[keys[2]]==('no_attachments','skipped'),q
    assert q[keys[3]]==('pending','pending'),q
    assert queue.ready_count()==1
    second=queue.reconcile_management(managed,done,'v1')
    assert second['missingAdded']==0 and second['previouslyValidAdded']==0
    assert second['obsoleteDoneRequeued']==0,second
    proxy=runpy.run_path(str(ROOT/'server/g2b-proxy.py'),run_name='reconcile_fixture')
    lanes=proxy['rfp_dual_lane_progress'](str(data/'rfp-dual-queue.sqlite3'),
                                           cohort=(set(managed),done))
    assert lanes['total']==4 and lanes['scan']['total']==4,lanes
    assert lanes['scan']['done']==1 and lanes['scan']['blockedNoAttachments']==1,lanes
    assert lanes['download']['total']==4 and lanes['download']['done']==3,lanes
    assert lanes['outsideScopeQueue']==1 and lanes['missingIncomplete']==0,lanes
    # Revalidated evidence must stop repeated work without touching originals.
    (snap/'rfp-coverage-index.json').write_text(json.dumps(
        dict(ok=True,byNotice={keys[0]:valid,keys[1]:valid})),encoding='utf-8')
    managed2,done2=management_scope(data,now=NOW)
    third=queue.reconcile_management(managed2,done2,'v1')
    assert third['completedEvidenceReconciled']==1,third
    with queue.connect() as db:
        row=db.execute('SELECT download_status,scan_status FROM rfp_dual_notices WHERE notice_key=?',(keys[1],)).fetchone()
    assert row==('ready','done'),row
print('RFP_MANAGEMENT_SCOPE_RECONCILE=PASS')
