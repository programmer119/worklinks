#!/usr/bin/env python3
"""A confirmed malformed cached original takes precedence over old backlog."""
import sys,tempfile,datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rfp_dual_queue import RfpDualQueue
with tempfile.TemporaryDirectory() as directory:
    queue=RfpDualQueue(Path(directory)/'queue.sqlite3')
    notices=[('R26BK00000001','000','2099-12-31'),
             ('R26BK00000002','000','2099-12-31'),
             ('R26BK00000003','000','2099-12-31')]
    assert queue.enqueue(notices,'v1')==3
    with queue.connect() as db:
        db.execute("""UPDATE rfp_dual_notices
          SET last_error='cached_original_missing'
          WHERE notice_key='R26BK00000003:000'""")
    first=queue.claim_download()
    assert first[0]=='R26BK00000003:000',first
    next_claim=queue.claim_download()
    assert next_claim[0]=='R26BK00000001:000',next_claim
# After successfully downloading a replacement, the recovered notice
# must be selected for scanning before older ordinary downloaded items.
with tempfile.TemporaryDirectory() as directory:
    queue=RfpDualQueue(Path(directory)/'queue.sqlite3')
    notices=[('R26BK00000011','000','2099-12-31'),
             ('R26BK00000012','000','2099-12-31')]
    queue.enqueue(notices,'v1')
    key_a,_=queue.claim_download()
    meta={'attachments':{'ok':True,'complete':True,
           'items':[{'name':'notice.pdf','url':'https://www.g2b.go.kr/UntyAtchFile/notice.pdf'}]},
          'noticeDocuments':{'ok':True,'complete':True},
          'downloadVerifiedFiles':[{'name':'notice.pdf',
            'url':'https://www.g2b.go.kr/UntyAtchFile/notice.pdf','sha256':'a'*64,'bytes':400}]}
    queue.downloaded(key_a,meta,1,1)
    key_b,_=queue.claim_download()
    # This original failed structure validation and was replaced.
    with queue.connect() as db:
        db.execute("UPDATE rfp_dual_notices SET last_error='cached_original_missing' WHERE notice_key=?",(key_b,))
    queue.downloaded(key_b,meta,1,1)
    with queue.connect() as db:
        mark=db.execute("SELECT last_error FROM rfp_dual_notices WHERE notice_key=?",(key_b,)).fetchone()[0]
    assert mark=='source_integrity_recovered_pending_scan',mark
    assert queue.claim_ready(1)[0][0]==key_b
print('RFP_CORRUPT_ORIGINAL_REDOWNLOAD_PRIORITY=PASS')
