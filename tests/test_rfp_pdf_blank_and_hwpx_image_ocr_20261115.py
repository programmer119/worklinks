#!/usr/bin/env python3
"""Real PDF rendering boundaries, zero-byte PDF streams, image-only HWPX/ZIP.

All fixtures are generated locally: no official attachment GET, no network OCR.
"""
import io
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject
from PIL import Image

def pdf(pages):
    writer=PdfWriter()
    for width,height,content in pages:
        page=writer.add_blank_page(width=width,height=height)
        stream=DecodedStreamObject()
        stream.set_data(content)
        page[NameObject('/Contents')]=writer._add_object(stream)
    b=io.BytesIO();writer.write(b)
    return b.getvalue()

# Exactly 697x1007pt used to render 12,001,929 pixels in the live PDF,
# exceeding the 12,000,000 pixel cap by ONLY 1,929 pixels. The renderer must
# downscale once rather than mark this readable page as a permanent failure.
large=pdf([(697,1007,b'q 0 0 1 rg 10 10 90 50 re f Q')])
with patch.object(reader.shutil,'which',return_value='/usr/bin/tesseract'),\
     patch.object(reader.subprocess,'run',return_value=SimpleNamespace(
         returncode=0,stdout='상생결제제도 안내자료 입찰 참가 자격'.encode(),stderr=b'')) as ocr:
    value=reader._ocr_pdf_page(large,0)
    assert '상생결제제도' in value,value
    assert ocr.call_count==1
    assert ocr.call_args.kwargs['input'].startswith(b'\x89PNG\r\n\x1a\n')

# /Contents can exist but contain ZERO bytes: do not OCR an actually blank
# page (the real official AI traffic-management notice has this on page 8).
pages=pdf([(595,842,b'q 0 0 1 rg 10 10 90 50 re f Q'),
           (595,842,b'')])
with patch.object(reader,'_ocr_pdf_page',return_value='입찰공고 참여 조건을 확인한다.') as ocr:
    text,details=reader._extract_pdf_with_audit(pages)
    assert '입찰공고' in text
    assert details['sourceComplete'] is True,details
    assert details['genuinelyBlankPages']==1,details
    assert details['ocrAttemptedPages']==1,details
    assert ocr.call_args.args[1]==0

# HWPX inline pictures point to BinData/image1.bmp and its hp:section has
# no hp:t text spans. The scanner records a deliberate OCR deferral; the
# verified-original repairer performs OCR and retains source provenance.
image=Image.new('RGB',(589,817),(255,255,255))
buf=io.BytesIO();image.save(buf,format='BMP');bmp=buf.getvalue()
section='''<?xml version="1.0" encoding="UTF-8"?>
<hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p><hp:pic/></hp:p>
  <hp:p><hp:pic/></hp:p>
</hp:section>'''
z=io.BytesIO()
with zipfile.ZipFile(z,'w') as w:
    w.writestr('Contents/section0.xml',section)
    w.writestr('BinData/image1.bmp',bmp)
hwpx=z.getvalue()
with patch.dict(os.environ,{'WORKLINKS_RFP_DEFER_OCR':'1'}):
    try:
        reader.extract_with_source_status('영향평가.hwpx',hwpx)
        raise AssertionError('fast scan must defer expensive raster OCR')
    except ValueError as e:
        assert str(e)=='hwpx_image_ocr_deferred_to_repair',str(e)
        assert reader.classify_failure(e)=='hwpx_image_ocr_deferred_to_repair'

with patch.dict(os.environ,{'WORKLINKS_RFP_DEFER_OCR':'0'}),\
     patch.object(reader,'_extract_image_with_audit',
                  return_value='소프트웨어사업 영향평가 결과서 국군의무사령부') as ocr:
    text,evidence=reader.extract_with_source_status('영향평가.hwpx',hwpx)
    assert '영향평가 결과서' in text
    assert evidence['sourceComplete'] is True,evidence
    assert evidence['extractionMethod']=='hwpx_embedded_image_ocr',evidence
    assert ocr.call_count==1,'same BMP referenced twice must OCR once'

# The original two 9-file notices failed as a whole after 6 readable members.
# The presence of image-only HWPX members must NOT discard the 6 valid ones.
outer=io.BytesIO()
with zipfile.ZipFile(outer,'w') as archive:
    archive.writestr('3. 제안요청서.hwpx',
        zipfile.ZipFile if False else hwpx)
    archive.writestr('7. 영향평가 결과서.hwpx',hwpx)
with patch.dict(os.environ,{'WORKLINKS_RFP_DEFER_OCR':'0'}),\
     patch.object(reader,'_extract_image_with_audit',
                  return_value='나라장터 과업 심의위원회 조달 조건') as ocr:
    text,evidence=reader.extract_with_source_status('입찰공고자료.zip',outer.getvalue())
    assert text.count('FILE ')==2,text
    assert '영향평가' in text
    assert evidence['sourceComplete'] is True
    assert evidence['extractionMethod']=='hwpx_embedded_image_ocr'

# Corrupted embedded content must never be recorded as successfully read.
bad=io.BytesIO()
with zipfile.ZipFile(bad,'w') as w:
    w.writestr('Contents/section0.xml',section)
    w.writestr('BinData/image1.bmp',b'corrupted image bytes')
with patch.dict(os.environ,{'WORKLINKS_RFP_DEFER_OCR':'0'}):
    try:
        reader.extract_with_source_status('영향평가.hwpx',bad.getvalue())
        raise AssertionError('corrupt image silently marked as success')
    except ValueError as e:
        assert str(e)=='hwpx_image_ocr_incomplete',str(e)

assert repair.READER_ATTEMPT_VERSION.endswith('embedded-image-v7')
print('RFP_PDF_PIXEL_BLANK_AND_HWPX_EMBEDDED_IMAGE_OCR=PASS')
