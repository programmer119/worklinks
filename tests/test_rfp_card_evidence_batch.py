#!/usr/bin/env python3
"""No-network regression for 4-insurance badges outside the first 400 saved rows."""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parents[1]
api=runpy.run_path(str(root/'server/g2b-proxy.py'),run_name='test_4insurance_batch')
handler=api['rfp_card_evidence_batch']
globals_=handler.__globals__
original=globals_['read_saved_rfp_evidence_index']

def source_record(title):
    return {'status':'text_extracted_requires_review','manifestComplete':True,
            'staffingRoleScanComplete':True,'files':[
      {'name':title+'.hwpx','readable':False,'sourceTextScanComplete':False,
       'skippedDuplicateFormat':True,'alternatePdfEvidence':title+'.pdf',
       'alternatePdfSourceSha256':'e'*64},
      {'name':title+'.pdf','readable':True,'sourceTextScanComplete':True,
       'sourceSha256':'e'*64,'qualificationScanTruncated':False,
       'unmatchedQualificationAnchorCount':0},
      {'name':'제안요청서.hwp','readable':True,'sourceTextScanComplete':True,
       'sourceSha256':'f'*64,'qualificationScanTruncated':False,
       'unmatchedQualificationAnchorCount':0}]}

first='R26BK01807134:000'
second='R26BK01818412:000'
record={first:source_record('용인 공고문'),second:source_record('플랫폼 공고문')}
try:
    globals_['read_saved_rfp_evidence_index']=lambda:record
    result=handler(first+','+second)
    assert result['ok'] and result['count']==2 and result['upstreamCalls']==0,result
    for key in (first,second):
        row=result['byNotice'][key]
        assert row['sourceAvailable'] and row['seen'],row
        assert row['complete'] and row['scanComplete'],row
        assert row['effectiveReadableCount']==row['documentCount']==3,row
        assert row['pdfCoveredCount']==1,row
    for invalid in ('','BAD:000',first+','+first,','.join([first]*101)):
        try:handler(invalid)
        except api['ApiError']:pass
        else:raise AssertionError('accepted invalid or duplicate request: '+invalid[:50])
    missing=handler('R26BK01877777:000')['byNotice']['R26BK01877777:000']
    assert missing['seen'] is False,missing
finally:
    globals_['read_saved_rfp_evidence_index']=original
print('RFP_VISIBLE_CARD_INSURANCE_BATCH_SOURCE_RECONCILIATION=PASS')
