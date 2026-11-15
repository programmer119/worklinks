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
# Regression: a newly completed scanner checkpoint supersedes an obsolete
# published coverage snapshot, and its actual version numbers reach the card.
import json
import sqlite3
import tempfile
from unittest.mock import patch
with tempfile.TemporaryDirectory() as tmp:
    path=str(Path(tmp)/'rfp-notice-progress.sqlite3')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE rfp_notice_checkpoints (notice_key TEXT PRIMARY KEY, checked_at TEXT, evidence_json TEXT)')
        prior=source_record('old')
        prior.update(checkedAt='2026-11-14T08:00:00+00:00',
                     classificationVersion=0,hwpxReaderVersion=0)
        recent=source_record('new')
        recent.update(checkedAt='2026-11-15T08:00:00+00:00',
                      classificationVersion=23,hwpxReaderVersion=3,
                      staffingRoleScanComplete=True)
        for f in recent['files']:
            if f.get('readable') is True:
                f.update(staffingRoleScanVersion=4,staffingFactScanVersion=2,
                         staffingRoleScanTruncated=False)
        db.execute('INSERT INTO rfp_notice_checkpoints VALUES (?,?,?)',
                   (first,recent['checkedAt'],json.dumps(recent)))
    globals_['read_saved_rfp_evidence_index']=lambda:{first:prior}
    progress_globals=handler.__globals__
    actual_db=progress_globals['G2B_DB_PATH']
    version_root=progress_globals['SNAPSHOT_ROOT']
    snapshot=Path(tmp)/'snapshots'
    snapshot.mkdir()
    (snapshot/'rfp-scanner-versions.json').write_text(json.dumps({
        'ok':True,'schemaVersion':1,'latest':{
          'classificationVersion':23,'staffingRoleScanVersion':4,
          'staffingFactScanVersion':2,'hwpxReaderVersion':3}}))
    with patch.dict(progress_globals,{'G2B_DB_PATH':str(Path(tmp)/'bids.sqlite3'),
                                      'SNAPSHOT_ROOT':str(snapshot)}):
        data=handler(first)['byNotice'][first]
        assert data['classificationVersion']==23,data
        assert data['versionSource']=='checkpoint',data
        assert data['parserCurrent'] is True,data
        assert data['staffingRoleVersions']==[4],data
        assert data['staffingFactVersions']==[2],data
        assert data['checkedAt']==recent['checkedAt'],data
    globals_['read_saved_rfp_evidence_index']=original
print('RFP_VISIBLE_CARD_INSURANCE_BATCH_SOURCE_RECONCILIATION=PASS')
