#!/usr/bin/env python3
"""Check WorkLinks deployment split: source gate here; real deploy in SuaveForge org."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'.github/workflows/worklinks-g2b-api-deploy.yml').read_text()
deploy=(ROOT/'server/deploy-g2b-api-only.sh').read_text()
diagnostics=(ROOT/'.github/workflows/worklinks-g2b-public-diagnostics.yml').read_text()
assert 'name: WorkLinks G2B API source gate' in source
assert 'runs-on: ubuntu-latest' in source
assert 'runs-on: [self-hosted' not in source
assert 'suaveforge/monitor' in source
assert 'worklinks-g2b-api-org-deploy.yml' in source
assert 'workflow_dispatch:' in source
assert 'SERVER123_API_DEPLOY_CONTROLLER=suaveforge/monitor' in source
assert 'OBSOLETE_PERSONAL_DEPLOY_CANCEL=PASS' in source
assert '123-research-general-06' not in source
assert 'PORT=18192' in deploy
assert 'WORKLINKS_G2B_PUBLIC_ROUTES=PASS' in deploy
assert 'PUBLIC_G2B_ROUTE_NOT_DEPLOYED=' in deploy
assert 'trap rollback ERR' in deploy
assert 'python /app/test_contract_evidence.py' in deploy
assert 'python /app/test_bid_evidence.py' in deploy
assert 'python3 tests/test_worklinks_deploy_runner_policy.py' in diagnostics
print('WORKLINKS_DEPLOY_RUNNER_POLICY=PASS')
