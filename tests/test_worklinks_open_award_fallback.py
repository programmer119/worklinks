#!/usr/bin/env python3
"""No official API or network calls; verify award fallback is sourced from saved bids."""
import datetime as dt
import importlib.util
from pathlib import Path

source=Path(__file__).resolve().parents[1]/'scripts'/'refresh_worklinks_open_award_fallback.py'
spec=importlib.util.spec_from_file_location('open_award_fallback',source)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
t=dt.datetime(2026,11,11,12,0)
def notice(bid='R26BK01808709',close='2026-11-30 23:59',method='협상에 의한 계약'):
    return {'bidNo':bid,'order':'000','closes':close,'awardMethod':method,
            'contract':'제한경쟁','awardMethodCode':'낙010001','awardFloorRate':'87.745'}
def fake(offset):
    assert offset==0
    return {'ok':True,'persisted':True,'totalCount':100,
            'items':[notice(),notice(bid='R26BK01811111',close='2026-11-10 23:59'),
                     *[notice(bid='INVALID') for _ in range(98)]]}
data=m.collect(fake,now=t)
assert data['ok'] and data['totalSavedSw']==100
assert data['count']==1 and 'R26BK01808709:000' in data['byNotice']
assert data['byNotice']['R26BK01808709:000']['awardFloorRate']=='87.745'
def fail(offset):
    return {'ok':True,'persisted':False,'totalCount':999,'items':[notice()]}
try:m.collect(fail,now=t)
except ValueError:pass
else:raise AssertionError('accepted non-persisted data')
print('WORKLINKS_OPEN_AWARD_FALLBACK_SERVER123_ONLY=PASS')
