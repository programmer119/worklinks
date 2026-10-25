#!/usr/bin/env python3
"""Protect default hourly RFP budget until approved G2B traffic is confirmed."""
import pathlib,re,runpy
root=pathlib.Path(__file__).resolve().parents[1]
workflow=(root/'.github/workflows/worklinks-rfp-snapshot.yml').read_text(encoding='utf-8')
m=re.search(r'python3 scripts/refresh_worklinks_rfp.py --limit (\\d+)',workflow)
assert m,'missing quota-bound scan invocation'
per_hour=int(m.group(1))
r=runpy.run_path(str(root/'scripts/refresh_worklinks_rfp.py'),run_name='test_quota')
probes=r['MAX_MANIFEST_PROBES_PER_RUN']
# Server bid_evidence_query makes three official requests per notice:
# getBidPblancListInfoPrtcptPsblRgn,
# getBidPblancListInfoEorderAtchFileInfo,
# getBidPblancListInfoServc (notice documents).
calls_per_notice=3
daily_budget=24*(per_hour+probes)*calls_per_notice
assert 0<per_hour<=8,(per_hour,daily_budget)
assert 0<=probes<=2,(probes,daily_budget)
assert daily_budget<=720,daily_budget
print('WORKLINKS_RFP_DEFAULT_QUOTA_BUDGET=PASS','hourly_new',per_hour,
      'hourly_manifest_probes',probes,'max_daily_calls',daily_budget)
