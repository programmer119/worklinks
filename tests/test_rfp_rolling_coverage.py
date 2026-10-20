#!/usr/bin/env python3
"""Regression: thousands of bids get fair, never-rejected RFP scan scheduling."""
import datetime as dt
import json
import pathlib
import runpy

root=pathlib.Path(__file__).resolve().parents[1]
module=runpy.run_path(str(root/'scripts/refresh_worklinks_rfp.py'),run_name='test_rolling')
discover=module['discover']
utc=dt.datetime.now(dt.timezone.utc)
today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
deadline=(today+dt.timedelta(days=4)).strftime('%Y%m%d')+'1400'
rows=[{'bidNo':'R26BK'+str(i).zfill(8),'order':'000',
       'kind':'servc','closes':deadline,
       'bidEligibility':{'requirements':[{'codes':['1468']}]}}
      for i in range(3450)]
calls=[]
def fake(url):
    from urllib.parse import parse_qs,urlsplit
    off=int(parse_qs(urlsplit(url).query)['offset'][0])
    calls.append(off)
    return {'ok':True,'totalCount':len(rows),'items':rows[off:off+500]}
discover.__globals__['fetch_json']=fake
first=discover(220,{})
assert len(first)==220,len(first)
assert calls==list(range(0,3500,500)),calls
recent={no+':'+order:{
 'checkedAt':utc.isoformat(),
 'classificationVersion':module['CLASSIFICATION_VERSION'],
 'hwpxReaderVersion':module['HWPX_READER_VERSION'],
 'reviewComplete':False,'files':[]} for no,order,_ in first}
calls.clear()
second=discover(220,recent)
assert len(second)==220,len(second)
assert set((n,o) for n,o,_ in first).isdisjoint((n,o) for n,o,_ in second)
assert len(calls)==7
# Partial scans, 403 errors, unknown times and after-deadline notices remain
# visible in the scan queue rather than being declared ineligible.
record={'checkedAt':utc.isoformat(),'classificationVersion':22,
        'status':'text_extracted_requires_review','files':[{
        'name':'공고문.hwpx','readable':True,
        'sourceSha256':'a'*64,'sourceTextScanComplete':True,
        'clauseCandidates':[{'sourceText':'업종코드 1468 필수','type':'industry_code'}]}]}
summary=module['compact_coverage'](record)
assert summary['status']=='text_extracted_requires_review'
assert summary['reviewComplete'] is False
assert summary['files'][0]['sourceSha256']=='a'*64
assert 'clauseCandidates' not in summary['files'][0]
assert summary['files'][0]['clauseCandidateCount']==1
print('WORKLINKS_RFP_ROLLING_CORPUS=PASS','total',len(rows),'batch',220,'cumulative_archive',True)
