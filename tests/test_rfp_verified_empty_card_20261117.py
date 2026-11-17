#!/usr/bin/env python3
"""Verified empty official manifest never becomes a fabricated successful RFP scan."""
import json,os,runpy,sqlite3,tempfile
from pathlib import Path
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='worklinks-empty-card-') as tmp:
    with patch.dict(os.environ,{'G2B_DB_PATH':str(Path(tmp)/'bids.sqlite3')}):
        api=runpy.run_path(str(root/'server/g2b-proxy.py'),run_name='test_verified_empty_card')
    g=api['read_saved_rfp_card_states'].__globals__
    source_key='R26BK01830918:000'
    invalid_key='R26BK01830919:000'
    scanned_key='R26BK01830920:000'
    def meta(files=None,details=None):
        return {'manifestOrigin':'verified_missing_date_batch_exception',
            'attachments':{'ok':True,'complete':True,'items':list(files or [])},
            'noticeDocuments':{'ok':True,'complete':True,'items':list(details or [])}}
    qpath=Path(tmp)/'rfp-dual-queue.sqlite3'
    with sqlite3.connect(qpath) as db:
        db.execute('''CREATE TABLE rfp_dual_notices(
            notice_key TEXT PRIMARY KEY,download_status TEXT,scan_status TEXT,metadata_json TEXT)''')
        db.execute('''CREATE TABLE rfp_bulk_manifests(
            notice_key TEXT PRIMARY KEY,metadata_json TEXT)''')
        for key,payload in [(source_key,meta()),(invalid_key,meta(details=[{'name':'실제 제안요청서.pdf'}])),
                            (scanned_key,meta())]:
            doc=json.dumps(payload,ensure_ascii=False)
            db.execute('INSERT INTO rfp_dual_notices VALUES (?,?,?,?)',
                (key,'no_attachments','skipped',doc))
            db.execute('INSERT INTO rfp_bulk_manifests VALUES (?,?)',(key,doc))
    statuses=api['read_verified_empty_rfp_manifest_states']([source_key,invalid_key,scanned_key])
    assert source_key in statuses and statuses[source_key]['officialAttachmentState']=='verified_empty'
    assert statuses[source_key]['seen'] is False and statuses[source_key]['scanExcluded'] is True
    assert statuses[source_key]['scanComplete'] is False
    assert invalid_key not in statuses,'nonempty detail cannot be treated as empty'
    original=api['read_saved_rfp_card_states']([source_key,invalid_key],{},compact=True)
    assert original[source_key]['officialAttachmentState']=='verified_empty'
    assert original[invalid_key]['seen'] is False
    existing={'status':'text_extracted_requires_review','manifestComplete':True,'files':[{
        'name':'제안요청서.pdf','readable':True,'sourceTextScanComplete':True,
        'sourceSha256':'a'*64}]}
    protected=api['read_saved_rfp_card_states']([scanned_key],{scanned_key:existing},compact=True)
    assert protected[scanned_key]['seen'] is True
    assert protected[scanned_key].get('officialAttachmentState')!='verified_empty'
    print('VERIFIED_EMPTY_CARD_API_PASS')
