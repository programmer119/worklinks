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
                'unscanned':1,'failed':1,'incomplete':1,'unknownDeadline':1},counts
assert result['stages']['classification']=={'total':6,'done':3,'remaining':3},result['stages']
assert result['stages']['facts']['done']==2,result['stages']
assert result['stages']['hwpx']=={'total':0,'done':0,'remaining':0},result['stages']
assert result['remainingPercent']==83.3 and result['rescanPercent']==33.3,result
assert deadline('202611151230').hour==12
assert deadline('20261115').hour==23
assert deadline('') is None
assert calc([],index,latest,asof=now)['rescanPercent'] is None
print('WORKLINKS_RFP_RESCAN_PROGRESS_REGRESSION=PASS',counts)
