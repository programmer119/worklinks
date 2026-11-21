#!/usr/bin/env python3
"""Zero-network checks: current day first, quota reserve, changed-only writes."""
import datetime as dt
import importlib.util
import pathlib
import sqlite3
import tempfile
import time
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prebid_priority',ROOT/'scripts/g2b_prebid_collector.py')
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
assert p.LIMIT_DAY==400,p.LIMIT_DAY
assert p.TODAY_RECHECK_SECONDS==3600
assert p.YESTERDAY_RECHECK_SECONDS==21600
assert p.BACKFILL_DAYS>=21
assert p.MIN_REQUEST_INTERVAL>=0.5
with tempfile.TemporaryDirectory() as td:
 p.DATA=pathlib.Path(td)/'data'/'g2b-prebid.sqlite3'
 p.KEY_PATH=pathlib.Path(td)/'key.env'
 p.KEY_PATH.write_text('G2B_STANDARD_SERVICE_KEY=UNIT_TEST_KEY\n',encoding='utf-8')
 db=p.connect()
 today=dt.datetime.now(p.KST).date()
 t=today.strftime('%Y%m%d')
 y=(today-dt.timedelta(days=1)).strftime('%Y%m%d')
 source={'orderPlanUntyNo':'R26DD12345678','bizNm':'실제 업무시스템 개발','orderInsttNm':'발주기관','nticeDt':t+'1015'}
 calls=[]
 def fetch(db,key,stage,kind,day,page):
  assert page==1
  calls.append((stage,kind,day))
  return 1,[source]
 # Newly discovered source row must be inserted once, then never rewritten if
 # identical even after the cadence clock expires.
 with mock.patch.object(p,'fetch_page',side_effect=fetch):
  first=p.collect_window(db,'TEST','plan','servc',t)
  assert 'new=1 changed=0 unchanged=0' in first,first
  original=db.execute("SELECT payload,first_seen,last_seen FROM prebid_records WHERE item_id='R26DD12345678'").fetchone()
  assert p.collect_window(db,'TEST','plan','servc',t)=='skipped'
  db.execute("UPDATE prebid_windows SET last_success=? WHERE stage='plan' AND kind='servc' AND day=?",(time.time()-3601,t))
  db.commit()
  unchanged=p.collect_window(db,'TEST','plan','servc',t)
  assert 'new=0 changed=0 unchanged=1' in unchanged,unchanged
  after=db.execute("SELECT payload,first_seen,last_seen FROM prebid_records WHERE item_id='R26DD12345678'").fetchone()
  assert original==after,(original,after)
  # Same notice ID, changed original title: update content, preserve first_seen.
  source['bizNm']='실제 업무시스템 개발 변경공고'
  db.execute("UPDATE prebid_windows SET last_success=? WHERE stage='plan' AND kind='servc' AND day=?",(time.time()-3601,t))
  db.commit()
  changed=p.collect_window(db,'TEST','plan','servc',t)
  assert 'new=0 changed=1 unchanged=0' in changed,changed
  now=db.execute("SELECT payload,first_seen FROM prebid_records WHERE item_id='R26DD12345678'").fetchone()
  assert '변경공고' in now[0] and now[1]==original[1]
 # Yesterday is refreshed six-hourly, not every 30 minutes.
 with mock.patch.object(p,'fetch_page',side_effect=fetch):
  old=p.collect_window(db,'TEST','plan','servc',y)
  assert old.startswith('ok:'),old
  assert p.collect_window(db,'TEST','plan','servc',y)=='skipped'
  db.execute("UPDATE prebid_windows SET last_success=? WHERE stage='plan' AND kind='servc' AND day=?",(time.time()-21601,y))
  db.commit()
  assert p.collect_window(db,'TEST','plan','servc',y).startswith('ok:')
 # Completed older windows remain immutable to the ordinary backfill.
 old_day=(today-dt.timedelta(days=3)).strftime('%Y%m%d')
 with mock.patch.object(p,'fetch_page',side_effect=fetch):
  assert p.collect_window(db,'TEST','plan','servc',old_day).startswith('ok:')
  assert p.collect_window(db,'TEST','plan','servc',old_day)=='skipped'
 # Today outranks yesterday regardless of previous success clocks.
 observed=[]
 def fake_collect(db,key,stage,kind,day):
  observed.append((stage,kind,day))
  return 'skipped'
 with mock.patch.object(p,'collect_window',side_effect=fake_collect),mock.patch.object(p,'run_backfill',return_value={}):
  p.run_once()
 assert len(observed)==8,observed
 assert [day for _,_,day in observed[:4]]==[t]*4,observed
 assert [day for _,_,day in observed[4:]]==[y]*4,observed
 # Once 25% has been set aside for the fresh queue, backfill cannot consume it.
 protected=p.LIMIT_DAY-max(24,p.LIMIT_DAY//4)-p.MAX_PAGES
 db.execute('INSERT INTO prebid_quota(day,calls) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET calls=excluded.calls',(t,protected))
 db.commit()
 with mock.patch.object(p,'collect_window',side_effect=AssertionError('backfill overran fresh reserve')):
  assert p.run_backfill(db,'TEST',today)=={}
 # The internal limiter is *enforced*, never silently over budget.
 db.execute('UPDATE prebid_quota SET calls=? WHERE day=?',(p.LIMIT_DAY,t))
 db.commit()
 try:p.reserve(db)
 except RuntimeError as error:
  assert str(error)=='prebid_daily_request_budget_exhausted'
 else:raise AssertionError('local quota not enforced')
 assert db.execute('SELECT calls FROM prebid_quota WHERE day=?',(t,)).fetchone()[0]==p.LIMIT_DAY
 db.close()
print('WORKLINKS_PREBID_PRIORITY_CHANGED_ONLY_QUOTA_PASS')
