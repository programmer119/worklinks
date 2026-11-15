#!/usr/bin/env python3
"""Offline safety regression for fast native-text skip on confirmed scan pages."""
import io,os,sys
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter
from pypdf._page import PageObject
from pypdf.generic import DecodedStreamObject,NameObject
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader

writer=PdfWriter()
scanned=writer.add_blank_page(width=595,height=842)
stream=DecodedStreamObject()
stream.set_data(b'q 0 0 0 rg 120 140 300 400 re f Q')
scanned[NameObject('/Contents')]=writer._add_object(stream)
buf=io.BytesIO()
writer.write(buf)
scanned_pdf=buf.getvalue()

env={'WORKLINKS_RFP_FAST_SKIP_PYPDF_NATIVE':'1',
     'WORKLINKS_RFP_OCR_REGION_PROBE':'0',
     'WORKLINKS_RFP_DEFER_OCR':'0'}
with patch.dict(os.environ,env),\\
     patch.object(PageObject,'extract_text',return_value='should-not-use') as native,\\
     patch.object(reader,'_ocr_pdf_page',return_value='한국어 입찰 참가자격 원본 OCR 확인입니다') as ocr:
    text,stats=reader.extract_with_source_status('scanned.pdf',scanned_pdf)
    assert native.call_count==0,'slow pypdf scan-page parse must be bypassed'
    assert ocr.call_count==1,ocr.call_count
    assert stats['sourceComplete'] is True,stats
    assert stats['ocrNativeFastProbePages']==1,stats
    assert stats['ocrNativeFastSkippedPages']==1,stats
    assert stats['ocrNativeFastFallbacks']==0,stats
    assert '한국어 입찰' in text,text

# Native PDF text must still use the original pypdf reader, not OCR.
doc=pymupdf.open()
native_page=doc.new_page(width=595,height=842)
native_page.insert_text((70,120),'Tender qualification native text evidence')
native_pdf=doc.tobytes()
doc.close()
with patch.dict(os.environ,env),\\
     patch.object(reader,'_ocr_pdf_page',side_effect=AssertionError('native page must not OCR')) as ocr:
    text,stats=reader.extract_with_source_status('native.pdf',native_pdf)
    assert 'Tender qualification native text' in text,text
    assert stats['sourceComplete'] is True,stats
    assert stats['ocrNativeFastProbePages']==1,stats
    assert stats['ocrNativeFastSkippedPages']==0,stats
    assert stats['ocrNativeFastFallbacks']==0,stats
    assert stats['ocrAttemptedPages']==0,stats
    assert ocr.call_count==0,ocr.call_count
print('RFP_PDF_FAST_NATIVE_ONLY_SCAN_BYPASS_WITH_NATIVE_TEXT_PRESERVED=PASS')
