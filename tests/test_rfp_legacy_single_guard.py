#!/usr/bin/env python3
"""Explicit browser detail remains, but stale automatic RFP metadata is impossible."""
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
proxy=(ROOT/'server/g2b-proxy.py').read_text()
route=proxy.index("if u.path == '/api/g2b/bid-evidence':")
guard=proxy.index("startswith('WorkLinks-RFP-ReadOnly/')",route)
query=proxy.index('result=bid_evidence_query',route)
assert route<guard<query
pipeline=(ROOT/'server/worklinks-server123-pipeline.py').read_text()
assert "legacy_single_bid_metadata_job_disabled_in_dual_queue" in pipeline
assert "kind in ('rfp','rfpRepair')" in pipeline
spec=importlib.util.spec_from_file_location('rfp_legacy_guard',
                                            ROOT/'scripts/refresh_worklinks_rfp.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
with patch.dict(os.environ,{'WORKLINKS_RFP_DUAL_SCAN_ONLY':'1'}):
    with patch.object(mod,'fetch_json',side_effect=AssertionError('per-bid official HTTP')),\
         patch.object(mod,'download',side_effect=AssertionError('per-bid download')):
        result=mod.process('R26BK12345678','000',metadata=None)
        assert result['reasonCode']=='dual_queue_bulk_manifest_missing'
        assert result['reviewComplete'] is False
print('RFP_DUAL_QUEUE_LEGACY_SINGLE_REQUEST_GUARD=PASS',flush=True)
