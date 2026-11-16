#!/usr/bin/env python3
"""Strict all-perimeter vector lines-only PDF page verification regression."""
import sys,types
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair

class P:
    def __init__(self,x,y):self.x=x;self.y=y
class Rect:
    width=595.276
    height=841.89
class Page:
    rect=Rect()
    def __init__(self):
        self.shapes=[
          ('left',P(56.64,28.32),P(56.64,791.04)),
          ('right',P(538.56,28.32),P(538.56,791.04)),
          ('top',P(56.64,28.32),P(538.8,28.32)),
          ('bottom',P(56.64,790.80),P(538.8,790.80))]
        self.text=''
        self.images=[]
    def get_text(self,mode):return self.text
    def get_images(self,full):return self.images
    def get_bboxlog(self):return [('stroke-path',None) for _ in self.shapes]
    def get_drawings(self):
        return [{'fill':None,'type':'s','width':0.24,
                 'items':[('l',p,q)]} for _,p,q in self.shapes]
class Document:
    def __init__(self,p):self.page=p
    def load_page(self,n):return self.page
p=Page();doc=Document(p)
with patch.dict(sys.modules,{'pymupdf':types.SimpleNamespace()}):
    assert reader._pdf_verified_perimeter_only_frame(b'sha-verified',7,{'document':doc})
    p.text='조달 입찰 요구 사항'
    assert not reader._pdf_verified_perimeter_only_frame(b'sha-verified',7,{'document':doc})
    p.text=''
    p.images=[('image',)]
    assert not reader._pdf_verified_perimeter_only_frame(b'sha-verified',7,{'document':doc})
    p.images=[]
    p.shapes.append(('middle',P(200,200),P(350,200)))
    assert not reader._pdf_verified_perimeter_only_frame(b'sha-verified',7,{'document':doc})
    p.shapes.pop()
    p.shapes[0]=('left',P(200,28),P(200,791))
    assert not reader._pdf_verified_perimeter_only_frame(b'sha-verified',7,{'document':doc})
f={'name':'contract.pdf','errorCategory':'pdf_ocr_incomplete',
    'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
    'lastSparseCoverAttemptVersion':repair.SPARSE_COVER_READER_VERSION,
    'extractionEvidence':{'pdfPages':8,'ocrFailedPages':1,'ocrBatchDeferredPages':0},
    'readable':False,'sourceTextScanComplete':False}
assert len(repair.reader_retry_files({'files':[f]}))==1
f['lastPerimeterAttemptVersion']=repair.EMPTY_PERIMETER_READER_VERSION
assert not repair.reader_retry_files({'files':[f]})
print('FOUR_PERIMETER_PATHS_ONLY_NO_TEXT_IMAGE_VIOLATIONS_REJECTED=PASS')
