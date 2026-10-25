#!/usr/bin/env python3
"""Checkpoint round trip: recover scanned RFP evidence after a failed push."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
spec = importlib.util.spec_from_file_location(
    'worklinks_rfp_recovery', root / 'scripts/recover_worklinks_rfp_checkpoint.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    detail = td / 'rfp-clauses.json'
    index = td / 'rfp-coverage-index.json'
    old = {'ok': True, 'byNotice': {'OLD:000': {
        'status': 'text_extracted_requires_review', 'checkedAt': '2026-10-25T00:00:00Z',
        'files': [{'name': 'original.pdf', 'sourceSha256': 'a'*64, 'readable': True}]}}}
    old_index = {'ok': True, 'byNotice': {'OLD:000': {**old['byNotice']['OLD:000'],
        'changcomClauseEvidence': {'files': [{'url': 'https://www.g2b.go.kr/doc'}]}}}}
    pending = {'ok': True, 'byNotice': {
        'OLD:000': {'status': 'metadata_fetch_failed', 'checkedAt': '2026-10-26T00:00:00Z'},
        'NEW:000': {'status': 'text_extracted_requires_review',
                    'checkedAt': '2026-10-26T00:00:00Z',
                    'files': [{'name': 'new.hwpx', 'readable': True, 'sourceSha256': 'b'*64}]}}}
    # A concurrent metadata-only probe must outrank a checkpoint whose
    # extracted document is newer but whose manifest check is older.
    old_index['byNotice']['NEW:000'] = {
        'status':'text_extracted_requires_review',
        'checkedAt':'2026-10-24T00:00:00Z',
        'manifestSignature':'x'*64,
        'manifestCheckedAt':'2026-10-27T00:00:00Z',
        'manifestChangePending':True,
        'manifestPendingSignature':'y'*64,
        'files':[{'name':'old-new.pdf','sourceSha256':'z'*64}]}
    old_index_pending = {'ok': True, 'byNotice': {
        'OLD:000': pending['byNotice']['OLD:000'],
        'NEW:000': {**pending['byNotice']['NEW:000'], 'files': [
            {'name': 'new.hwpx', 'readable': True, 'sourceSha256': 'b'*64}]}}}
    detail.write_text(json.dumps(old), encoding='utf-8')
    index.write_text(json.dumps(old_index), encoding='utf-8')
    zpath = td / 'pending.zip'
    with zipfile.ZipFile(zpath, 'w') as z:
        z.writestr('rfp-clauses.json', json.dumps(pending))
        z.writestr('rfp-coverage-index.json', json.dumps(old_index_pending))
    detail_count, index_count = recovery.recover(zpath, detail, index)
    assert (detail_count, index_count) == (1, 1), (detail_count, index_count)
    d = json.loads(detail.read_text())
    i = json.loads(index.read_text())
    assert set(d['byNotice']) == {'OLD:000', 'NEW:000'}
    assert d['byNotice']['OLD:000']['files'][0]['sourceSha256'] == 'a'*64
    assert i['byNotice']['OLD:000']['changcomClauseEvidence']
    assert i['byNotice']['NEW:000']['files'][0]['sourceSha256'] == 'b'*64
    assert i['byNotice']['NEW:000']['manifestChangePending'] is True
    assert i['byNotice']['NEW:000']['manifestCheckedAt'] == '2026-10-27T00:00:00Z'
    assert i['scannedNoticeCount'] == 2
    assert recovery.recover(zpath, detail, index) == (0, 0)
print('WORKLINKS_RFP_CHECKPOINT_RECOVERY=PASS')
