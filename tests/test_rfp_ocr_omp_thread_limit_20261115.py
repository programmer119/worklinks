#!/usr/bin/env python3
"""No-network unit contract: same Tesseract OCR, controlled OpenMP CPU work."""
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject

pdf=PdfWriter()
page=pdf.add_blank_page(width=300,height=430)
stream=DecodedStreamObject()
stream.set_data(b'q 0 0 1 rg 10 10 90 50 re f Q')
page[NameObject('/Contents')]=pdf._add_object(stream)
buf=io.BytesIO();pdf.write(buf)
expected='입찰공고문 조달계약 기술지원 협약서 한국어 영어 테스트'
original_threads=os.environ.get('OMP_THREAD_LIMIT')
with patch.dict(os.environ,{'OMP_THREAD_LIMIT':'8'}),\
     patch.object(reader.subprocess,'run',return_value=SimpleNamespace(
         returncode=0,stdout=expected.encode('utf-8'),stderr=b'')) as command:
    text=reader._ocr_pdf_page(buf.getvalue(),0)
    assert text==expected,text
    kw=command.call_args.kwargs
    args=command.call_args.args[0]
    assert args[:3]==['tesseract','stdin','stdout'],args
    assert args[args.index('-l')+1]=='kor+eng',args
    assert args[args.index('--psm')+1]=='3',args
    assert int(args[args.index('--dpi')+1])>=72,args
    assert reader.PDF_OCR_TARGET_DPI==300
    assert reader.PDF_OCR_TESSERACT_OMP_THREADS==1
    assert kw['timeout']==22,kw
    assert kw['check'] is False,kw
    assert kw['env']['OMP_THREAD_LIMIT']=='1',kw
    assert os.environ['OMP_THREAD_LIMIT']=='8','must not alter host-global thread setting'
    assert kw['input'].startswith(b'\x89PNG\r\n\x1a\n')
assert os.environ.get('OMP_THREAD_LIMIT')==original_threads
print('RFP_PDF_OCR_OMP1_SAME_DPI_PSM_LANG_TIMEOUT_NO_HOST_ENV_CHANGE=PASS')
