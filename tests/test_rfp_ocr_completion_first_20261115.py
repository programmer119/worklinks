#!/usr/bin/env python3
"""Offline regression: finish short pending bids and never timeout long PDF OCR pass."""
import io
import os
import sys
import tempfile
import datetime as dt
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair
from pypdf import PdfWriter
from pypdf.generic import NameObject,DecodedStreamObject

def pending(name,pages):
    return {'name':name,'readable':False,'errorCategory':'pdf_ocr_incomplete',
      'sourceTextScanComplete':False,
      'extractionEvidence':{'pdfFiles':1,'pdfPages':pages,'ocrRecoveredPages':24,
              'ocrBatchDeferredPages':pages-24,'ocrFailedPages':0}}
short=pending('26-page.pdf',26)
long=pending('91-page.pdf',91)
one={'files':[short]}
two={'files':[long]}
assert repair.repair_completion_score(one,[short])==(0,1,2)
assert repair.repair_completion_score(two,[long])==(0,1,67)
now=dt.datetime(2026,11,15,tzinfo=dt.timezone.utc)
candidates=[
    (0,now,'long',{},'verified_download_queue',1,repair.repair_completion_score(two,[long])),
    (0,now+dt.timedelta(days=3),'short',{},'verified_download_queue',1,repair.repair_completion_score(one,[short]))]
chosen,files=repair.choose_repair_batch(candidates,limit=1,max_files=2)
assert [r[0] for r in chosen]==['short'],chosen
# A hard HWP/ZIP notice must not repeatedly occupy the first slot while a
# single-OCR-file notice is ready to become fully verified.
koica=( -1,now,'koica',{},'verified_download_queue',2,(0,2,9))
one_pdf=(0,now,'pdf-one-left',{},'verified_download_queue',1,(0,1,2))
selected,_=repair.choose_repair_batch([koica,one_pdf],limit=1,max_files=2)
assert selected[0][0]=='pdf-one-left',selected
# No progress without previously completed pages must NOT cause repeat forever.
broken={'files':[dict(long,lastReaderAttemptVersion=repair.READER_ATTEMPT_VERSION)]}
assert repair.reader_retry_files(broken)==broken['files']
fatal={'files':[{'name':'bad.zip','readable':False,'errorCategory':'nested_archive_requires_review',
 'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION}]}
assert repair.reader_retry_files(fatal)==[]

writer=PdfWriter()
for i in range(26):
    page=writer.add_blank_page(width=595,height=842)
    stream=DecodedStreamObject()
    stream.set_data(b'q 0 0 1 rg 10 10 90 50 re f Q')
    page[NameObject('/Contents')]=writer._add_object(stream)
buffer=io.BytesIO()
writer.write(buffer)
with tempfile.TemporaryDirectory() as tmp:
    fakeclock=[0.0]
    def fake_ocr(raw,index):
        fakeclock[0]+=15.0
        return '등록 자격 조건 확인을 완료한 OCR 문서 '+str(index)
    with patch.dict(os.environ,{'WORKLINKS_RFP_OCR_PAGE_CACHE_DB':str(Path(tmp)/'page.sqlite3'),
       'WORKLINKS_RFP_DEFER_OCR':'0','WORKLINKS_RFP_OCR_PASS_SECONDS':'115'}),\
       patch.object(reader.time,'monotonic',side_effect=lambda:fakeclock[0]),\
       patch.object(reader,'_ocr_pdf_page',side_effect=fake_ocr) as scan:
        previous=0
        for _ in range(10):
            _,info=reader.extract_with_source_status('supplier.pdf',buffer.getvalue())
            assert info['ocrAttemptedPages']<=6,info
            assert info['ocrRecoveredPages']>previous,info
            assert info['ocrFailedPages']==0,info
            previous=info['ocrRecoveredPages']
            if info['sourceComplete']:break
        assert info['sourceComplete'] is True,info
        assert info['ocrRecoveredPages']==26,info
        assert scan.call_count==26,scan.call_count
print('OCR_COMPLETION_FIRST_AND_DEADLINE_BOUND_PAGE_PASS=PASS')
