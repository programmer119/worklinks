#!/usr/bin/env python3
"""No-network PDF OCR perf regression: open PyMuPDF once and skip cached pages."""
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,PropertyMock
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
from pypdf import PdfWriter
from pypdf._page import PageObject
from pypdf.generic import DecodedStreamObject,NameObject

def scanned(count,blank=False):
    writer=PdfWriter()
    for i in range(count):
        page=writer.add_blank_page(width=150,height=200)
        stream=DecodedStreamObject()
        stream.set_data(b'' if blank and i==count-1 else
                        b'q 0 0 1 rg 10 10 50 50 re f Q')
        page[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO()
    writer.write(output)
    return output.getvalue()

pdf=scanned(3)
original_open=pymupdf.open
calls=[]
def counted_open(*a,**kw):
    calls.append(1)
    return original_open(*a,**kw)

with tempfile.TemporaryDirectory() as tmp:
    with patch.dict(os.environ,{'WORKLINKS_RFP_OCR_PAGE_CACHE_DB':str(Path(tmp)/'pages.sqlite3'),
                                'WORKLINKS_RFP_DEFER_OCR':'0'}),\
         patch.object(reader.subprocess,'run',return_value=SimpleNamespace(
             returncode=0,stdout=('조달청 입찰 자격 조건 및 사업 요건 처리 ' * 4).encode(),stderr=b'')) as mockocr,\
         patch.object(pymupdf,'open',side_effect=counted_open),\
         patch.object(PageObject,'images',new_callable=PropertyMock) as images:
        value,evidence=reader.extract_with_source_status('3pages.pdf',pdf)
        assert evidence['ocrAttemptedPages']==3,evidence
        assert evidence['sourceComplete'] is True,evidence
        assert evidence['ocrPdfOpenSeconds']>=0,evidence
        assert evidence['ocrRenderSeconds']>=0,evidence
        assert evidence['ocrTesseractSeconds']>=0,evidence
        assert evidence['ocrPdfTotalSeconds']>=0,evidence
        assert evidence['ocrReceiptWriteSeconds']>=0,evidence
        assert evidence['pdfSources'][0]['ocrPdfOpenedOnce'] is True,evidence
        assert len(calls)==1,('one PyMuPDF PDF handle should serve 3 pages',len(calls))
        assert mockocr.call_count==3,mockocr.call_count
        assert images.call_count==0,('page.images invoked on image-only contents',images.call_count)
        assert not hasattr(reader._DOCUMENT_SCAN,'ocr_render_cache'), 'render handle leaked'

        value2,cached=reader.extract_with_source_status('3pages.pdf',pdf)
        assert cached['sourceComplete'] is True,cached
        assert cached['ocrAttemptedPages']==0,cached
        assert cached['ocrRestoredPages']==3,cached
        assert len(calls)==1,'cached pages must not reopen PyMuPDF'
        assert mockocr.call_count==3,'cached pages must not redo Tesseract'
        assert images.call_count==0,'cached pages must not decode XObjects'

# Truly blank page still isn't marked as source OCR work.
blank=scanned(2,blank=True)
with patch.object(reader,'_ocr_pdf_page',return_value='입찰 참가 자격 검사 조달청 입찰') as ocr:
    _,ev=reader.extract_with_source_status('blank-page.pdf',blank)
    assert ev['ocrAttemptedPages']==1,ev
    assert ev['pdfSources'][0]['genuinelyBlankPages']==1,ev
    assert ocr.call_count==1
print('PDF_OCR_OPEN_ONCE_NO_REDUNDANT_IMAGES_AND_HASHED_PAGE_CACHE_PASS')
