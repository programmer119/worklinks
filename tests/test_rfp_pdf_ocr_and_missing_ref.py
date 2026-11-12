#!/usr/bin/env python3
"""Offline: bounded PDF OCR, provenance, same-stem PDF fallback and HTTP 422."""
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter, PdfReader
from pypdf.generic import DecodedStreamObject,NameObject

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
spec=importlib.util.spec_from_file_location('rfp_ocr_test',root/'scripts/refresh_worklinks_rfp.py')
rfp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(rfp)

# A PDF content stream with NO selectable text must use page-local OCR.
writer=PdfWriter()
page=writer.add_blank_page(width=600,height=800)
stream=DecodedStreamObject()
stream.set_data(b'q 0 0 1 rg 10 10 90 50 re f Q')
page[NameObject('/Contents')]=writer._add_object(stream)
buff=io.BytesIO();writer.write(buff);blob=buff.getvalue()
assert PdfReader(io.BytesIO(blob)).pages[0].extract_text()==''
with patch.object(rfp,'_ocr_pdf_page',return_value='입찰참가자격 증명은 입찰 마감 전에 제출한다.') as fake:
    text,meta=rfp.extract_with_source_status('scan.pdf',blob)
    assert '입찰참가자격' in text
    assert meta['sourceComplete'] is True
    assert meta['ocrAttemptedPages']==1 and meta['ocrRecoveredPages']==1,meta
    assert fake.call_count==1

with patch.object(rfp,'_ocr_pdf_page',side_effect=ValueError('pdf_ocr_engine_unavailable')):
    try:
        rfp.extract('scan.pdf',blob)
        raise AssertionError('image PDF without successful OCR was accepted')
    except ValueError as exc:
        assert str(exc)=='pdf_ocr_incomplete'

# A fully empty PDF page must NOT trigger OCR or invalidate adjacent text.
blank=PdfWriter();blank.add_blank_page(width=600,height=800)
b=io.BytesIO();blank.write(b)
with patch.object(rfp,'_ocr_pdf_page',side_effect=AssertionError('spurious OCR')):
    try:
        rfp.extract('blank.pdf',b.getvalue())
        raise AssertionError('an all-empty document should not pass')
    except ValueError as exc:
        assert str(exc)=='no_searchable_text'

# Same-stem official PDF can be used as an alternative citation without
# claiming that the HWP binary itself was successfully read.
siblings=[
 {'name':'입찰공고.hwp','readable':False,'sourceTextScanComplete':False,
  'errorCategory':'no_searchable_text'},
 {'name':'입찰공고.pdf','readable':True,'sourceTextScanComplete':True,
  'sourceSha256':'b'*64,'sourceUrl':'https://www.g2b.go.kr/doc.pdf'},
 {'name':'독립 제안요청서.hwp','readable':False,'sourceTextScanComplete':False}]
assert rfp.annotate_official_pdf_siblings(siblings)==1
assert siblings[0]['alternatePdfEvidence']=='입찰공고.pdf'
assert siblings[0]['readable'] is False
assert siblings[0]['sourceTextScanComplete'] is False
assert siblings[2].get('alternatePdfEvidence') is None
assert rfp.annotate_official_pdf_siblings(siblings)==0

url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadRfpFile.do?rfpNo=R26DH00060250&rfpOrd=000&rfpUntyAtchFileNo=1'
jsonbody=json.dumps({'ErrorMsg':'파일이 존재하지 않습니다.','ErrorCode':-1}).encode('utf-8')
def fake_422(request,timeout=35):
    raise urllib.error.HTTPError(url,422,'Unprocessable Entity',{},io.BytesIO(jsonbody))
with patch.object(rfp.OPENER,'open',side_effect=fake_422):
    try:
        rfp.download(url)
        raise AssertionError('wrongly accepted 422')
    except rfp.OfficialAttachmentReferenceMissing as exc:
        assert rfp.classify_failure(exc)=='official_attachment_reference_missing_422'

# Other 422 reasons must not be classified as confirmed missing file.
wrong=urllib.error.HTTPError(url,422,'Unprocessable Entity',{},
    io.BytesIO(b'{"ErrorCode":-5,"ErrorMsg":"unknown"}'))
assert rfp.official_missing_reference(wrong) is False
print('WORKLINKS_PDF_OCR_422_SIBLING_REGRESSION=PASS')
