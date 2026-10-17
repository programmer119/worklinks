#!/usr/bin/env python3
"""Guard WorkLinks production G2B deployment runner policy from regression."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
workflow=(ROOT/'.github/workflows/worklinks-g2b-api-deploy.yml').read_text()
deploy=(ROOT/'server/deploy-g2b-api-only.sh').read_text()
diagnostic=(ROOT/'.github/workflows/worklinks-g2b-public-diagnostics.yml').read_text()
assert 'runs-on: [self-hosted, Linux, X64, server123, suaveforge-deploy, suaveforge-org]' in workflow
assert '[[ "$RUNNER_NAME" =~ ^123-suaveforge-org-0[123]$ ]]' in workflow
assert 'research-general' not in workflow.split('runs-on:',1)[1].split('timeout-minutes:',1)[0]
assert '123-research-general-06' not in workflow
assert 'cancel-in-progress: false' in workflow
assert 'workflow_dispatch:' in workflow
assert 'test -S /home/ggul-docker/run/docker.sock' in workflow
assert 'test -s /home/worklinks/g2b/data/bids.sqlite3' in workflow
assert 'PORT=18192' in deploy
assert 'WORKLINKS_G2B_PUBLIC_ROUTES=PASS' in deploy
assert 'PUBLIC_G2B_ROUTE_NOT_DEPLOYED=' in deploy
assert 'trap rollback ERR' in deploy
assert 'python /app/test_contract_evidence.py' in deploy
assert 'python /app/test_bid_evidence.py' in deploy
assert 'python3 tests/test_worklinks_deploy_runner_policy.py' in diagnostic
print('WORKLINKS_DEPLOY_RUNNER_POLICY=PASS')
