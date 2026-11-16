#!/usr/bin/env python3
"""Verify opt-in dense image OCR recovery is gated and does not fake PDF completion."""
import os,sys,subprocess
from pathlib import Path
from unittest.mock import patch
import pymupdf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair

doc=pymupdf.open()
page=doc.new_page(width=595,height=842)
pix=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,30,30),False)
pix.clear_with(255)
page.insert_image(page.rect,stream=pix.tobytes('png'))
assert 'fill-image' in [x[0] for x in page.get_bboxlog()]
raw=doc.tobytes()
doc.close()

valid=('계약서 정부 사업 시방서 가속기센터 구축 전기공사 내용\n'*16).encode()
with patch.dict(os.environ,{'WORKLINKS_RFP_DENSE_IMAGE_PSM11_OCR':'1',
                            'WORKLINKS_RFP_DENSE_IMAGE_FAST_ONLY':'1'}),\
     patch.object(reader.shutil,'which',return_value='/usr/bin/tesseract'),\
     patch.object(reader.subprocess,'run',
                 return_value=subprocess.CompletedProcess([],0,valid,b'')) as run:
    out=reader._ocr_pdf_page(raw,0,'drawing.pdf')
    assert out==valid.decode()
    assert '--psm' in run.call_args.args[0] and '11' in run.call_args.args[0]
    assert '--dpi' in run.call_args.args[0] and '120' in run.call_args.args[0]

with patch.dict(os.environ,{'WORKLINKS_RFP_DENSE_IMAGE_PSM11_OCR':'1',
                            'WORKLINKS_RFP_DENSE_IMAGE_FAST_ONLY':'1'}),\
     patch.object(reader.shutil,'which',return_value='/usr/bin/tesseract'),\
     patch.object(reader.subprocess,'run',
                 return_value=subprocess.CompletedProcess([],0,b'bad',b'')):
    try:reader._ocr_pdf_page(raw,0,'drawing.pdf')
    except ValueError as e:assert str(e)=='pdf_ocr_dense_image_unreadable'
    else:raise AssertionError('low confidence OCR falsely completed')

file={'name':'drawing.pdf','readable':False,'sourceTextScanComplete':False,
      'errorCategory':'pdf_ocr_incomplete',
      'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
      'lastPerimeterAttemptVersion':repair.EMPTY_PERIMETER_READER_VERSION,
      'lastSparseCoverAttemptVersion':repair.SPARSE_COVER_READER_VERSION,
      'extractionEvidence':{'pdfPages':18,'ocrFailedPages':2,
                            'ocrBatchDeferredPages':0,'ocrRecoveredPages':16,
                            'ocrRestoredPages':16}}
scan={'files':[file]}
with patch.dict(os.environ,{},clear=False):
    os.environ.pop('WORKLINKS_RFP_DENSE_IMAGE_PSM11_OCR',None)
    assert not repair.reader_retry_files(scan), 'do not endlessly retry existing failed PDFs'
with patch.dict(os.environ,{'WORKLINKS_RFP_DENSE_IMAGE_PSM11_OCR':'1'}):
    assert repair.reader_retry_files(scan)==[file]
    assert not repair.reader_retry_files({'files':[dict(file,name='unsafe.docx')]}), 'PDF only'
# Old-version failure cooldown must not block a NEW, verified and explicitly
# scoped OCR strategy. Normal, unscoped runs still honor the cooldown.
pdf_reader=reader.PdfReader if hasattr(reader,'PdfReader') else None
with patch.object(reader,'_pdf_ocr_page_cache',return_value=(None,'sha',{})),\
     patch.object(reader,'_pdf_ocr_failed_page_cooldowns',return_value={0:'old_22s_timeout'}),\
     patch.object(reader,'_ocr_pdf_page',return_value=valid.decode()):
    with patch.dict(os.environ,{'WORKLINKS_RFP_DENSE_IMAGE_PSM11_OCR':'1',
                                'WORKLINKS_RFP_DENSE_IMAGE_FAST_ONLY':'1'}):
        extracted,evidence=reader.extract_with_source_status('drawing.pdf',raw)
        assert evidence['sourceComplete'] is True,evidence
        assert '계약서 정부 사업' in extracted
    with patch.dict(os.environ,{'WORKLINKS_RFP_DENSE_IMAGE_PSM11_OCR':'0',
                                'WORKLINKS_RFP_DENSE_IMAGE_FAST_ONLY':'0'}):
        try:
            _,evidence=reader.extract_with_source_status('drawing.pdf',raw)
            assert evidence['sourceComplete'] is False,evidence
        except ValueError as error:
            assert str(error)=='pdf_ocr_incomplete'

print('WORKLINKS_DENSE_IMAGE_PSM11_OPTIN_CONFIDENCE_AND_SOURCE_SCOPE=PASS')
