#!/usr/bin/env python3
"""Recover stale notice labels only from stage-2 SHA receipts, without API GET."""
import gzip,hashlib,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import repair_open_rfp_cached_attachments as repair

notice='R26BK01829923:000'
source='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01829923&fileSeq=1'
name='입찰공고자료(26G056-H).zip'
sha=hashlib.sha256(b'verified compressed original').hexdigest()
def saved(name,sha,readable=True):
    return {'name':name,'readable':readable,
      'sourceTextScanComplete':readable,'sourceSha256':sha if readable else None}
meta={'attachments':{'ok':True,'complete':True,'items':[{'name':name,'url':source}]},
      'noticeDocuments':{'ok':True,'complete':True},
      'downloadVerifiedFiles':[{'name':name,'url':source,'sha256':sha}]}
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'rfp-coverage-index.json'
    records={
      notice:{'status':'text_unavailable','reasonCode':'download_or_format_failure',
          'manifestComplete':True,'reviewComplete':False,'files':[saved(name,sha)]},
      'R26BK01829962:000':{'status':'text_unavailable','manifestComplete':True,
          'files':[saved(name,'b'*64)]},
      'R26BK01829970:000':{'status':'text_unavailable','manifestComplete':True,
          'files':[saved(name,sha,readable=False)]}
    }
    p.write_text(json.dumps({'ok':True,'byNotice':records}))
    with patch.object(repair.rfp,'staffing_summary',return_value={}),\
         patch.object(repair.rfp,'staffing_fact_summary',return_value={}):
        fixed=repair.reconcile_old_verified_source_status(
            p,{k:meta for k in records},set(records),
            '2026-11-15T09:00:00+00:00')
    assert fixed==1,fixed
    data=json.loads(p.read_text())
    row=data['byNotice'][notice]
    assert row['status']=='text_extracted_requires_review',row
    assert row['reasonCode']=='readable_text_requires_full_review',row
    assert row['readableDocumentCount']==1
    assert row['unreadableDocumentCount']==0
    assert row['reviewComplete'] is False
    assert row['requiredConditionsComplete'] is False
    assert data['byNotice']['R26BK01829962:000']['status']=='text_unavailable'
    assert data['byNotice']['R26BK01829970:000']['status']=='text_unavailable'
    assert json.loads(gzip.decompress(Path(str(p)+'.gz').read_bytes()))==data

    # Not an unconditional sweep: second invocation has no stale source
    # and must not rewrite the index.
    before=p.read_bytes()
    with patch.object(repair.rfp,'staffing_summary',return_value={}),\
         patch.object(repair.rfp,'staffing_fact_summary',return_value={}):
        assert repair.reconcile_old_verified_source_status(
            p,{k:meta for k in records},set(records),'2026-11-15T09:10:00+00:00')==0
    assert p.read_bytes()==before
print('RFP_HISTORICAL_OCR_REPAIR_STATUS_SHA_PROVENANCE=PASS')
