#!/usr/bin/env python3
"""Offline proof: only truly white pages may bypass a failed PDF OCR page."""
import io,os,sys
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader,PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader

source=pymupdf.open()
source.new_page(width=595,height=842).insert_text((80,120),
    'Public procurement staffing and eligibility contract text')
native_pdf=source.tobytes()
source.close()

def make_pdf(content):
    writer=PdfWriter()
    writer.append_pages_from_reader(PdfReader(io.BytesIO(native_pdf)))
    page=writer.add_blank_page(width=595,height=842)
    stream=DecodedStreamObject()
    stream.set_data(content)
    page[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO()
    writer.write(output)
    return output.getvalue()

env={'WORKLINKS_RFP_FAST_SKIP_PYPDF_NATIVE':'1','WORKLINKS_RFP_DEFER_OCR':'0',
     'WORKLINKS_RFP_OCR_REGION_PROBE':'0'}
blank_pdf=make_pdf(b'q\nQ\n')
with patch.dict(os.environ,env),patch.object(reader,'_ocr_pdf_page',return_value='') as ocr:
    text,stats=reader.extract_with_source_status('contract.pdf',blank_pdf)
    assert stats['sourceComplete'] is True,stats
    assert stats['genuinelyBlankPages']==1,stats
    assert stats['ocrFailedPages']==0,stats
    assert 'Public procurement' in text,text
    assert ocr.call_count==1,ocr.call_count

# A real black diagram still requires source OCR even if OCR yielded no text.
diagram_pdf=make_pdf(b'q 0 0 0 rg 120 140 300 400 re f Q')
with patch.dict(os.environ,env),patch.object(reader,'_ocr_pdf_page',return_value='') as ocr:
    text,stats=reader.extract_with_source_status('diagram.pdf',diagram_pdf)
    assert stats['sourceComplete'] is False,stats
    assert stats['genuinelyBlankPages']==0,stats
    assert stats['ocrFailedPages']==1,stats
    assert ocr.call_count==1,ocr.call_count
print('RFP_TRUE_WHITE_PAGE_SKIP_AND_NONWHITE_FAIL_CLOSED=PASS')
