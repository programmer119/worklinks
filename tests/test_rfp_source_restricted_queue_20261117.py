#!/usr/bin/env python3
"""Protected originals are blocked, not falsely scanned or endlessly retried."""
import json,runpy,tempfile,sqlite3,time
from pathlib import Path
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1]
x=runpy.run_path(str(root/'scripts/rfp_dual_queue.py'),run_name='test_protected_queue')
Queue=x['RfpDualQueue']
sha=lambda n:str(n)*64
with tempfile.TemporaryDirectory() as tmp:
    q=Queue(Path(tmp)/'queue.sqlite3')
    rows=[('R26BK01818624','000','2026-12-31'),
          ('R26BK01813949','000','2026-12-31'),
          ('R26BK01811830','000','2026-12-31')]
    q.enqueue(rows,'25:3:4:2')
    keys=[n+':000' for n,_,_ in rows]
    def verified(name,hash_char):
        return {'name':name,'sha256':sha(hash_char),'url':'https://www.g2b.go.kr/test/'+name}
    def readable(name,char):
        return {'name':name,'readable':True,'sourceTextScanComplete':True,'sourceSha256':sha(char)}
    protected={'name':'DRM 보안 원본.hwpx','readable':False,
               'errorCategory':'drm_protected_original_requires_authorized_decryption'}
    evidence={
       keys[0]:{'manifestComplete':True,'files':[readable('공고문.pdf','a'),protected]},
       keys[1]:{'manifestComplete':True,'files':[readable('공고문.pdf','b'),protected,
                                                     {'name':'과업서.pdf','readable':False,'errorCategory':'pdf_ocr_incomplete'}]},
       keys[2]:{'manifestComplete':True,'files':[readable('공고문.pdf','c'),
                                                     {'name':'기술협약서.pdf','readable':False,'errorCategory':'pdf_ocr_incomplete'}]}}
    for i,key in enumerate(keys):
        files=evidence[key]['files']
        receipts=[verified(f['name'],str(i+1)) for f in files]
        metadata={'downloadVerifiedFiles':receipts,'attachments':{'ok':True,'complete':True,'items':receipts}}
        with q.connect() as db:
            db.execute("""UPDATE rfp_dual_notices SET download_status='ready',
                       scan_status='retry',metadata_json=?,download_total=?,
                       download_done=?,scan_retry_epoch=?,last_error='scan_source_incomplete'
                       WHERE notice_key=?""",(json.dumps(metadata,ensure_ascii=False),len(files),len(files),time.time()+3600,key))
    assert x['verified_protected_only_source'](evidence[keys[0]])
    assert not x['verified_protected_only_source'](evidence[keys[1]])
    assert not x['verified_protected_only_source'](evidence[keys[2]])
    assert q.hold_verified_source_restrictions(evidence)==1
    with q.connect() as db:
        states={key:db.execute("SELECT scan_status,scan_retry_epoch,last_error FROM rfp_dual_notices WHERE notice_key=?",(key,)).fetchone() for key in keys}
    assert states[keys[0]][0]=='source_restricted' and states[keys[0]][1]==0,states
    assert 'source_restricted' in states[keys[0]][2]
    assert states[keys[1]][0]=='retry' and states[keys[2]][0]=='retry'
    # A recovered original can reopen a true scan only after full SHA evidence.
    complete=dict(evidence)
    complete[keys[0]]={'manifestComplete':True,
                      'files':[readable('공고문.pdf','a'),readable('DRM 보안 원본.hwpx','e')]}
    assert q.reopen_changed_scan_evidence(complete)==1
    with q.connect() as db:
        state=db.execute("SELECT scan_status,scan_retry_epoch FROM rfp_dual_notices WHERE notice_key=?",(keys[0],)).fetchone()
    assert state==('pending',0.0),state
    print('SOURCE_RESTRICTED_QUEUE_REGRESSION_PASS')
