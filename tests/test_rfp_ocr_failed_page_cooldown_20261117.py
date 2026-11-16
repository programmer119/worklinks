#!/usr/bin/env python3
"""Real offline PDF regression: repeated unreadable pages must not starve later pages.

A failed OCR attempt is NOT a success receipt; it is a durable deferral
allowing later original pages to be attempted on the next bounded pass.
"""
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair

writer=PdfWriter()
for offset in (0,20):
    page=writer.add_blank_page(width=595,height=842)
    stream=DecodedStreamObject()
    stream.set_data(f'q 0 0 0 rg {120+offset} 140 300 400 re f Q'.encode('ascii'))
    page[NameObject('/Contents')]=writer._add_object(stream)
out=io.BytesIO()
writer.write(out)
raw=out.getvalue()

with tempfile.TemporaryDirectory() as tmp:
    cache=Path(tmp)/'page-cache.sqlite3'
    env={'WORKLINKS_RFP_OCR_PAGE_CACHE_DB':str(cache),
         'WORKLINKS_RFP_FAST_SKIP_PYPDF_NATIVE':'1',
         'WORKLINKS_RFP_DEFER_OCR':'0',
         'WORKLINKS_RFP_OCR_REGION_PROBE':'0'}
    with patch.dict(os.environ,env),patch.object(reader,'MAX_PDF_OCR_PAGES',1):
        with patch.object(reader,'_ocr_pdf_page',return_value='') as first:
            text,p1=reader.extract_with_source_status('drawings.pdf',raw)
            assert first.call_count==1 and first.call_args.args[1]==0
            assert p1['sourceComplete'] is False and p1['ocrFailedPages']==1
            assert p1['ocrNewFailedPages']==1 and p1['ocrBatchDeferredPages']==1,p1
            assert repair.reader_retry_files({'files':[{'name':'drawings.pdf',
                 'readable':False,'errorCategory':'pdf_ocr_incomplete',
                 'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
                 'extractionEvidence':p1}]}),'a newly failed page is a valid bounded checkpoint'
        with patch.object(reader,'_ocr_pdf_page',
                          return_value='Staffing specification verified readable text from PDF image') as second:
            text,p2=reader.extract_with_source_status('drawings.pdf',raw)
            assert second.call_count==1 and second.call_args.args[1]==1,second.call_args_list
            assert p2['sourceComplete'] is False,p2
            assert p2['ocrCachedFailedPages']==1,p2
            assert p2['ocrNewFailedPages']==0,p2
            assert p2['ocrFailedPages']==1,p2
            assert p2['ocrRecoveredPages']==1,p2
            assert p2['ocrBatchDeferredPages']==0,p2
        with patch.object(reader,'_ocr_pdf_page',side_effect=AssertionError('same failure repeated')) as third:
            text,p3=reader.extract_with_source_status('drawings.pdf',raw)
            third.assert_not_called()
            assert p3['sourceComplete'] is False
            assert p3['ocrRecoveredPages']==1 and p3['ocrCachedFailedPages']==1
    with sqlite3.connect(cache) as db:
        failures=db.execute('SELECT page_index,attempts,reason FROM rfp_pdf_ocr_page_failures').fetchall()
        receipts=db.execute('SELECT page_index FROM rfp_pdf_ocr_page_receipts').fetchall()
    assert failures==[(0,1,'ocr_text_below_12_alphanumeric')],failures
    assert receipts==[(1,)],receipts
print('RFP_LONGPDF_FAILED_OCR_CHECKPOINT_UNBLOCKS_NEXT_PAGE_WITHOUT_FALSE_SUCCESS=PASS')
