#!/usr/bin/env python3
"""Triggered version upgrades rescan legacy, never consume first-scan slots."""
import datetime as dt
import os
import runpy
from pathlib import Path

root=Path(__file__).resolve().parents[1]
m=runpy.run_path(str(root/'scripts/refresh_worklinks_rfp.py'),run_name='upgrade_queue_test')
today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
future=(today+dt.timedelta(days=3)).strftime('%Y%m%d')+'1400'
past=(today-dt.timedelta(days=3)).strftime('%Y%m%d')+'1400'
rows=[dict(bidNo='R26BK'+str(n).zfill(8),order='000',closes=deadline,kind='servc') for n,deadline in
      [(1,future),(2,future),(3,future),(4,past),(5,future),(6,future),(7,future)]]
versions=(m['CLASSIFICATION_VERSION'],m['HWPX_READER_VERSION'],
          m['STAFFING_ROLE_SCAN_VERSION'],m['STAFFING_FACT_SCAN_VERSION'])
def previous():
    return dict(status='text_extracted_requires_review',
      checkedAt='2026-10-01T00:00:00+00:00',
      classificationVersion=versions[0],hwpxReaderVersion=versions[1],
      staffingRoleScanComplete=True,readableDocumentCount=1,
      files=[dict(name='request.pdf',readable=True,sourceTextScanComplete=True,
                  sourceSha256='a'*64,staffingRoleScanVersion=versions[2],
                  staffingFactScanVersion=versions[3])])
saved={r['bidNo']+':000':previous() for r in rows if r['bidNo']!='R26BK00000007'}
saved['R26BK00000001:000']['classificationVersion']=versions[0]-1
saved['R26BK00000002:000']['files'][0]['staffingFactScanVersion']=versions[3]-1
saved['R26BK00000003:000']['classificationVersion']=versions[0]-1
saved['R26BK00000003:000']['reviewComplete']=True
saved['R26BK00000004:000']['classificationVersion']=versions[0]-1
saved['R26BK00000005:000']={'status':'not_scanned','files':[]}
saved['R26BK00000006:000']['classificationVersion']=versions[0]-1
saved['R26BK00000006:000']['lastAttemptAt']=dt.datetime.now(dt.timezone.utc).isoformat()
saved['R26BK00000006:000']['lastAttemptReaderFingerprint']=':'.join(str(n) for n in
    (versions[0],versions[1],versions[2],versions[3]))

def fetch(url):
    from urllib.parse import parse_qs,urlsplit
    offset=int(parse_qs(urlsplit(url).query)['offset'][0])
    return {'ok':True,'totalCount':len(rows),'items':rows[offset:offset+500]}
m['discover'].__globals__['fetch_json']=fetch
previous_env=os.environ.get('WORKLINKS_RFP_UPGRADE_ONLY')
try:
    os.environ['WORKLINKS_RFP_UPGRADE_ONLY']='1'
    chosen=m['discover'](8,saved,targets=set())
finally:
    if previous_env is None:os.environ.pop('WORKLINKS_RFP_UPGRADE_ONLY',None)
    else:os.environ['WORKLINKS_RFP_UPGRADE_ONLY']=previous_env
keys={no+':'+order for no,order,_ in chosen}
assert keys=={'R26BK00000001:000','R26BK00000002:000','R26BK00000003:000'},(keys,chosen)
# Initial scans remain eligible through the independent ordinary scanner.
ordinary=m['discover'](8,saved,targets=set())
ordinary_keys={no+':'+order for no,order,_ in ordinary}
assert {'R26BK00000005:000','R26BK00000007:000'}.issubset(ordinary_keys),ordinary_keys
print('WORKLINKS_RFP_UPGRADE_ONLY_QUEUE_REGRESSION=PASS',sorted(keys))
