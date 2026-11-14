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
now=datetime.datetime(2026,11,14,12,0,tzinfo=KST)
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
assert counts=={'total':6,'completed':1,'remaining':5,'rescanRequired':2,'legacy':2,
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
print('WORKLINKS_RFP_RESCAN_PROGRESS_REGRESSION=PASS',counts)


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
