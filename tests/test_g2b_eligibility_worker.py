#!/usr/bin/env python3
"""No-network full-corpus G2B eligibility worker regression (5000+ records)."""
import datetime as dt
import json
import os
import pathlib
import runpy
import sqlite3
import tempfile
import time

root=pathlib.Path(__file__).resolve().parents[1]
mod=runpy.run_path(str(root/'server/g2b-eligibility-worker.py'),run_name='local_qa')
tz=dt.timezone(dt.timedelta(hours=9))
today=dt.datetime.now(tz).date()
assert mod['datepart'](today.strftime('%Y%m%d')+'1400')==today
assert mod['datepart'](today.strftime('%Y-%m-%d')+' 10:00')==today
assert mod['datepart']('not-a-date') is None
assert mod['datepart']('20261344') is None
assert not mod['checked_and_complete'](json.dumps({'ok':True,'complete':False}),
                                       dt.datetime.now(dt.timezone.utc).isoformat(),mod['now']()-mod['TTL'])

with tempfile.TemporaryDirectory(prefix='worklinks-eligibility-backfill-') as temp:
 con=sqlite3.connect(os.path.join(temp,'fixture.sqlite3'))
 con.executescript("""
  CREATE TABLE bid_notices(kind TEXT,bid_no TEXT,bid_ord TEXT,payload TEXT,last_seen TEXT,
   sw_candidate INTEGER,PRIMARY KEY(kind,bid_no,bid_ord));
  CREATE TABLE bid_license_cache(bid_no TEXT,bid_ord TEXT,payload TEXT,checked_at TEXT,
   PRIMARY KEY(bid_no,bid_ord));
 """)
 timestamp=mod['now']().isoformat()
 fresh=json.dumps({'ok':True,'complete':True,'requirements':[{'codes':['1468']}]})
 partial=json.dumps({'ok':True,'complete':False,'requirements':[]})
 far=(today+dt.timedelta(days=5)).strftime('%Y%m%d')+'1000'
 rows=[]
 cache=[]
 # Old 4,000-row SQL cap must not hide a valid unreviewed indexed bid.
 for idx in range(5200):
  no='R26BK'+str(idx).zfill(8)
  raw_order='0' if idx%2==0 else '000'
  source=json.dumps({'title':'GPU 서버 유지관리 또는 소프트웨어 관련 입찰',
                     'posted':today.strftime('%Y%m%d'),'closes':far})
  rows.append(('servc',no,raw_order,source,timestamp,1))
  if idx<5196:
   cache.append((no,'000',fresh,timestamp))
 # One recently incomplete cache is not a completed review.
 cache.append(('R26BK00005196','000',partial,timestamp))
 # A stale complete row requires revalidation without blocking the card.
 cache.append(('R26BK00005197','000',fresh,
               (mod['now']()-dt.timedelta(days=9)).isoformat()))
 rows.append(('servc','R26BK99999998','0','{}',timestamp,0)) # not in SW index
 con.executemany('INSERT INTO bid_notices VALUES (?,?,?,?,?,?)',rows)
 con.executemany('INSERT INTO bid_license_cache VALUES (?,?,?,?)',cache)
 con.commit()
 result=mod['targets'](con)
 ids={(no,order) for _,no,order in result}
 assert len(result)==4,result
 assert ids=={('R26BK00005196','000'),('R26BK00005197','000'),
             ('R26BK00005198','000'),('R26BK00005199','000')},ids
 assert len(ids)==len(result),'the same bid and normalized order must be fetched only once'
 assert ('R26BK00000000','000') not in ids,'0/000 cached notice must not loop forever'
 # When one upstream lookup fails, back off only that bid; later work advances.
 omitted=('R26BK00005198','000')
 remaining=mod['targets'](con,{omitted:time.monotonic()+300})
 assert len(remaining)==3
 assert omitted not in {(no,order) for _,no,order in remaining}
 # Source index is the discovery scope; a GPU title cannot silently erase
 # an officially indexed candidate from qualification enrichment.
 assert ('R26BK00005199','000') in ids
 # Compare expiry: closed bids are backfilled *after* open bids.
 con.execute('INSERT INTO bid_notices VALUES(?,?,?,?,?,?)',
   ('servc','R26BK99999997','000',
    json.dumps({'closes':(today-dt.timedelta(days=2)).isoformat()}),timestamp,1))
 con.commit()
 next_batch=mod['targets'](con)
 assert next_batch[-1][1]=='R26BK99999997',next_batch
 print('WORKLINKS_WHOLE_CORPUS_LICENSE_BACKFILL=PASS',
       'indexed',len(rows)-1,'already_cached',len(cache),'remaining',len(result),
       'normalized_ordinals',True,'unbounded_scan',True,'retry_isolated',True)
