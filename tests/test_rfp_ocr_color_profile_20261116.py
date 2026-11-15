#!/usr/bin/env python3
"""Verify 300-DPI RGB default, opt-in gray and exact per-page profiling."""
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader

writer=PdfWriter()
page=writer.add_blank_page(width=300,height=430)
stream=DecodedStreamObject()
stream.set_data(b'q 0 0 1 rg 10 10 90 50 re f Q')
page[NameObject('/Contents')]=writer._add_object(stream)
buffer=io.BytesIO()
writer.write(buffer)
raw=buffer.getvalue()
result_text='입찰 참가 자격 조달청 한국어 영어 증빙 서류 확인'

def run_color(color=None):
    settings={'WORKLINKS_RFP_OCR_COLORSPACE':color} if color else {}
    with patch.dict(os.environ,settings,clear=False),\
         patch.object(reader.subprocess,'run',return_value=SimpleNamespace(
             returncode=0,stdout=result_text.encode(),stderr=b'')) as mock:
        if not color:
            os.environ.pop('WORKLINKS_RFP_OCR_COLORSPACE',None)
        text,evidence=reader.extract_with_source_status('fixture.pdf',raw)
        args=mock.call_args
        image=Image.open(io.BytesIO(args.kwargs['input']))
        image.load()
        return text,evidence,image.mode,args.args[0]

original=run_color()
gray=run_color('gray')
assert original[0]==gray[0]==result_text
assert original[2]=='RGB',original[2]
assert gray[2]=='L',gray[2]
for item,mode in [(original,'rgb'),(gray,'gray')]:
    profile=item[1]['pdfSources'][0]['ocrPageProfiles']
    assert len(profile)==1,profile
    assert profile[0]['colorspace']==mode,profile
    assert profile[0]['effectiveDpi']==300.0,profile
    assert profile[0]['pixels']>0,profile
    assert profile[0]['pngBytes']>0,profile
    assert profile[0]['renderSeconds']>=0,profile
    assert profile[0]['tesseractSeconds']>=0,profile
    assert item[3][item[3].index('--psm')+1]=='3'
    assert item[3][item[3].index('-l')+1]=='kor+eng'
assert original[1]['sourceComplete'] is True
assert gray[1]['sourceComplete'] is True
print('RFP_OCR_300DPI_OPT_IN_GRAY_AND_PER_PAGE_PROFILE=PASS')
