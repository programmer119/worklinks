#!/usr/bin/env python3
"""No-network regression: 24-page OCR slices resume through SQLite and nested ZIP."""
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject

def image_only_pdf(count):
    writer=PdfWriter()
    for i in range(count):
        page=writer.add_blank_page(width=595,height=842)
        stream=DecodedStreamObject()
        stream.set_data(b'q 0 0 1 rg 10 10 90 50 re f Q')
        page[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO()
    writer.write(output)
    return output.getvalue()

def text_for(page):
    return '입찰자격 확인과 기술지원 문서의 실제 OCR 페이지 '+str(page+1)

assert reader.MAX_PDF_OCR_PAGES==24
assert repair.READER_ATTEMPT_VERSION.endswith('v15-20261116')
with tempfile.TemporaryDirectory() as tmp:
    cache=str(Path(tmp)/'rfp-ocr-page-cache.sqlite3')
    with patch.dict(os.environ,{'WORKLINKS_RFP_OCR_PAGE_CACHE_DB':cache,
                                'WORKLINKS_RFP_DEFER_OCR':'0'}):
        for number in (26,31,91):
            pdf=image_only_pdf(number)
            actual=[]
            with patch.object(reader,'_ocr_pdf_page',
                    side_effect=lambda _raw,index: (actual.append(index),text_for(index))[1]):
                for batch in range((number+23)//24):
                    value,evidence=reader.extract_with_source_status(
                        'scan.pdf',pdf)
                    processed=min(number,(batch+1)*24)
                    assert evidence['ocrAttemptedPages']==min(24,number-batch*24),evidence
                    assert evidence['ocrRecoveredPages']==processed,evidence
                    assert evidence['ocrRestoredPages']==batch*24,evidence
                    assert evidence['ocrBatchDeferredPages']==number-processed,evidence
                    assert evidence['ocrFailedPages']==0,evidence
                    assert evidence['sourceComplete'] is (processed==number),evidence
                assert sorted(actual)==list(range(number)),(number,actual)
                assert len(value.splitlines())==number
                assert evidence['ocrRestoredPages']==number if number%24==0 else (
                    evidence['ocrRestoredPages']==((number-1)//24)*24)
            # Final rerun restores all pages from SHA cache, zero Tesseract calls.
            with patch.object(reader,'_ocr_pdf_page',
                    side_effect=AssertionError('already saved page rescanned')):
                _,evidence2=reader.extract_with_source_status('scan.pdf',pdf)
                assert evidence2['ocrAttemptedPages']==0,evidence2
                assert evidence2['ocrRestoredPages']==number
                assert evidence2['sourceComplete'] is True
        # ZIP is a container; persist receipts using exact inner PDF bytes.
        pdf=image_only_pdf(27)
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('별첨/영상기반 기술지원협약서.pdf',pdf)
        with patch.object(reader,'_ocr_pdf_page',side_effect=lambda _raw,i:text_for(i)) as ocr:
            first,info=reader.extract_with_source_status('bundle.zip',stream.getvalue())
            assert info['ocrRecoveredPages']==24 and info['ocrBatchDeferredPages']==3,info
            assert info['sourceComplete'] is False
            second,info=reader.extract_with_source_status('bundle.zip',stream.getvalue())
            assert info['ocrRecoveredPages']==27 and info['ocrRestoredPages']==24,info
            assert info['sourceComplete'] is True,info
            assert ocr.call_count==27
            assert 'FILE ' in second
    # Only an actually progressed 24-page slice is allowed to resume.
    partial={'name':'scan.pdf','readable':False,'errorCategory':'pdf_ocr_incomplete',
             'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
             'extractionEvidence':{'ocrRecoveredPages':24,'ocrBatchDeferredPages':67}}
    assert repair.reader_retry_files({'files':[partial]})==[partial]
    stalled=dict(partial,extractionEvidence={'ocrRecoveredPages':0,'ocrBatchDeferredPages':67})
    assert repair.reader_retry_files({'files':[stalled]})==[]
    complete=dict(partial,extractionEvidence={'ocrRecoveredPages':91,'ocrBatchDeferredPages':0})
    assert repair.reader_retry_files({'files':[complete]})==[]
print('RFP_OCR_24_PAGE_SLICES_91_PAGE_RESUME_AND_ZIP=PASS')
