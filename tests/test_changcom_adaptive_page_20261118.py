#!/usr/bin/env python3
"""Local /saved oversized response must not permanently freeze Changcom feed."""
import importlib.util,pathlib
from urllib.parse import parse_qs
root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('actionable',root/'scripts/refresh_worklinks_actionable.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rows=[{'bidNo':'R26BK'+str(i).zfill(8),'title':'문서 '+str(i)} for i in range(1377)]
tried=[]
def oversized(path):
    args=parse_qs(path.split('?',1)[1])
    offset=int(args['offset'][0]); limit=int(args['limit'][0])
    tried.append((offset,limit))
    # Simulate growing attachment evidence: some later offsets fit only 60.
    ceiling=60 if offset>=1000 else 125
    if limit>ceiling:raise ValueError('public_g2b_page_too_large')
    return {'ok':True,'totalCount':len(rows),'items':rows[offset:offset+limit]}
actual,n=mod.all_indexed(oversized)
assert n==len(rows) and actual==rows
assert (0,500) in tried and (0,250) in tried and (0,125) in tried
assert any(size<=60 for off,size in tried if off>=1000)
assert len(set(x['bidNo'] for x in actual))==len(actual)
def malformed(path):
    if path.endswith('limit=500&offset=0'):raise ValueError('network_down')
    raise AssertionError('should not retry non-size errors')
try:mod.all_indexed(malformed)
except ValueError as e:assert str(e)=='network_down'
else:raise AssertionError('failed call silently published result')
def unbounded(path):
    raise ValueError('public_g2b_page_too_large')
try:mod.all_indexed(unbounded)
except ValueError as e:assert str(e)=='public_g2b_page_too_large'
else:raise AssertionError('single invalid record was accepted')
print('WORKLINKS_CHANGCOM_ADAPTIVE_LOCAL_PAGE_COMPLETE=PASS')
