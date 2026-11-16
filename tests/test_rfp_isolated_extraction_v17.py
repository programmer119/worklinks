#!/usr/bin/env python3
"""A noisy native PDF/HWP extractor must not break the verified child protocol."""
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair
from rfp_dual_queue import RfpDualQueue,scan_evidence_signature

assert reader._RFP_EXTRACT_CHILD_MARKER==b'\n__WORKLINKS_EXTRACT_RESULT_V2__'
expected={'ok':True,'text':'계약 서류를 정확하게 판독합니다',
          'evidence':{'sourceComplete':True,'pdfPages':1}}
noisy=b'native parser log line 1\nWARN: diagnostic only\n'
framed=noisy+reader._RFP_EXTRACT_CHILD_MARKER+json.dumps(
    expected,ensure_ascii=False).encode('utf-8')
assert reader.decode_extraction_child_result(framed)==(
    expected['text'],expected['evidence'])
try:
    reader.decode_extraction_child_result(noisy+b'{"ok":true}')
except ValueError as err:
    assert str(err)=='isolated_extraction_worker_reply_invalid'
else:
    raise AssertionError('missing final marker accepted')
try:
    reader.decode_extraction_child_result(
        reader._RFP_EXTRACT_CHILD_MARKER+b'{"ok":true,"text":"partial"}')
except ValueError as err:
    assert str(err)=='isolated_extraction_worker_reply_invalid'
else:
    raise AssertionError('partial invalid evidence accepted')

with tempfile.TemporaryDirectory() as folder:
    # Run the ACTUAL production child program with a mock reader that prints
    # before returning successful verified source text.
    Path(folder,'refresh_worklinks_rfp.py').write_text(
        "def extract_with_source_status(name,raw):\n"
        "    print('native-library-side-information',flush=True)\n"
        "    return 'verified '+raw.decode('utf-8'), {'sourceComplete':True}\n")
    child=subprocess.run([sys.executable,'-c',reader._RFP_EXTRACT_CHILD_PROGRAM,
                          folder,'sample.pdf'],
                          input=b'official-source',capture_output=True,
                          timeout=12,check=True)
    assert b'native-library-side-information' in child.stdout
    text,evidence=reader.decode_extraction_child_result(child.stdout)
    assert text=='verified official-source' and evidence['sourceComplete'] is True

assert repair.READER_ATTEMPT_VERSION.startswith('framed-isolated-extract-v')
old={
 'files':[{'name':'contract.pdf',
           'errorCategory':'isolated_extraction_worker_reply_invalid',
           'readable':False,
           'lastReaderAttemptVersion':'real-byte-recursive-office-v16-20261116'}]}
assert len(repair.reader_retry_files(old))==1
recent=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=10)).isoformat()
older=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=140)).isoformat()
old['files'][0].update(lastReaderAttemptVersion=repair.READER_ATTEMPT_VERSION,
                       lastReaderAttemptAt=recent,lastReaderTransientRetryCount=0)
assert not repair.reader_retry_files(old)
old['files'][0]['lastReaderAttemptAt']=older
assert len(repair.reader_retry_files(old))==1
old['files'][0]['lastReaderTransientRetryCount']=1
assert not repair.reader_retry_files(old)

with tempfile.TemporaryDirectory() as folder:
    queue=RfpDualQueue(Path(folder)/'q.sqlite3')
    key='R26BK99999998:000'
    queue.enqueue([('R26BK99999998','000','2099-01-01')],'reader-v1')
    assert queue.scan_wait_reason()=='download_wait'
    claim=queue.claim_download()
    assert claim is not None
    src='https://www.g2b.go.kr/UntyAtchFile/source.pdf'
    meta={'attachments':{'ok':True,'complete':True,
             'items':[{'name':'source.pdf','url':src}]},
          'noticeDocuments':{'ok':True,'complete':True},
          'downloadVerifiedFiles':[{'name':'source.pdf','url':src,'sha256':'b'*64}]}
    queue.downloaded(key,meta,1,1)
    assert queue.scan_wait_reason()=='ready'
    assert len(queue.claim_ready(1))==1
    failed={'manifestComplete':True,'files':[{
       'name':'source.pdf','readable':False,
       'errorCategory':'isolated_extraction_worker_reply_invalid',
       'sourceSha256':'b'*64}]}
    assert queue.scan_finished(key,False,'isolated_extraction_worker_reply_invalid',
                               scan_evidence_signature(failed))
    assert queue.scan_wait_reason()=='source_repair_wait'
    assert queue.ready_count()==0
    assert queue.reopen_changed_scan_evidence({key:failed})==0
print('WORKLINKS_FRAMED_CHILD_AND_BOUNDED_OCR_RESUME_AND_WAIT_STATUS=PASS',flush=True)
