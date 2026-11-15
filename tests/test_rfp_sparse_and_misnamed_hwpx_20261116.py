#!/usr/bin/env python3
"""OCR sparse-page fallback and official HWPML XML disguised as .hwpx.

All fixtures are local; no government network or live database writes.
"""
import io
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as rfp
from pypdf import PdfWriter

hwpml=b'''<?xml version="1.0" encoding="UTF-8"?>
<HWPML><BODY><P>Official procurement qualifications apply</P>
<P>Technical staffing and verification requirements</P></BODY></HWPML>'''
assert rfp.detected_source_format('sample.hwpx',hwpml)=='hwpml_xml'
value=rfp.extract('sample.hwpx',hwpml)
assert 'Official procurement' in value and 'staffing' in value,value
assert rfp.detected_source_format('sample.hwp',hwpml)=='hwpml_xml'
assert 'Technical staffing' in rfp.extract('sample.hwp',hwpml)
for bad in (b'<?xml version="1.0"?><BAD><p>contents</p></BAD>',
            b'<?xml version="1.0"?><HWPML><p>truncated'):
    try:rfp.extract('sample.hwpx',bad)
    except ValueError as exc:
        assert rfp.classify_failure(exc) in ('unrecognized_hwpml_root','hml_xml_parse_failed')
    else:raise AssertionError('Invalid HWPML passed')
# Real ZIP-based HWPX continues to use its existing reader.
import zipfile
z=io.BytesIO()
with zipfile.ZipFile(z,'w') as archive:
    archive.writestr('Contents/section0.xml',
        '<hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:p><hp:t>입찰자격 검증과 납품 기술 지원 조건</hp:t></hp:p></hp:section>')
assert '입찰자격 검증' in rfp.extract('document.hwpx',z.getvalue())

pdf=io.BytesIO()
writer=PdfWriter();writer.add_blank_page(width=595,height=842);writer.write(pdf)
pdf=pdf.getvalue()
def make_reply(mode):
    value={
        '3':'AB',
        '6':'기술지원 원문 및 공급 조건',
        '11':'기술지원 원문 및 공급 조건, 상주인력 확인'
    }[mode]
    return SimpleNamespace(returncode=0,stdout=value.encode('utf-8'),stderr=b'')
calls=[]
def run_fake(command,**kwargs):
    mode=command[command.index('--psm')+1]
    calls.append((mode,kwargs['input']))
    return make_reply(mode)
with patch.object(rfp.shutil,'which',return_value='/usr/bin/tesseract'),\
     patch.object(rfp.subprocess,'run',side_effect=run_fake):
    text=rfp._ocr_pdf_page(pdf,0)
assert '상주인력' in text,text
assert [x[0] for x in calls]==['3','6','11'],calls
assert calls[0][1]==calls[1][1]==calls[2][1],'OCR render unexpectedly repeated'
calls.clear()
def sufficient(command,**kwargs):
    calls.append(command[command.index('--psm')+1])
    return SimpleNamespace(returncode=0,stdout='정상적인 기술지원 문서 문구'.encode(),stderr=b'')
with patch.object(rfp.shutil,'which',return_value='/usr/bin/tesseract'),\
     patch.object(rfp.subprocess,'run',side_effect=sufficient):
    assert '정상적인' in rfp._ocr_pdf_page(pdf,0)
assert calls==['3'],'Normal OCR should not try extra PSMs'
calls.clear()
def too_sparse(command,**kwargs):
    calls.append(command[command.index('--psm')+1])
    return SimpleNamespace(returncode=0,stdout='A'.encode(),stderr=b'')
with patch.object(rfp.shutil,'which',return_value='/usr/bin/tesseract'),\
     patch.object(rfp.subprocess,'run',side_effect=too_sparse):
    _,evidence=rfp.extract_with_source_status('sparse.pdf',pdf)
assert evidence['sourceComplete'] is False
assert evidence['ocrFailedPages']==1
assert evidence['pdfSources'][0]['ocrFailureDetails'][0]['reason']=='ocr_text_below_12_alphanumeric'
print('RFP_SPARSE_300DPI_PSM6_PSM11_AND_HWPML_XML_FIX=PASS')
