#!/usr/bin/env python3
"""No download or false success: recover only fully CRC-proven six-byte HWPX truncation."""
import io,os,sys,zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as rfp
import repair_open_rfp_cached_attachments as repair

def archive(members):
    io_bytes=io.BytesIO()
    with zipfile.ZipFile(io_bytes,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,content in members:z.writestr(name,content)
    return io_bytes.getvalue()

hwpx=archive([
    ('mimetype',b'application/hwp+zip'),
    ('Contents/header.xml',b'<header><p><t>PUBLIC RECORD</t></p></header>'),
    ('Contents/section0.xml','<document><p><t>검증 가능한 과업의 제출 자료와 적용 조건</t></p></document>'.encode('utf-8'))])
assert zipfile.is_zipfile(io.BytesIO(hwpx))
damaged=hwpx[:-6]
assert not zipfile.is_zipfile(io.BytesIO(damaged))
repaired=rfp.recover_crc_verified_truncated_hwpx_eocd(damaged)
assert repaired is not None
assert repaired[0]==hwpx
assert repaired[1]==3
text,evidence=rfp.extract_with_source_status('verified-source.hwpx',damaged)
assert '검증 가능한 과업' in text,(text,evidence)
assert evidence['sourceComplete'] is True,evidence
assert evidence['crcVerifiedArchiveEndRecordRecovery']==[{
    'sourceFile':'verified-source.hwpx','missingEndRecordBytes':6,'crcVerifiedMembers':3}]
bundle=archive([('verified-source.hwpx',damaged)])
text,evidence=rfp.extract_with_source_status('official-bundle.zip',bundle)
assert '검증 가능한 과업' in text
assert evidence['sourceComplete'] is True

assert rfp.recover_crc_verified_truncated_hwpx_eocd(hwpx[:-7]) is None
bad=bytearray(damaged)
bad[100]^=0x01
assert rfp.recover_crc_verified_truncated_hwpx_eocd(bytes(bad)) is None

def failed(name,reason,evidence=None):
    return {'name':name,'readable':False,'errorCategory':reason,
      'extractionEvidence':evidence or {},'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
      'lastReaderTransientRetryCount':2,'lastReaderAttemptAt':'2026-11-18T01:00:00+00:00',
      'lastPerimeterAttemptVersion':repair.EMPTY_PERIMETER_READER_VERSION,
      'lastSparseCoverAttemptVersion':repair.SPARSE_COVER_READER_VERSION}
badzip=failed('제안요청서 등.zip','file_extract_failure')
short=failed('2. 규격서.pdf','pdf_ocr_incomplete',{
    'pdfPages':5,'ocrFailedPages':1,'ocrBatchDeferredPages':0})
with patch.dict(os.environ,{'WORKLINKS_RFP_TARGETED_TRUNCATED_HWPX':'1',
    'WORKLINKS_RFP_SHORT_VECTOR_FAST_OCR':'1','WORKLINKS_RFP_SHORT_VECTOR_FAST_ONLY':'1'}):
    picked=repair.reader_retry_files({'files':[badzip,short]})
    assert picked==[badzip,short],picked
    badzip['lastTruncatedHwpxAttemptVersion']=repair.TRUNCATED_HWPX_READER_VERSION
    short['lastShortVectorAttemptVersion']=repair.SHORT_VECTOR_READER_VERSION
    assert repair.reader_retry_files({'files':[badzip,short]})==[]
print('RFP_TRUNCATED_HWPX_AND_VECTOR_SCOPED_RETRY=PASS')
