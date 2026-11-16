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
print('RFP_CORRUPT_ORIGINAL_REDOWNLOAD_PRIORITY=PASS')
