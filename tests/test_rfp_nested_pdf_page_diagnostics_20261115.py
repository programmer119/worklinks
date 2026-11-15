#!/usr/bin/env python3
"""Seven-page ZIP PDF: preserve the exact failing member, page and OCR error."""
import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import refresh_worklinks_rfp as reader

writer = PdfWriter()
for _ in range(7):
    page = writer.add_blank_page(width=595, height=842)
    stream = DecodedStreamObject()
    stream.set_data(b'q 0 0 1 rg 10 10 90 50 re f Q')
    page[NameObject('/Contents')] = writer._add_object(stream)
pdf_file = io.BytesIO()
writer.write(pdf_file)
zip_file = io.BytesIO()
with zipfile.ZipFile(zip_file, 'w') as archive:
    archive.writestr('pdf/세부규격서.pdf', pdf_file.getvalue())

def simulated_ocr(_raw, index):
    if index == 6:
        raise subprocess.TimeoutExpired(cmd='tesseract', timeout=22)
    return '입찰 참가자격 및 세부 규격 검토 근거 ' + str(index)

with patch.dict(os.environ, {'WORKLINKS_RFP_DEFER_OCR': '0'}), \
     patch.object(reader, '_ocr_pdf_page', side_effect=simulated_ocr):
    text, evidence = reader.extract_with_source_status('규격서 등.zip', zip_file.getvalue())
    sources = evidence['pdfSources']
    assert len(sources) == 1, evidence
    source = sources[0]
    assert source['sourceFile'] == 'pdf/세부규격서.pdf', source
    assert source['pdfPages'] == 7, source
    assert source['ocrRecoveredPages'] == 6, source
    assert source['ocrFailedPages'] == 1, source
    assert source['unresolvedPages'] == [7], source
    assert source['ocrFailureDetails'] == [{'page': 7, 'reason': 'ocr_timeout_22s'}], source
    assert evidence['sourceComplete'] is False, evidence
    assert 'FILE pdf/세부규격서.pdf' in text, text

print('RFP_NESTED_PDF_PAGE_DIAGNOSTICS=PASS')
