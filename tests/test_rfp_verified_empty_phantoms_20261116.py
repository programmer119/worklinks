#!/usr/bin/env python3
"""No-network verified empty-manifest scan exclusion regression."""
import sys,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rfp_dual_queue import RfpDualQueue

with tempfile.TemporaryDirectory() as root:
    q=RfpDualQueue(Path(root)/'state.sqlite3')
    good='R26BK99999811:001';bad='R26BK99999812:001'
    q.enqueue([(good.split(':')[0],'001','2099-12-31'),
               (bad.split(':')[0],'001','2099-12-31')],'reader-v1')
    empty={'attachments':{'ok':True,'complete':True,'items':[]},
           'noticeDocuments':{'ok':True,'complete':True}}
    with q.connect() as db:
        db.executemany("""INSERT INTO rfp_bulk_manifests(
            notice_key,metadata_json,sources,saved_at) VALUES(?,?,?,?)""",
            [(k,json.dumps(empty),'verified_official_three_source','2026-11-16T12:00:00Z')
              for k in (good,bad)])
    for key in (good,bad):
        assert q.claim_download()[0] in (good,bad)
        # Claiming order must be deterministic; check currently fetching key.
        with q.connect() as db:
            claimed=db.execute("SELECT notice_key FROM rfp_dual_notices WHERE download_status='fetching'").fetchone()[0]
        q.no_attachments(claimed,empty)
    with q.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM rfp_dual_notices WHERE scan_status='skipped'").fetchone()[0]==2
    q.enqueue([(good.split(':')[0],'001','2099-12-31'),
               (bad.split(':')[0],'001','2099-12-31')],'reader-v2')
    with q.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM rfp_dual_notices WHERE scan_status='skipped'").fetchone()[0]==2
        # Reproduce stale production state caused by an earlier reader rollout.
        db.execute("UPDATE rfp_dual_notices SET scan_status='pending' WHERE notice_key IN (?,?)",(good,bad))
        # One record has incomplete metadata: do NOT exclude that one.
        unsafe={'attachments':{'ok':True,'complete':False,'items':[]},
                'noticeDocuments':{'ok':True,'complete':True}}
        db.execute("UPDATE rfp_dual_notices SET metadata_json=? WHERE notice_key=?",
                   (json.dumps(unsafe),bad))
    assert q.restore_verified_empty_skips()==1
    with q.connect() as db:
        a=db.execute("SELECT download_status,scan_status FROM rfp_dual_notices WHERE notice_key=?",(good,)).fetchone()
        b=db.execute("SELECT download_status,scan_status FROM rfp_dual_notices WHERE notice_key=?",(bad,)).fetchone()
    assert a==('no_attachments','skipped'),a
    assert b==('no_attachments','pending'),b
    assert q.restore_verified_empty_skips()==0
    with q.connect() as db:
        db.execute("UPDATE rfp_dual_notices SET metadata_json=? WHERE notice_key=?",
                   (json.dumps(empty),bad))
    tally=q.reconcile_management({good:'2099-12-31',bad:'2099-12-31'},set(),'reader-v3')
    assert tally['verifiedEmptyRestored']==1,tally
    with q.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM rfp_dual_notices WHERE scan_status='skipped'").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM rfp_dual_notices WHERE scan_status='done'").fetchone()[0]==0
print('VERIFIED_EMPTY_MANIFEST_SKIP_PRESERVED_AND_OLD_PHANTOMS_REPAIRED=PASS')
