#!/usr/bin/env python3
"""Backfill official G2B license restrictions for EVERY indexed SW candidate.

This worker collects facts only. It never marks candidates unsuitable, edits
the original notices, or interprets missing evidence as a disqualification.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

DB=os.environ.get('G2B_DB_PATH','/app/data/bids.sqlite3')
API=os.environ.get('G2B_LOCAL_API','http://127.0.0.1:18192/api/g2b')
POLL=max(60,int(os.environ.get('G2B_QUAL_POLL','180')))
BATCH=max(20,min(350,int(os.environ.get('G2B_QUAL_BATCH','200'))))
TTL=dt.timedelta(days=7)
EXTRA_POLL=max(1800,int(os.environ.get('G2B_EXTRA_POLL','1800')))
EXTRA_SUCCESS_TTL=dt.timedelta(hours=72)
EXTRA_PARTIAL_TTL=dt.timedelta(hours=6)

def now():
 return dt.datetime.now(dt.timezone.utc)

def log(*args):
 print(now().isoformat(),*args,flush=True)

def datepart(value):
 text=str(value or '')
 m=re.search(r'(20\d{2})[-./]?(\d{1,2})[-./]?(\d{1,2})',text)
 if not m:return None
 try:return dt.date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
 except ValueError:return None

def checked_and_complete(raw,checked_at,cutoff):
 """A partial official API response is never a completed screening."""
 if not raw or not checked_at:return False
 try:
  stamp=dt.datetime.fromisoformat(str(checked_at).replace('Z','+00:00'))
  result=json.loads(raw)
  return (stamp.tzinfo is not None and stamp>=cutoff
   and result.get('ok') is True and result.get('complete') is True)
 except (TypeError,ValueError,AttributeError):
  return False

def targets(conn,retry_after=None,at_monotonic=None):
 """Read ALL SW-indexed notices; no hidden LIMIT 4000, title gate, or ordinal mismatch.

 An indexed bid's title alone must never make it invisible to the official
 restrictions collector. The index is a *discovery* heuristic, not a decision.
 The lookup is data enrichment; ambiguous results never block bids.
 """
 cutoff=now()-TTL
 retry_after=retry_after or {}
 clock=time.monotonic() if at_monotonic is None else at_monotonic
 rows=conn.execute("""
  SELECT b.kind,b.bid_no,b.bid_ord,b.payload,q.payload,q.checked_at
  FROM bid_notices b
  LEFT JOIN bid_license_cache q ON q.bid_no=b.bid_no
   AND q.bid_ord=printf('%03d',CAST(b.bid_ord AS INTEGER))
  WHERE b.sw_candidate=1
  ORDER BY b.last_seen DESC,b.bid_no DESC
 """).fetchall()
 today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
 ranked=[]
 seen=set()
 for kind,no,order,payload,qualified,checked_at in rows:
  order=str(order or '').strip()
  if not re.fullmatch(r'\d{1,3}',order):continue
  canonical=order.zfill(3)
  key=(str(no),canonical)
  if key in seen:continue
  seen.add(key)
  if checked_and_complete(qualified,checked_at,cutoff):continue
  if retry_after.get(key,0)>clock:continue
  try:meta=json.loads(payload)
  except (ValueError,TypeError):meta={}
  expires=datepart(meta.get('closes'))
  active=expires is None or expires>=today
  days=max(0,(expires-today).days) if expires and active else 99999
  # Unchecked/open notices first, then stale; never spend quota on already
  # cached complete results until their seven-day refresh is due.
  rank=(0 if active else 1,0 if qualified is None else 1,days,
        str(no),canonical)
  ranked.append((rank,kind,str(no),canonical))
 ranked.sort(key=lambda x:x[0])
 return [(kind,no,ordn) for _,kind,no,ordn in ranked[:BATCH]]

def extra_target(conn):
 """Choose one open software-service notice, never scan upstream on UI reload.

 At most one notice per EXTRA_POLL interval, three optional official operations
 per notice. An absent/failed response is pending, not 'no restrictions'.
 """
 conn.execute('CREATE TABLE IF NOT EXISTS bid_extra_cache(bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,payload TEXT NOT NULL,checked_at TEXT NOT NULL,PRIMARY KEY(bid_no,bid_ord))')
 rows=conn.execute("""
  SELECT b.bid_no,b.bid_ord,b.payload,e.payload,e.checked_at
  FROM bid_notices b LEFT JOIN bid_extra_cache e
   ON b.bid_no=e.bid_no AND e.bid_ord=printf('%03d',CAST(b.bid_ord AS INTEGER))
  WHERE b.sw_candidate=1 AND b.kind='servc'
  ORDER BY b.last_seen DESC,b.bid_no DESC
 """).fetchall()
 seen=set()
 candidates=[]
 today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
 for no,order,payload,cached,checked_at in rows:
  try: canonical=str(order or '').zfill(3)
  except (ValueError,TypeError):continue
  if not re.fullmatch(r'\d{3}',canonical) or (no,canonical) in seen:continue
  seen.add((no,canonical))
  try: info=json.loads(payload)
  except (TypeError,ValueError): info={}
  end=datepart(info.get('closes'))
  if end is not None and end<today:continue
  if checked_at:
   try:
    stamp=dt.datetime.fromisoformat(checked_at.replace('Z','+00:00'))
    data=json.loads(cached or '{}')
    limit=EXTRA_SUCCESS_TTL if data.get('complete') is True else EXTRA_PARTIAL_TTL
    if stamp.tzinfo is not None and now()-stamp<limit:continue
   except (ValueError,TypeError,AttributeError):pass
  remaining=(end-today).days if end is not None else 99999
  candidates.append(((remaining,0 if not checked_at else 1,no),no,canonical))
 if not candidates:return None
 candidates.sort(key=lambda x:x[0])
 return (candidates[0][1],candidates[0][2])

def fetch_extra(no,order):
 query=urllib.parse.urlencode({'bidNo':no,'order':order})
 req=urllib.request.Request(API+'/bid-extra?'+query,headers={'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=38) as response:
  data=json.loads(response.read().decode('utf8'))
 if str(data.get('bidNo') or '')!=no or str(data.get('order') or '')!=order:
  raise ValueError('supplemental_notice_identity_mismatch')
 return data

def verify(no,order):
 query=urllib.parse.urlencode({'bidNo':no,'order':order})
 req=urllib.request.Request(API+'/eligibility?'+query,headers={'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=27) as response:
  data=json.loads(response.read().decode('utf8'))
 if not data.get('ok') or not data.get('complete'):
  raise ValueError('incomplete_eligibility')
 if str(data.get('bidNo') or '')!=no or str(data.get('order') or '').zfill(3)!=order:
  raise ValueError('upstream_bid_identity_mismatch')
 return data

def main():
 conn=sqlite3.connect(DB,timeout=30)
 conn.execute('PRAGMA busy_timeout=30000')
 conn.execute('PRAGMA journal_mode=WAL')
 conn.execute('CREATE TABLE IF NOT EXISTS bid_license_cache (bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,payload TEXT NOT NULL,checked_at TEXT NOT NULL,PRIMARY KEY(bid_no,bid_ord))')
 conn.commit()
 retry_after={}
 attempts={}
 last_extra=0
 while True:
  if time.monotonic()-last_extra>=EXTRA_POLL:
   last_extra=time.monotonic()
   try:
    target=extra_target(conn)
    if target:
     extra=fetch_extra(*target)
     log('BID_EXTRA_CACHE_REFRESH',target[0],target[1],
         'complete',bool(extra.get('complete')),
         'sources',len(extra.get('sources') or {}))
    else:log('BID_EXTRA_CACHE_UP_TO_DATE_OR_NO_OPEN_NOTICE')
   except Exception as error:
    log('BID_EXTRA_CACHE_RETRY_LATER',type(error).__name__)
  completed=0
  errors=0
  rate_limited=False
  try:
   queue=targets(conn,retry_after)
   if not queue:
    log('QUALIFICATIONS_QUEUE_EMPTY_OR_BACKOFF')
    time.sleep(POLL)
    continue
   log('QUALIFICATION_BATCH_START',len(queue),'cache_rows',
       conn.execute('SELECT COUNT(*) FROM bid_license_cache').fetchone()[0])
   for kind,no,order in queue:
    key=(no,order)
    try:
     verify(no,order)
     completed+=1
     retry_after.pop(key,None)
     attempts.pop(key,None)
     if completed%20==0:log('QUALIFICATION_PROGRESS',completed)
    except Exception as error:
     errors+=1
     failures=min(attempts.get(key,0)+1,8)
     attempts[key]=failures
     cooldown=min(1800,30*(2**(failures-1)))
     retry_after[key]=time.monotonic()+cooldown
     log('QUALIFICATION_RETRY_LATER',no,order,type(error).__name__,'backoff_s',cooldown)
     # A provider outage or quota limit is not a reason to hammer thousands
     # of other bids in the same failed batch.
     if (isinstance(error,urllib.error.HTTPError) and
         error.code in (403,429,500,502,503,504)) or (
         'upstream_temporarily_rate_limited' in str(error)):
      rate_limited=True
      log('QUALIFICATION_UPSTREAM_BACKOFF',type(error).__name__)
      break
    time.sleep(0.45)
   total=conn.execute('SELECT COUNT(*) FROM bid_license_cache').fetchone()[0]
   log('QUALIFICATION_BATCH_END','success',completed,'errors',errors,
       'total_cached',total,'source','official_G2B_license_limit')
   time.sleep(max(POLL,600) if rate_limited else (10 if completed else POLL))
  except Exception as error:
   log('QUALIFICATION_LOOP_ERROR',type(error).__name__)
   time.sleep(POLL)

if __name__=='__main__':
 main()
