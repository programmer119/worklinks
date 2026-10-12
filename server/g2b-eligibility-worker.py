#!/usr/bin/env python3
# WorkLinks: persistent G2B bid qualification enrichment.
# Official restrictions are fetched through the server's existing authenticated API.
# On successful requests the API itself commits bid_license_cache to SQLite.
import datetime as dt
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request

DB=os.environ.get('G2B_DB_PATH','/app/data/bids.sqlite3')
API=os.environ.get('G2B_LOCAL_API','http://127.0.0.1:18192/api/g2b')
POLL=max(60,int(os.environ.get('G2B_QUAL_POLL','180')))
BATCH=max(20,min(350,int(os.environ.get('G2B_QUAL_BATCH','200'))))
HARD=re.compile(r'GPU|컴퓨터.?서버|고성능.?서버|워크스테이션|실험.?장비|센서|프린터|위성.?통신|CCTV|카메라|시공|통신.?공사|기자재|드론|3D.?프린팅',re.I)
SW=re.compile(r'개발|구축|고도화|유지.?보수|유지.?관리|기능.?개선|홈페이지|웹서비스|데이터|DB|소프트웨어|SW|인공지능|AI|클라우드|플랫폼|정보시스템',re.I)
def now():return dt.datetime.now(dt.timezone.utc)
def log(*args):print(now().isoformat(),*args,flush=True)
def should_check(r):
 kind,title=r.get('kind'),str(r.get('title') or '')
 if kind in ('cnstwk','frgcpt'):return False
 if kind=='thng':
  if HARD.search(title):return False
  return bool(re.search(r'소프트웨어|S\/W|SW|라이선스|솔루션',title,re.I))
 if HARD.search(title) and not re.search(r'데이터.?분석|데이터.?수집|소프트웨어.?개발|플랫폼.?개발',title,re.I):
  return False
 return bool(SW.search(title))
def datepart(s):
 s=str(s or '')
 m=re.search(r'20\d{2}[-./]\d{1,2}[-./]\d{1,2}',s)
 if not m:return None
 try:return dt.datetime.strptime(re.sub(r'[./]','-',m.group(0)),'%Y-%m-%d').date()
 except ValueError:return None
def targets(conn):
 cutoff=(now()-dt.timedelta(days=7)).isoformat()
 # The partial filter is on the archived SW candidate index. Source notices are never dropped.
 rows=conn.execute("""
  SELECT b.kind,b.bid_no,b.bid_ord,b.payload FROM bid_notices b
  LEFT JOIN bid_license_cache q ON q.bid_no=b.bid_no AND q.bid_ord=b.bid_ord
  WHERE b.sw_candidate=1 AND (q.bid_no IS NULL OR q.checked_at < ?)
  ORDER BY b.last_seen DESC LIMIT 4000
 """,(cutoff,)).fetchall()
 today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
 ranked=[]
 for kind,no,order,payload in rows:
  try:x=json.loads(payload)
  except (TypeError,ValueError):continue
  if not should_check(x):continue
  expires=datepart(x.get('closes'))
  is_active=expires is None or expires>=today
  rank=(0 if is_active else 1, (expires-today).days if expires and is_active else 100000,
    -int(str(x.get('posted') or '0')[:4] or 0))
  ranked.append((rank,kind,no,order))
 ranked.sort(key=lambda x:x[0])
 return [(kind,no,order) for _,kind,no,order in ranked[:BATCH]]
def verify(no,ord):
 query=urllib.parse.urlencode({'bidNo':no,'order':ord})
 req=urllib.request.Request(API+'/eligibility?'+query,headers={'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=27) as r:
  data=json.loads(r.read().decode('utf8'))
 if not data.get('ok') or not data.get('complete'):
  raise ValueError('incomplete_eligibility')
 return data
def main():
 conn=sqlite3.connect(DB,timeout=30)
 conn.execute('PRAGMA busy_timeout=30000')
 conn.execute('PRAGMA journal_mode=WAL')
 conn.execute('CREATE TABLE IF NOT EXISTS bid_license_cache (bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,payload TEXT NOT NULL,checked_at TEXT NOT NULL,PRIMARY KEY(bid_no,bid_ord))')
 conn.commit()
 while True:
  done=0;errors=0
  try:
   queue=targets(conn)
   if not queue:
    log('QUALIFICATIONS_UP_TO_DATE');time.sleep(POLL);continue
   log('QUALIFICATION_BATCH_START',len(queue))
   for kind,no,ord in queue:
    try:
     verify(no,ord)
     done+=1
     if done%20==0:log('QUALIFICATION_PROGRESS',done)
    except Exception as e:
     errors+=1
     log('QUALIFICATION_RETRY_LATER',no,type(e).__name__)
    time.sleep(0.45)
   total=conn.execute('SELECT COUNT(*) FROM bid_license_cache').fetchone()[0]
   log('QUALIFICATION_BATCH_END','success',done,'errors',errors,'total_cached',total)
   time.sleep(10 if done else POLL)
  except Exception as e:
   log('QUALIFICATION_LOOP_ERROR',type(e).__name__)
   time.sleep(POLL)
if __name__=='__main__':main()
