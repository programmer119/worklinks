#!/usr/bin/env python3
"""No-network proof: an OCR source repair survives busy postpublish SQLite.

The original document and published RFP evidence are never thrown away or
re-OCRed just because the separate notice checkpoint was write-locked.
"""
import json,runpy,sqlite3,tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
module=runpy.run_path(str(ROOT/'server/worklinks-server123-pipeline.py'),
                      run_name='worklinks_ocr_busy_regression')
retry=module['retry_published_ocr_reconcile']
globals_=retry.__globals__
assert callable(module['reconcile_published_ocr_batch'])
with tempfile.TemporaryDirectory(prefix='rfp-busy-') as tmp:
    pending=Path(tmp)/'pending.json'
    keys=['R26BK01809385:000','R26BK01809525:000']
    pending.write_text(json.dumps({'keys':keys,'publishedAt':'2026-11-16T02:00:00Z'}),
                       encoding='utf-8')
    attempts=[]
    def reconcile(ids,*,dual_enabled):
        assert ids==keys,ids
        attempts.append(ids)
        if len(attempts)==1:
            raise sqlite3.OperationalError('database is locked')
    with patch.dict(globals_,{'OCR_RECONCILE_PENDING':pending,
                              'reconcile_published_ocr_batch':reconcile}),\
         patch.dict(__import__('os').environ,{'WORKLINKS_RFP_DUAL_QUEUE':'1'}):
        assert retry(attempts=1) is False
        assert pending.is_file(),'a busy checkpoint must stay pending'
        assert retry(attempts=1) is True
        assert not pending.exists(),'only successful reconciliation retires marker'
    assert len(attempts)==2,attempts
    print('RFP_OCR_POSTPUBLISH_BUSY_RETRY_PRESERVES_DURABLE_EVIDENCE=PASS')

# Non-busy failures must NOT be disguised as transient contention.
with tempfile.TemporaryDirectory(prefix='rfp-error-') as tmp:
    pending=Path(tmp)/'pending.json'
    pending.write_text(json.dumps({'keys':keys}),encoding='utf-8')
    def unexpected(ids,*,dual_enabled):
        raise sqlite3.OperationalError('no such table: verified_cache')
    with patch.dict(globals_,{'OCR_RECONCILE_PENDING':pending,
                              'reconcile_published_ocr_batch':unexpected}):
        try:retry(attempts=1)
        except sqlite3.OperationalError as e:
            assert 'no such table' in str(e)
        else:
            raise AssertionError('non-busy schema corruption must fail closed')
        assert pending.exists()
    print('RFP_OCR_POSTPUBLISH_UNEXPECTED_DB_ERRORS_NOT_SWALLOWED=PASS')
