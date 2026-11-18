#!/usr/bin/env python3
"""Previously attempted official originals receive one exact source-scoped repair."""
import os,sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import repair_open_rfp_cached_attachments as repair

def candidate(name,err,evidence=None):
    return {'name':name,'readable':False,'sourceTextScanComplete':False,
      'errorCategory':err,'extractionEvidence':evidence or {},
      'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
      'lastReaderTransientRetryCount':2,
      'lastReaderAttemptAt':'2026-11-18T01:00:00+00:00',
      'lastSparseCoverAttemptVersion':repair.SPARSE_COVER_READER_VERSION,
      'lastPerimeterAttemptVersion':repair.EMPTY_PERIMETER_READER_VERSION}
zipfile=candidate('제안요청서 등.zip','file_extract_failure')
pdf=candidate('2. 규격서.pdf','pdf_ocr_incomplete',
    {'pdfPages':5,'ocrFailedPages':1,'ocrBatchDeferredPages':0})
with patch.dict(os.environ,{'WORKLINKS_RFP_SHORT_VECTOR_FAST_OCR':'0',
    'WORKLINKS_RFP_SHORT_VECTOR_FAST_ONLY':'0',
    'WORKLINKS_RFP_TARGETED_TRUNCATED_HWPX':'0'}):
    assert repair.reader_retry_files({'files':[zipfile,pdf]})==[]
with patch.dict(os.environ,{'WORKLINKS_RFP_SHORT_VECTOR_FAST_OCR':'1',
    'WORKLINKS_RFP_SHORT_VECTOR_FAST_ONLY':'1',
    'WORKLINKS_RFP_TARGETED_TRUNCATED_HWPX':'1'}):
    assert repair.reader_retry_files({'files':[zipfile,pdf]})==[zipfile,pdf]
    zipfile['lastTruncatedHwpxAttemptVersion']=repair.TRUNCATED_HWPX_READER_VERSION
    pdf['lastShortVectorAttemptVersion']=repair.SHORT_VECTOR_READER_VERSION
    assert repair.reader_retry_files({'files':[zipfile,pdf]})==[]
print('TARGETED_RFP_SOURCE_REPAIR_GUARDS_PASS')
