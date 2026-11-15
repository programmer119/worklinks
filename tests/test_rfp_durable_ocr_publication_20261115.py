#!/usr/bin/env python3
"""No-network regression: fast scanner cannot erase complete OCR repair."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('ocr_safe_scheduler',
                                            ROOT/'server/worklinks-server123-pipeline.py')
pipeline=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
import refresh_worklinks_rfp as reader

VERSIONS={'classificationVersion':reader.CLASSIFICATION_VERSION,
 'staffingRoleScanVersion':reader.STAFFING_ROLE_SCAN_VERSION,
 'staffingFactScanVersion':reader.STAFFING_FACT_SCAN_VERSION,
 'hwpxReaderVersion':reader.HWPX_READER_VERSION}
def valid(checked,signature='unchanged'):
    return {
     'status':'text_extracted_requires_review','checkedAt':checked,
     'manifestComplete':True,'manifestSignature':signature,
     'classificationVersion':VERSIONS['classificationVersion'],
     'hwpxReaderVersion':VERSIONS['hwpxReaderVersion'],
     'staffingRoleScanComplete':True,
     'files':[{'name':'(붙임5) 긴급입찰사유서.hwpx',
      'readable':True,'sourceSha256':'a'*64,
      'sourceTextScanComplete':True,'qualificationScanTruncated':False,
      'staffingRoleScanVersion':VERSIONS['staffingRoleScanVersion'],
      'staffingFactScanVersion':VERSIONS['staffingFactScanVersion'],
      'staffingRoleScanTruncated':False,
      'extractionEvidence':{'pdfFiles':5,'ocrAttemptedPages':5,
                            'ocrRecoveredPages':5,'unresolvedPages':0}}]}
def incomplete(checked,signature='unchanged'):
    row=valid(checked,signature)
    row['staffingRoleScanComplete']=False
    row['files'][0].update(readable=False,sourceSha256='',
                            sourceTextScanComplete=False,
                            errorCategory='pdf_ocr_incomplete')
    return row

key='R26BK01827520:000'
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    pipeline.DATA=root
    pipeline.SEEDS=root/'snapshots'
    pipeline.SEEDS.mkdir()
    (pipeline.SEEDS/'rfp-scanner-versions.json').write_text(json.dumps(
       {'ok':True,'latest':VERSIONS}),encoding='utf-8')
    live={'ok':True,'byNotice':{key:valid('2026-11-15T10:31:11+00:00')}}
    dest=pipeline.SEEDS/'rfp-coverage-index.json'
    dest.write_text(json.dumps(live),encoding='utf-8')
    checkpoint=root/'rfp-notice-progress.sqlite3'
    with sqlite3.connect(checkpoint) as db:
        db.execute('CREATE TABLE rfp_notice_checkpoints(notice_key TEXT PRIMARY KEY,checked_at TEXT,evidence_json TEXT)')
        good=live['byNotice'][key]
        db.execute('INSERT INTO rfp_notice_checkpoints VALUES(?,?,?)',
                   (key,good['checkedAt'],json.dumps(good)))
    stage=root/'stage.json'
    staged={'ok':True,'byNotice':{key:incomplete('2026-11-15T10:32:00+00:00')}}
    stage.write_text(json.dumps(staged),encoding='utf-8')
    merged=pipeline.merge_rfp_coverage_before_publish(stage)
    assert pipeline.rfp_coverage_complete(merged[key],VERSIONS)
    assert merged[key]['files'][0]['extractionEvidence']['ocrRecoveredPages']==5
    pipeline.publish_atomic(stage,dest)
    assert json.loads(dest.read_text())['byNotice'][key]['staffingRoleScanComplete']
    # A genuinely changed official manifest must not retain stale OCR proof.
    staged={'ok':True,'byNotice':{key:incomplete('2026-11-15T10:33:00+00:00','changed')}}
    stage.write_text(json.dumps(staged),encoding='utf-8')
    changed=pipeline.merge_rfp_coverage_before_publish(stage)
    assert changed[key]['manifestSignature']=='changed'
    assert not pipeline.rfp_coverage_complete(changed[key],VERSIONS)
    # New repair evidence must become a durable checkpoint, independent of JSON.
    newkey='R26BK01827521:000'
    corrected=valid('2026-11-15T10:34:00+00:00','new-signature')
    staged={'ok':True,'byNotice':{newkey:corrected}}
    stage.write_text(json.dumps(staged),encoding='utf-8')
    pipeline.merge_rfp_coverage_before_publish(stage)
    pipeline.publish_atomic(stage,dest)
    assert pipeline.publish_verified_repair_checkpoints([newkey])==1
    with sqlite3.connect(checkpoint) as db:
        saved=db.execute('SELECT evidence_json FROM rfp_notice_checkpoints WHERE notice_key=?',
                         (newkey,)).fetchone()
    assert saved and json.loads(saved[0])['staffingRoleScanComplete']
    assert pipeline.publish_verified_repair_checkpoints([key])==0
    # Per-notice scanner checkpoint must not be downgraded by deferred OCR.
    old_env=os.environ.get('WORKLINKS_RFP_NOTICE_PROGRESS_DB')
    os.environ['WORKLINKS_RFP_NOTICE_PROGRESS_DB']=str(checkpoint)
    try:
        assert reader.publish_notice_checkpoint(newkey,corrected,'23:3:4:2')
        assert reader.publish_notice_checkpoint(newkey,incomplete(
          '2026-11-15T10:35:00+00:00','new-signature'),'23:3:4:2')
    finally:
        if old_env is None:os.environ.pop('WORKLINKS_RFP_NOTICE_PROGRESS_DB',None)
        else:os.environ['WORKLINKS_RFP_NOTICE_PROGRESS_DB']=old_env
    with sqlite3.connect(checkpoint) as db:
        saved=json.loads(db.execute('SELECT evidence_json FROM rfp_notice_checkpoints WHERE notice_key=?',
                              (newkey,)).fetchone()[0])
    assert saved['staffingRoleScanComplete']
    assert saved['files'][0]['readable']
    assert saved['checkedAt']=='2026-11-15T10:34:00+00:00'
print('RFP_DURABLE_OCR_NO_STALE_OVERWRITE=PASS')
