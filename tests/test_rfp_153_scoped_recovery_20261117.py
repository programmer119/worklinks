#!/usr/bin/env python3
"""Strict scope and fail-closed tests for five-page 153-PDF recovery."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import repair_open_rfp_cached_attachments as repair
import repair_rfp_153_target_pages_20261117 as scoped

sha=scoped.EXPECTED_SHA
assert scoped.valid_source(scoped.NOTICE,sha,153)
for key,digest,pages in (('OTHER',sha,153),(scoped.NOTICE,'0'*64,153),
                          (scoped.NOTICE,sha,152)):
    assert not scoped.valid_source(key,digest,pages)
assert scoped.TARGET_PAGES==(2,5,107,130,132)
assert not scoped.sufficient_text(''.join('A' for _ in range(200)),tiled=True)
assert not scoped.sufficient_text(''.join('가' for _ in range(10)),tiled=False)
assert scoped.sufficient_text('가'*150+'1'*500,tiled=True)
assert scoped.sufficient_text('가'*10+'1'*60)
item={'name':'3. 공사도면_안산송산 예시.pdf',
      'sourceSha256':sha,'readable':False,'sourceTextScanComplete':False,
      'errorCategory':'pdf_ocr_incomplete',
      'extractionEvidence':{'pdfPages':153},
      'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
      'lastReaderTransientRetryCount':2,
      'ocrBatchDeferredPages':0}
with patch.dict(os.environ,{'WORKLINKS_RFP_153_VERIFIED_RECEIPT_RECHECK':'1'}):
    assert repair.reader_retry_files({'files':[item]})==[item]
    for mutate in (
       {'sourceSha256':'0'*64},{'name':'wrong.pdf'},
       {'errorCategory':'drm_protected_original_requires_authorized_decryption',
        'lastPartialDrmZipAttemptVersion':repair.PARTIAL_DRM_ZIP_READER_VERSION},
       {'extractionEvidence':{'pdfPages':152}}):
        candidate=dict(item,**mutate)
        assert repair.reader_retry_files({'files':[candidate]})==[]
with patch.dict(os.environ,{'WORKLINKS_RFP_153_VERIFIED_RECEIPT_RECHECK':'0'}):
    assert repair.reader_retry_files({'files':[item]})==[]
print('RFP_153_HASH_SCOPED_RECEIPT_RECHECK=PASS')
