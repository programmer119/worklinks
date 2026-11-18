#!/usr/bin/env python3
"""Offline: a public attachment with verified DRMONE is not a parser failure."""
import json
import runpy
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
api=runpy.run_path(str(root/'server/g2b-proxy.py'),run_name='test_drm_access')
state=api['rfp_source_access_state']
saved=api['saved_rfp_search_state']
drm='drm_protected_original_requires_authorized_decryption'
good={'name':'공고문.pdf','readable':True,'sourceTextScanComplete':True,
      'sourceSha256':'a'*64,'staffingRoleScanVersion':4,
      'staffingFactScanVersion':2}
protected={'name':'설계내역서.xlsx','readable':False,'sourceTextScanComplete':False,
           'errorCategory':drm,'lastReaderAttemptVersion':'verified_drm_v1'}
d={'status':'text_extracted_requires_review','manifestComplete':True,
   'staffingRoleScanComplete':False,'files':[good,protected]}
s=state(d['files'])
assert s['status']=='restricted',s
assert s['protectedFileCount']==1 and s['otherUnreadableCount']==0,s
assert s['isParserFailure'] is False,s
for compact in (False,True):
    row=saved(d,compact=compact)
    assert row['sourceAccess']==s,row
    assert row['complete'] is False and row['scanComplete'] is False,row
    if not compact:
        assert row['fileStatuses'][1]['accessStatus']=='restricted',row
assert state([good])['status']=='none'
bad={'name':'다른.pdf','readable':False,'sourceTextScanComplete':False,
     'errorCategory':'pdf_ocr_incomplete'}
assert state([good,protected,bad])['status']=='mixed'
assert state([good,protected,bad])['otherUnreadableCount']==1
assert state([good,{'name':'서류.hwpx','readable':False,
    'skippedDuplicateFormat':True,'alternatePdfEvidence':'서류.pdf',
    'sourceTextScanComplete':False}])['protectedFileCount']==0
with tempfile.TemporaryDirectory(prefix='drm-source-state-') as tmp:
    path=Path(tmp)
    (path/'rfp-scanner-versions.json').write_text(json.dumps({'ok':True,
        'schemaVersion':1,'latest':{'classificationVersion':23,
        'hwpxReaderVersion':3,'staffingRoleScanVersion':4,
        'staffingFactScanVersion':2}}),encoding='utf-8')
    bid_db=path/'bids.sqlite3'
    q_db=path/'rfp-dual-queue.sqlite3'
    key='R26BK01825441:000'
    with sqlite3.connect(bid_db) as conn:
        conn.execute('CREATE TABLE bid_notices (bid_no TEXT,bid_ord TEXT,payload TEXT,sw_candidate INTEGER,last_seen TEXT)')
        conn.execute('INSERT INTO bid_notices (bid_no,bid_ord,payload,sw_candidate) VALUES (?,?,?,?)',
                     (key.split(':')[0],'000',json.dumps({'title':'상수도 모니터링','closes':'2026-11-30'}),1))
    with sqlite3.connect(q_db) as conn:
        conn.execute('CREATE TABLE rfp_dual_notices (notice_key TEXT,download_status TEXT,scan_status TEXT)')
        conn.execute('CREATE TABLE rfp_bulk_manifests (notice_key TEXT)')
        conn.execute('INSERT INTO rfp_dual_notices VALUES (?,?,?)',(key,'ready','retry'))
    g=api['rfp_rescan_cause_report'].__globals__
    overrides={
      'SNAPSHOT_ROOT':str(path),'G2B_DB_PATH':str(bid_db),
      'open_bid_db':lambda:sqlite3.connect(bid_db),
      'read_saved_rfp_evidence_index':lambda:{key:d},
      'read_rfp_notice_checkpoints':lambda index: (index,None,None),
      'rfp_progress_from_rows':lambda *args,**kwargs:{
          'counts':{'eligible':1,'completed':0,'remaining':1},
          '_cohortKeys':({key},set())},
      'rfp_stage_checks':lambda doc,vers:{
          'classification':True,'roles':False,'facts':False,'hwpx':None},
    }
    with patch.dict(g,overrides):
        out=api['rfp_rescan_cause_report']()
    assert out['categoryCounts']=={'source_restricted':1},out
    assert out['primaryCauseCounts']=={'official_attachment_drm_access_restricted':1},out
    assert out['counts']['remaining']==1,out
    assert len(out['records'])==1 and out['records'][0]['sourceAccess']=='restricted',out
    assert out['records'][0]['problemFileCount']==1,out
# A source-verified HWP5 distribution copy has its own protected-source
# reason; it must never be reported as a broken extractor or DRMONE.
hwp_protected=dict(protected,name='5. 청렴계약 이행 서약서.hwpx',
    errorCategory='hwp_record_fallback_protected')
hwp_state=state([good,hwp_protected])
assert hwp_state['status']=='restricted' and hwp_state['isParserFailure'] is False
assert hwp_state['protectedFileCount']==1 and hwp_state['otherUnreadableCount']==0
assert 'HWP' in hwp_state['protectedFiles'][0]['reason']
hwp_card=saved(dict(d,files=[good,hwp_protected]),compact=False)
assert hwp_card['sourceAccess']['status']=='restricted'
assert hwp_card['fileStatuses'][1]['accessStatus']=='restricted'

print('WORKLINKS_DRM_OFFICIAL_SOURCE_RESTRICTION_NOT_PARSER_FAILURE=PASS')
