#!/usr/bin/env python3
"""Bounded consensus for 4-11 character Korean PDF title/logo page only."""
import os,sys,tempfile,hashlib,datetime as dt
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
import refresh_worklinks_rfp as rfp
import repair_open_rfp_cached_attachments as R

checked=rfp.verified_sparse_ocr_text
assert checked('건축 시방서\n','건축 시방서\n',0.00051,2).strip()=='건축 시방서'
assert checked('기계설비 시방서','기계설비 시방서',0.00066,2).strip()=='기계설비 시방서'
assert checked('Hele 공영홈쇼핑','Hele 공영홈쇼핑',0.00847,5).strip()=='Hele 공영홈쇼핑'
assert not checked('3. 시 방 서','3. Al at Al',0.00222,1)
assert not checked('시방서','시방서',0.1,2)
assert not checked('기계설비 시방서','기계설비 시방서',0.2,2)
assert not checked('기계설비 시방서','기계설비 시방서',0.002,8)
assert not checked('Hello','Hello',0.001,1)
assert not checked('','',0.001,1)

# Visually checked actual official SHA-verified PDF page 1: only
# "3. 시 방 서" on one full-page image, ink ratio 0.00222. A filename-exact
# title may be accepted even if PSM11 garbles the same sparse title.
assert rfp.verified_sparse_title_page('3. 시 방 서','시방서.pdf',0,0.00222,1).strip()=='3. 시 방 서'
assert not rfp.verified_sparse_title_page('3. 시 방 서','다른문서.pdf',0,0.00222,1)
assert not rfp.verified_sparse_title_page('3. 시 방 서','시방서.pdf',1,0.00222,1)
assert not rfp.verified_sparse_title_page('3. 시 방 서','시방서.pdf',0,0.02,1)
assert not rfp.verified_sparse_title_page('3. 시 방 서','시방서.pdf',0,0.00222,2)

f={'name':'verified-cover.pdf','readable':False,
   'sourceTextScanComplete':False,'errorCategory':'pdf_ocr_incomplete',
   'lastReaderAttemptVersion':R.READER_ATTEMPT_VERSION,
   'extractionEvidence':{'pdfFiles':1,'pdfPages':34,'ocrBatchDeferredPages':0,
      'ocrFailedPages':1}}
scan={'files':[f]}
assert len(R.reader_retry_files(scan))==1
f['lastSparseCoverAttemptVersion']=R.SPARSE_COVER_READER_VERSION
f['lastPerimeterAttemptVersion']=R.EMPTY_PERIMETER_READER_VERSION
assert not R.reader_retry_files(scan)
f.pop('lastSparseCoverAttemptVersion')
f['extractionEvidence']['ocrBatchDeferredPages']=4
assert not R.reader_retry_files(scan)
f['extractionEvidence']['ocrBatchDeferredPages']=0
f['extractionEvidence']['ocrFailedPages']=3
assert not R.reader_retry_files(scan)

with tempfile.TemporaryDirectory() as folder:
    os.environ['WORKLINKS_RFP_OCR_PAGE_CACHE_DB']=str(Path(folder)/'cache.sqlite3')
    try:
        original=b'full original PDF byte content for SHA-based text cache'
        db,digest,cached=rfp._pdf_ocr_page_cache(original)
        assert cached=={}
        word='기계설비 시방서'
        db.execute('''INSERT INTO rfp_pdf_ocr_page_receipts
            (pdf_sha256,page_index,reader_version,text,text_sha256,stored_at)
            VALUES(?,?,?,?,?,?)''',
            (digest,0,rfp.SPARSE_OCR_PAGE_CACHE_VERSION,word,
             hashlib.sha256(word.encode()).hexdigest(),
             dt.datetime.now(dt.timezone.utc).isoformat()))
        db.commit();db.close()
        db,digest,cached=rfp._pdf_ocr_page_cache(original)
        assert cached[0]==word,'validated sparse 7-character page failed SHA cache'
        db.close()
    finally:
        os.environ.pop('WORKLINKS_RFP_OCR_PAGE_CACHE_DB',None)
print('SHA_VERIFIED_SPARSE_COVER_TWO_MODE_AGREEMENT_AND_CACHE_RETRY_GATES=PASS')
