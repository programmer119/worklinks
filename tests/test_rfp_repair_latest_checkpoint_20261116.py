#!/usr/bin/env python3
"""Newest verified scan checkpoint must drive source repair selection."""
import datetime as dt
import json,sqlite3,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rfp_management_reconcile as M
import repair_open_rfp_cached_attachments as R

with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);snap=base/'snapshots';snap.mkdir()
    ver={'ok':True,'schemaVersion':1,'latest':{
        'classificationVersion':23,'staffingRoleScanVersion':4,
        'staffingFactScanVersion':2,'hwpxReaderVersion':3}}
    (snap/'rfp-scanner-versions.json').write_text(json.dumps(ver))
    source='a'*64
    files=[{'name':'공고문.pdf','readable':True,'sourceSha256':source,
      'sourceTextScanComplete':True,'staffingRoleScanVersion':4,
      'staffingFactScanVersion':2,'staffingRoleScanTruncated':False,
      'qualificationScanTruncated':False}]
    old={'status':'text_extracted_requires_review',
      'checkedAt':'2026-11-15T10:00:00+00:00',
      'manifestComplete':True,'manifestSignature':'d'*64,
      'classificationVersion':23,'staffingRoleScanComplete':True,
      'files':files}
    new={**old,'checkedAt':'2026-11-16T07:10:00+00:00',
         'staffingRoleScanComplete':False,
         'files':[dict(files[0],readable=False,sourceSha256=None,
                  sourceTextScanComplete=False,staffingRoleScanVersion=0,
                  staffingFactScanVersion=0,errorCategory='pdf_ocr_incomplete')]}
    assert M.same_thumbnail_original(old,new)
    assert M.latest_complete(old,ver['latest'])
    assert not M.latest_complete(new,ver['latest'])
    k='R26BK01817748:000'
    (snap/'rfp-coverage-index.json').write_text(json.dumps({'ok':True,'byNotice':{k:old}}))
    with sqlite3.connect(base/'rfp-notice-progress.sqlite3') as db:
        db.execute('CREATE TABLE rfp_notice_checkpoints(notice_key TEXT,checked_at TEXT,evidence_json TEXT)')
        db.execute('INSERT INTO rfp_notice_checkpoints VALUES(?,?,?)',(k,new['checkedAt'],json.dumps(new)))
    latest=R.source_verified_current_repair_rows(base,{k:old})
    assert latest[k]['checkedAt']==new['checkedAt'],'failure checkpoint was silently ignored'
    assert len(R.failed_files(latest[k]))==1
    assert len(R.reader_retry_files(latest[k]))==1
    assert not M.latest_complete(latest[k],ver['latest'])
    # A changed manifest must never overwrite the old source with a different
    # attachment set merely because a newer checkpoint exists.
    changed={**new,'manifestSignature':'e'*64}
    with sqlite3.connect(base/'rfp-notice-progress.sqlite3') as db:
        db.execute('UPDATE rfp_notice_checkpoints SET evidence_json=?',(json.dumps(changed),))
    assert R.source_verified_current_repair_rows(base,{k:old})[k]==old
print('RFP_LATEST_SHA_MATCHING_FAILED_CHECKPOINT_SELECTED_WITHOUT_FALSE_SUCCESS=PASS')
