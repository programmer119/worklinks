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

# Temporary read-only diagnostic for 2026-11-12 through 2026-11-18.
# GitHub Actions executes this on the diagnostic PR branch only.
import collections as _col, datetime as _dt, json as _json, time as _time, urllib.request as _request
_root='https://api-suaveforge.suaveforge.com:18458/api/g2b'
_offset=0;_total=None;_page=125;_saved=[];_failed=False
while _offset<100000:
    _ok=False
    for _size in dict.fromkeys([_page,60,25]):
        try:
            with _request.urlopen(_root+'/saved?sw=1&limit='+str(_size)+'&offset='+str(_offset),timeout=18) as _resp:
                _obj=_json.load(_resp)
            if not _obj.get('ok') or not _obj.get('persisted') or not isinstance(_obj.get('items'),list):raise ValueError('bad saved DB response')
            if _total is not None and int(_obj['totalCount'])!=_total:raise ValueError('DB changed during fetch')
            _total=int(_obj['totalCount']);_items=_obj['items']
            if not _items and _offset<_total:raise ValueError('short page')
            _saved.extend(_items);_offset+=len(_items);_page=_size;_ok=True
            break
        except Exception as _exc:
            print('SW_DIAG_RETRY',_offset,_size,str(_exc)[:200],flush=True)
            _time.sleep(0.4)
    if not _ok:
        _failed=True
        break
    if _offset>=_total:break
print('SW_DIAG_FETCH',_offset,_total,'failed',_failed,flush=True)
print('SW_DIAG_SAMPLES',_json.dumps([{k:x.get(k) for k in ('bidNo','order','posted','kind')} for x in _saved[:5]],ensure_ascii=False),flush=True)
_counter=_col.Counter();_revisions=_col.Counter();_seen=set();_invalid=0
for _x in _saved:
    _bid=str(_x.get('bidNo') or '')
    _ord=str(_x.get('order') if _x.get('order') is not None else '')
    _date=str(_x.get('posted') or '')[:10].replace('.','-').replace('/','-')
    try: _day=_dt.date.fromisoformat(_date)
    except ValueError: _invalid+=1;continue
    _key=(str(_x.get('kind') or ''),_bid,_ord)
    if _key in _seen:continue
    _seen.add(_key)
    if _dt.date(2026,11,12)<=_day<=_dt.date(2026,11,18):
        if _ord.isdigit() and int(_ord)==0:_counter[_date]+=1
        else:_revisions[_date]+=1
for _i in range(7):
    _d=(_dt.date(2026,11,12)+_dt.timedelta(days=_i)).isoformat()
    print('SW_DIAG_DAY',_d,'NEW',_counter[_d],'UPDATES',_revisions[_d],flush=True)
print('SW_DIAG_TOTAL','NEW',sum(_counter.values()),'UPDATES',sum(_revisions.values()),'INVALID',_invalid,'FETCHED',len(_saved),flush=True)
if _failed:raise RuntimeError('cannot verify SW daily count: saved DB connection failed')
