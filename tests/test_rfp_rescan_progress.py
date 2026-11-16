#!/usr/bin/env python3
"""Read-only notice progress: immutable test clock, no public API calls."""
import datetime
from pathlib import Path
import runpy

root=Path(__file__).resolve().parents[1]
p=runpy.run_path(str(root/'server/g2b-proxy.py'),run_name='rescan_test')
calc=p['rfp_progress_from_rows']
deadline=p['rfp_deadline_kst']
KST=datetime.timezone(datetime.timedelta(hours=9))
now=datetime.datetime(2026,11,13,12,0,tzinfo=KST)
latest=dict(classificationVersion=23,staffingRoleScanVersion=4,staffingFactScanVersion=2,hwpxReaderVersion=3)
def notice(bid,end):
    return (bid,'000',{'kind':'servc','bidNo':bid,'order':'000','closes':end})
def good(file='request.pdf'):
    return dict(status='text_extracted_requires_review',classificationVersion=23,
      hwpxReaderVersion=2,manifestComplete=True,staffingRoleScanComplete=True,
      files=[dict(name=file,readable=True,sourceTextScanComplete=True,
                  qualificationScanTruncated=False,staffingRoleScanVersion=4,
                  staffingFactScanVersion=2)])
rows=[
    notice('R26BK00000001','2026-11-15 16:00'),
    notice('R26BK00000002','2026-11-15 10:00'),
    notice('R26BK00000003','2026-11-15 10:00'),
    notice('R26BK00000004','2026-11-15 10:00'),
    notice('R26BK00000005','2026-11-15 10:00'),
    notice('R26BK00000006','2026-11-15 10:00'),
    notice('R26BK00000007','2026-11-13 10:00'),
    notice('R26BK00000008',''),
    notice('R26BK00000001','2026-11-15 16:00'), # duplicate source category
]
index={
 'R26BK00000001:000':good(), # no HWPX in PDF-only document
 'R26BK00000002:000':{**good(),'classificationVersion':22},
 'R26BK00000003:000':{**good(),'files':[{**good()['files'][0],'staffingFactScanVersion':1}]},
 'R26BK00000004:000':{**good(),'staffingRoleScanComplete':False},
 'R26BK00000005:000':{'status':'metadata_fetch_failed','files':[]},
 # R26BK00000006 absent = never scanned
}
result=calc(rows,index,latest,asof=now)
counts=result['counts']
assert counts=={'total':6,'eligible':6,'excluded':0,'completed':1,'remaining':5,'rescanRequired':2,'legacy':2,
                'unscanned':1,'failed':1,'incomplete':1,'unknownDeadline':1,
                'unknownDeadlineCompleted':0,'unknownDeadlinePending':1},counts
assert result['stages']['classification']=={'total':6,'done':3,'remaining':3},result['stages']
assert result['stages']['facts']['done']==2,result['stages']
assert result['stages']['hwpx']=={'total':0,'done':0,'remaining':0},result['stages']
assert result['remainingPercent']==83.3 and result['rescanPercent']==33.3,result
assert deadline('202611151230').hour==12
assert deadline('20261115').hour==23
assert deadline('') is None
checked_unknown=calc(rows,{**index,'R26BK00000008:000':good()},latest,asof=now)['counts']
assert checked_unknown['unknownDeadlineCompleted']==1
assert checked_unknown['unknownDeadlinePending']==0
assert calc([],index,latest,asof=now)['rescanPercent'] is None
# A verified no-file notice is terminally excluded from actionable scan.
# It must not be falsely marked failed or first-time unscanned.
no_file={'R26BK00000005:000','R26BK00000006:000'}
fixed=calc(rows,index,latest,asof=now,excluded_keys=no_file)['counts']
assert fixed['total']==6 and fixed['eligible']==4 and fixed['excluded']==2,fixed
assert fixed['completed']==1 and fixed['remaining']==3,fixed
assert fixed['failed']==0 and fixed['unscanned']==0,fixed
assert fixed['legacy']==2 and fixed['incomplete']==1,fixed
assert fixed['completed']+fixed['remaining']+fixed['excluded']==fixed['total'],fixed
print('WORKLINKS_RFP_NO_FILE_BUCKET_SEPARATION=PASS',fixed)
print('WORKLINKS_RFP_RESCAN_PROGRESS_REGRESSION=PASS',counts)

# The global progress must count stale OCR files as a version-triggered rescan,
# not lose them in the generic incomplete bucket. Only live notices with >24h
# remain eligible, exactly like the independent OCR cached-original worker.
ocr_latest=dict(latest,ocrReaderVersion='pdf25-blank-hwpx-embedded-image-v12-provenance-rescan')
ocr_file=dict(name='archive.zip',readable=False,sourceTextScanComplete=False,
    errorCategory='pdf_ocr_incomplete',
    lastReaderAttemptVersion='pdf25-blank-hwpx-embedded-image-v11-finish-first')
ocr_record={**good(), 'files':[ocr_file]}
ocr_id='R26BK00000991'
ocr_notice=notice(ocr_id,'2026-11-18 16:00')
near_id='R26BK00000992'
near_notice=notice(near_id,'2026-11-14 11:59')
exact_id='R26BK00000993'
exact_notice=notice(exact_id,'2026-11-14 12:00')
ocr_rows=[ocr_notice,near_notice,exact_notice]
ocr_index={ocr_id+':000':ocr_record,
    near_id+':000':ocr_record,exact_id+':000':ocr_record}
new_report=calc(ocr_rows,ocr_index,ocr_latest,asof=now)
# Server can change eligibility semantics without breaking already-open
# dashboards which validate the stable schema v1 scope token.
assert new_report['scope']=='unexpired_saved_sw_bid_notices',new_report
assert new_report['managementScope']=='actionable_saved_sw_bid_notices_24h',new_report
assert new_report['minimumHoursToDeadline']==24,new_report
assert new_report['counts']['total']==1,new_report
assert new_report['counts']['legacy']==1,new_report
assert new_report['counts']['rescanRequired']==1,new_report
assert new_report['ocrRescan']['targetNotices']==1,new_report
assert new_report['ocrRescan']['targetFiles']==1,new_report
upgraded={**ocr_record,'files':[{**ocr_file,
    'lastReaderAttemptVersion':ocr_latest['ocrReaderVersion']}]}
rechecked=calc([ocr_notice],{ocr_id+':000':upgraded},ocr_latest,asof=now)
assert rechecked['counts']['legacy']==0,rechecked
assert rechecked['counts']['incomplete']==1,rechecked
assert rechecked['ocrRescan']['targetFiles']==0,rechecked
print('RFP_OCR_READER_VERSION_RESCAN_AND_24H_COHORT=PASS')

# The authoritative queue must not treat a partially OCR-failed ZIP notice
# as verified-complete merely because a different PDF sibling was readable.
import sys
sys.path.insert(0,str(root/'scripts'))
import rfp_management_reconcile as reconcile
mixed={**good(),'files':good()['files']+[ocr_file]}
assert reconcile.latest_complete(mixed,ocr_latest) is False
assert reconcile.latest_complete(good(),ocr_latest) is True
print('RFP_OCR_FAILED_MEMBER_QUEUE_RECONCILIATION=PASS')


# One completed notice becomes visible without waiting for all eight batch tasks.
import os
import tempfile
import sqlite3
from unittest.mock import patch
reader=runpy.run_path(str(root/'scripts/refresh_worklinks_rfp.py'),run_name='test_notice_checkpoints')
writer=reader['publish_notice_checkpoint']
overlay=p['read_rfp_notice_checkpoints']
latest_reader=dict(classificationVersion=reader['CLASSIFICATION_VERSION'],
    staffingRoleScanVersion=reader['STAFFING_ROLE_SCAN_VERSION'],
    staffingFactScanVersion=reader['STAFFING_FACT_SCAN_VERSION'],
    hwpxReaderVersion=reader['HWPX_READER_VERSION'])
def completed_scan(checked):
    return dict(status='text_extracted_requires_review',
        checkedAt=checked,classificationVersion=latest_reader['classificationVersion'],
        hwpxReaderVersion=latest_reader['hwpxReaderVersion'],
        manifestComplete=True,readableDocumentCount=1,
        files=[dict(name='rfp.pdf',readable=True,sourceSha256='a'*64,
          sourceTextScanComplete=True,qualificationScanTruncated=False,
          staffingRoleScanTruncated=False,
          staffingRoleScanVersion=latest_reader['staffingRoleScanVersion'],
          staffingFactScanVersion=latest_reader['staffingFactScanVersion'])])
with tempfile.TemporaryDirectory() as temp:
    dbpath=str(Path(temp)/'rfp-notice-progress.sqlite3')
    timestamp='2026-11-14T07:00:01+00:00'
    ids=['R26BK01800001:000','R26BK01800002:000']
    bids=[notice(x.split(':')[0],'2026-11-15 10:00') for x in ids]
    with patch.dict(os.environ,{'WORKLINKS_RFP_NOTICE_PROGRESS_DB':dbpath}):
        assert writer(ids[0],completed_scan(timestamp),'test-v1')
        with patch.dict(overlay.__globals__,{'G2B_DB_PATH':str(Path(temp)/'bids.sqlite3')}):
            index_one,first_recent,first_pending=overlay({})
            assert len(first_recent)==1 and first_pending==1
            result_one=calc(bids,index_one,latest_reader,asof=now)['counts']
            assert result_one['completed']==1 and result_one['unscanned']==1,result_one
            assert writer(ids[1],completed_scan('2026-11-14T07:00:04+00:00'),'test-v1')
            index_two,second_recent,second_pending=overlay({})
            result_two=calc(bids,index_two,latest_reader,asof=now)['counts']
            assert result_two['completed']==2 and second_pending==2,result_two
            # The complete index now supersedes the checkpoint, even when
            # an earlier in-flight batch is still updating its local scan.
            latest_archived=completed_scan('2026-11-14T07:01:00+00:00')
            index_archived,changes,pending=overlay({ids[0]:latest_archived})
            assert index_archived[ids[0]]==latest_archived and pending==1
            # Replaying an older event cannot move a verified notice backward.
            assert writer(ids[0],completed_scan('2026-11-14T06:59:59+00:00'),'test-v1')
            _,_,pending2=overlay({ids[0]:latest_archived})
            assert pending2==1
print('WORKLINKS_RFP_EACH_NOTICE_IMMEDIATE_PROGRESS=PASS')

# The UI's three progress rows are real per-notice queue counts, not animation.
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)/'rfp-dual-queue.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE rfp_dual_notices (notice_key TEXT PRIMARY KEY, download_status TEXT, scan_status TEXT)')
        conn.execute('CREATE TABLE rfp_bulk_manifests (notice_key TEXT PRIMARY KEY)')
        conn.executemany('INSERT INTO rfp_dual_notices VALUES (?,?,?)',[
            ('notice-a','ready','done'),('notice-b','fetching','scanning'),
            ('notice-c','pending','pending')])
        conn.executemany('INSERT INTO rfp_bulk_manifests VALUES (?)',[
            ('notice-a',),('notice-b',),('old-retired-notice',)])
    lanes=p['rfp_dual_lane_progress'](str(path))
    assert lanes['available'] is True,lanes
    assert lanes['manifest']=={'total':3,'done':2},lanes
    assert lanes['download']['done']==1 and lanes['download']['active']==1,lanes
    assert lanes['scan']['done']==1 and lanes['scan']['active']==1,lanes
print('WORKLINKS_RFP_METADATA_DOWNLOAD_SCAN_LANES=PASS')

# All official attachment lists may be complete while many downloads are still
# pending. Pending downloads must NOT appear as active manifest collection.
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)/'cohort-queue.sqlite3'
    ids=['R26BK00009001:000','R26BK00009002:000','R26BK00009003:000']
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE rfp_dual_notices (notice_key TEXT PRIMARY KEY, download_status TEXT, scan_status TEXT, metadata_json TEXT, updated_at TEXT)')
        conn.execute('CREATE TABLE rfp_bulk_manifests (notice_key TEXT PRIMARY KEY)')
        conn.executemany('INSERT INTO rfp_dual_notices VALUES (?,?,?,?,?)', [
            (ids[0],'ready','done','{}',''),
            (ids[1],'pending','pending','{}',''),
            (ids[2],'retry','pending','{}','')])
        conn.executemany('INSERT INTO rfp_bulk_manifests VALUES (?)',
                         [(key,) for key in ids])
    lanes=p['rfp_cohort_lanes'](str(path),set(ids),{ids[0]})
    assert lanes['manifest']=={'total':3,'done':3,'remaining':0,
        'pending':0,'active':0,'failed':0},lanes
    assert lanes['download']['failed']==1,lanes
print('WORKLINKS_RFP_MANIFEST_DONE_DOWNLOAD_PENDING_NOT_ACTIVE=PASS')

# A verified empty official attachment list is a terminal scan exclusion.
# It is NOT a scanner failure and NOT a stale previously-completed scan.
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)/'empty-cohort.sqlite3'
    ids=['R26BK00009101:000','R26BK00009102:000']
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE rfp_dual_notices (notice_key TEXT PRIMARY KEY, download_status TEXT, scan_status TEXT, metadata_json TEXT, updated_at TEXT)')
        conn.execute('CREATE TABLE rfp_bulk_manifests (notice_key TEXT PRIMARY KEY)')
        conn.executemany('INSERT INTO rfp_dual_notices VALUES (?,?,?,?,?)',[
            (ids[0],'ready','done','{}',''),
            (ids[1],'no_attachments','skipped','{}','')])
        conn.executemany('INSERT INTO rfp_bulk_manifests VALUES (?)',
                         [(key,) for key in ids])
    stage=p['rfp_cohort_lanes'](str(path),set(ids),set())
    assert stage['scan']['blockedNoAttachments']==1,stage
    assert stage['scan']['total']==1,stage
    assert stage['scan']['failed']==0,stage
    assert stage['scan']['staleQueueComplete']==1,stage
    assert stage['scan']['active']==0,stage
print('RFP_NO_FILE_SKIPPED_NOT_FAILED_OR_STALE=PASS')


# Regression from live server123 (2026-11-16): a confirmed HTTP 422 notice
# had six previously verified receipts and a completed scan checkpoint. It
# must NOT count both as a successful full download and a confirmed failure.
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'confirmed-overlap.sqlite3'
    ids=['R26BK00009301:000','R26BK00009302:000','R26BK00009303:000']
    missing={'downloadErrorFiles':[{
        'name':'긴급입찰 사유서.hwp',
        'reason':'official_attachment_reference_missing_422',
        'httpStatus':422}],
        'downloadVerifiedFiles':[{'name':'other.pdf','sha256':'a'*64}]}
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE rfp_dual_notices (notice_key TEXT PRIMARY KEY, download_status TEXT, scan_status TEXT, metadata_json TEXT, updated_at TEXT)')
        db.execute('CREATE TABLE rfp_bulk_manifests (notice_key TEXT PRIMARY KEY)')
        db.executemany('INSERT INTO rfp_dual_notices VALUES (?,?,?,?,?)', [
            (ids[0],'error_confirmed','done',json.dumps(missing,ensure_ascii=False),''),
            (ids[1],'ready','done','{}',''),
            (ids[2],'no_attachments','skipped','{}','')])
        db.executemany('INSERT INTO rfp_bulk_manifests VALUES (?)',
                       [(key,) for key in ids])
    lanes=p['rfp_cohort_lanes'](str(path),set(ids),{ids[0],ids[1]})
    download=lanes['download']
    assert download['total']==3 and download['done']==2,lanes
    assert download['errors']==1 and download['processed']==3,lanes
    assert download['done']+download['errors']==download['total'],lanes
    assert download['errorDetails'][0]['noticeKey']==ids[0],lanes
    assert download['errorDetails'][0]['files'][0]['httpStatus']==422,lanes
print('WORKLINKS_CONFIRMED_ORIGINAL_NOT_DOUBLE_COUNTED_AS_SUCCESS=PASS')
