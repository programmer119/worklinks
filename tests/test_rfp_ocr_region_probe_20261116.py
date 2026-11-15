#!/usr/bin/env python3
"""No-network regression: experimental ROI never changes legal OCR output."""
import io,os,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader

writer=PdfWriter()
page=writer.add_blank_page(width=595,height=842)
stream=DecodedStreamObject()
stream.set_data(b'q 0 0 0 rg '+
    b' '.join((b'90 %d 420 3 re f' % y) for y in range(150,691,40))+b' Q')
page[NameObject('/Contents')]=writer._add_object(stream)
out=io.BytesIO()
writer.write(out)
raw=out.getvalue()
baseline='입찰 참가자격 및 4대보험 확인'
experimental='입찰 참가자격 및 상주인원 확인'
outputs=[SimpleNamespace(returncode=0,stdout=t.encode('utf-8'),stderr=b'')
         for t in (baseline,experimental)]
context={'raw':raw,'document':None,'pdfOpenSeconds':0.0,
         'renderSeconds':0.0,'tesseractSeconds':0.0,'renderPixels':0}
try:
    with patch.dict(os.environ,{'WORKLINKS_RFP_OCR_COLORSPACE':'gray',
                                  'WORKLINKS_RFP_OCR_REGION_PROBE':'1',
                                  'WORKLINKS_RFP_OCR_REGION_PROBE_SAMPLE':'1'}),\\
         patch.object(reader.subprocess,'run',side_effect=outputs) as call:
        reader._DOCUMENT_SCAN.ocr_render_cache=context
        actual=reader._ocr_pdf_page(raw,0)
        assert actual==baseline,(actual,baseline)
        assert call.call_count==2,call.call_count
        first=call.call_args_list[0].args[0]
        second=call.call_args_list[1].args[0]
        assert first[first.index('--psm')+1]=='3',first
        assert second[second.index('--psm')+1]=='4',second
        for command in (first,second):
            assert command[command.index('--dpi')+1]=='300',command
            assert command[command.index('-l')+1]=='kor+eng',command
        assert context['regionProbeDone'] is True
        probe=context['regionProbe'][0]
        assert probe['status']=='compared',probe
        assert probe['exactMatch'] is False,probe
        assert 0.05<probe['areaRatio']<0.82,probe
        assert '입찰' not in str(probe),'source content must not enter telemetry'
finally:
    if context.get('document') is not None:context['document'].close()
    if hasattr(reader._DOCUMENT_SCAN,'ocr_render_cache'):
        del reader._DOCUMENT_SCAN.ocr_render_cache
print('RFP_ROI_PROBE_300DPI_SAFE_BASELINE_UNCHANGED=PASS')
