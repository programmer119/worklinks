#!/usr/bin/env python3
"""Offline regression: verified long native PDFs use MuPDF with pypdf fallback."""
import io,os,re,sys
from pathlib import Path
from unittest.mock import patch
from pypdf._page import PageObject
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader

doc=pymupdf.open()
for i in range(64):
    page=doc.new_page(width=595,height=842)
    if i==9:
        page.draw_rect(pymupdf.Rect(50,80,450,650),color=(0,0,0),fill=(0,0,0))
    else:
        page.insert_text((54,100),
            'Tender No %d eligibility 4 insurance on site work technical staffing' % i,
            fontsize=10)
        page.insert_text((54,140),
            'Software development contract and qualification evidence passage',fontsize=10)
raw=doc.tobytes()
doc.close()
env={'WORKLINKS_RFP_OCR_REGION_PROBE':'0','WORKLINKS_RFP_DEFER_OCR':'0',
     'WORKLINKS_RFP_FAST_SKIP_PYPDF_NATIVE':'1'}
original_extract=PageObject.extract_text
calls={'n':0}

def counting(self,*args,**kwargs):
    calls['n']+=1
    return original_extract(self,*args,**kwargs)

norm=lambda s:re.sub(r'\s+','',s)

with patch.dict(os.environ,dict(env,WORKLINKS_RFP_FAST_MUPDF_NATIVE='0')), \
     patch.object(reader,'_ocr_pdf_page',return_value='한국어 스캔 페이지 실제 OCR 결과'):
    baseline,evidence=reader.extract_with_source_status('64-page.pdf',raw)
    assert evidence['ocrAttemptedPages']==1,evidence

calls['n']=0
with patch.dict(os.environ,dict(env,WORKLINKS_RFP_FAST_MUPDF_NATIVE='1')), \
     patch.object(PageObject,'extract_text',counting), \
     patch.object(reader,'_ocr_pdf_page',return_value='한국어 스캔 페이지 실제 OCR 결과'):
    faster,stats=reader.extract_with_source_status('64-page.pdf',raw)
    assert norm(faster)==norm(baseline), 'native text must not lose any nonspace characters'
    assert stats['sourceComplete'] is True,stats
    assert stats['ocrNativeMuPdfAcceptedFiles']==1,stats
    assert stats['ocrNativeMuPdfTextPages']>=40,stats
    assert stats['ocrNativeMuPdfVerifiedPages']>=3,stats
    assert stats['ocrAttemptedPages']==1,stats
    assert calls['n']<20,calls
    print('RFP_FAST_MUPDF_NATIVE_LONG_PDF_MATCH=PASS',stats['ocrNativeMuPdfVerifiedPages'],
          stats['ocrNativeMuPdfTextPages'],calls['n'])

# Deliberately force a mismatch on one validated pypdf sample page.
# The complete file must use pypdf and never substitute different evidence.
calls['n']=0
def incorrect_baseline(self,*args,**kwargs):
    calls['n']+=1
    return 'Different source content from native pypdf'
with patch.dict(os.environ,dict(env,WORKLINKS_RFP_FAST_MUPDF_NATIVE='1')), \
     patch.object(PageObject,'extract_text',incorrect_baseline), \
     patch.object(reader,'_ocr_pdf_page',return_value='한국어 스캔 페이지 실제 OCR 결과'):
    baseline_fallback,stats=reader.extract_with_source_status('64-page.pdf',raw)
    assert stats['ocrNativeMuPdfAcceptedFiles']==0,stats
    assert stats['pdfSources'][0]['ocrNativeMuPdfDecision']=='native_text_sample_mismatch',stats
    assert 'Different source content' in baseline_fallback
    assert calls['n']>=64,calls
print('RFP_FAST_MUPDF_NATIVE_SAFE_FALLBACK_ON_MISMATCH=PASS')
