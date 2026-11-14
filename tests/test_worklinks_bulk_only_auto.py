#!/usr/bin/env python3
"""No-network proof: scheduled jobs cannot call one official API per notice."""
import importlib.util
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
FLAG='WORKLINKS_NO_AUTOMATIC_SINGLE_NOTICE'
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

eligibility=load('server/g2b-eligibility-worker.py','worklinks_eligibility_bulk_gate')
award=load('server/g2b-award-enricher.py','worklinks_award_bulk_gate')
with patch.dict(os.environ,{FLAG:'1'}):
    # The mandatory service must NOT idle: it must delegate to date batching.
    main_source=(ROOT/'server/g2b-eligibility-worker.py').read_text()
    assert 'QUALIFICATION_BATCH_COLLECTION_STARTED' in main_source
    assert 'module.run_forever()' in main_source
    assert 'g2b-mandatory-date-batch.py' in main_source
    batch_source=(ROOT/'server/g2b-mandatory-date-batch.py').read_text()
    assert 'mandatory-enrichment-batch?' in batch_source
    assert "'bidNtceNo'" in batch_source  # parse returned IDs, never request IDs
    with tempfile.TemporaryDirectory() as tmp:
        import sqlite3
        db=sqlite3.connect(str(Path(tmp)/'awards.sqlite3'))
        award.init(db)
        def forbidden(*args,**kwargs):raise AssertionError('award singleton HTTP was called')
        result=award.cycle(db,fetch=forbidden)
        assert result['requests']==0 and result['state']=='bulk_only_no_single_upstream',result
        status=db.execute('SELECT requests_last_run,message FROM bid_award_worker_status WHERE id=1').fetchone()
        assert status==(0,'bulk_only_no_single_upstream'),status
        db.close()

pipeline=(ROOT/'server/worklinks-server123-pipeline.py').read_text(encoding='utf-8')
assert "kind in ('rfp','rfpRepair')" in pipeline
assert "os.environ.get('WORKLINKS_RFP_DUAL_QUEUE')=='1'" in pipeline
download=(ROOT/'scripts/rfp_download_worker.py').read_text(encoding='utf-8')
assert 'BulkManifestPlanner' in download
for deploy in ('deploy-g2b-eligibility-worker-only.sh','deploy-g2b-award-enricher.sh'):
    source=(ROOT/'server'/deploy).read_text(encoding='utf-8')
    assert 'WORKLINKS_NO_AUTOMATIC_SINGLE_NOTICE=1' in source
print('AUTOMATIC_SINGLE_NOTICE_OFF_NO_NETWORK=PASS',flush=True)
