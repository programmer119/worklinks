#!/usr/bin/env python3
"""Isolated, quota-bounded WORKLINK prebid discovery: procurement plans + specs.

Official services:
  /1230000/ao/OrderPlanSttusService/getOrderPlanSttusList{Servc,Thng}
  /1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfo{Servc,Thng}
No existing bids/RFP DB modifications; no false electronic-bid deadline.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KST=dt.timezone(dt.timedelta(hours=9))
DATA=Path(os.environ.get('G2B_PREBID_DB','/app/data/g2b-prebid.sqlite3'))
KEY_PATH=Path(os.environ.get('G2B_OPERATING_KEY_PATH','/run/secrets/g2b-standard.env'))
SERVICE={
 ('plan','servc'):('https://apis.data.go.kr/1230000/ao/OrderPlanSttusService','getOrderPlanSttusListServc'),
 ('plan','thng'):('https://apis.data.go.kr/1230000/ao/OrderPlanSttusService','getOrderPlanSttusListThng'),
 ('prespec','servc'):('https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService','getPublicPrcureThngInfoServc'),
 ('prespec','thng'):('https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService','getPublicPrcureThngInfoThng'),
}
LIMIT_DAY=max(8,min(100,int(os.environ.get('WORKLINKS_PREBID_REQUESTS_PER_DAY','48'))))
MAX_PAGES=max(1,min(20,int(os.environ.get('WORKLINKS_PREBID_MAX_PAGES','8'))))
PAGE_SIZE=500
INTERVAL=max(1800,int(os.environ.get('WORKLINKS_PREBID_LOOP_SECONDS','1800')))
# Prevent silently missing notices published before this collector was installed.
BACKFILL_DAYS=max(2,min(30,int(os.environ.get('WORKLINKS_PREBID_BACKFILL_DAYS','14'))))
BACKFILL_PER_CYCLE=max(1,min(8,int(os.environ.get('WORKLINKS_PREBID_BACKFILL_PER_CYCLE','4'))))
SW_RE=re.compile(r'소프트웨어|정보시스템|전산|정보화|홈페이지|웹사이트|플랫폼|데이터베이스|인공지능|AI\b|\bSW\b|S/W|ICT|응용시스템|모바일\s*앱|시스템\s*(?:개발|고도화|구축)|디지털\s*전환',re.I)

def _first(row,*names):
 for name in names:
  value=row.get(name)
  if value is not None and str(value).strip():return str(value).strip()
 return ''

def official_url(s):
 try:
  u=urllib.parse.urlparse(str(s or ''))
  if u.scheme=='https' and (u.hostname=='g2b.go.kr' or u.hostname.endswith('.g2b.go.kr')):
   return u.geturl()
 except (TypeError,ValueError):pass
 return ''

def normalize(stage,kind,row):
 if not isinstance(row,dict):return None
 if stage=='plan':
  ident=_first(row,'orderPlanUntyNo','orderPlanSno','rcritRgstNo')
  title=_first(row,'bizNm','orderBizNm','orderPlanNm')
  org=_first(row,'orderInsttNm','totlmngInsttNm')
  posted=_first(row,'nticeDt','rgstDt')
  budget=_first(row,'sumOrderAmt','orderContrctAmt')
  orderyear=_first(row,'orderYear')
  ordermonth=_first(row,'orderMnth')
  planned_month=(orderyear+'-'+ordermonth.zfill(2) if orderyear and ordermonth else '')
  opinion=''
  files=[]
  url=official_url(_first(row,'orderPlanInfoUrl','orderPlanDtlUrl'))
 else:
  ident=_first(row,'bfSpecRgstNo')
  title=_first(row,'bizNm','bfSpecNm','prdctNm','prdctClsfcNoNm')
  org=_first(row,'orderInsttNm','rlDminsttNm')
  posted=_first(row,'rgstDt','rcptDt')
  budget=_first(row,'asignBdgtAmt')
  planned_month=''
  opinion=_first(row,'opninRgstClseDt')
  files=[safe for i in range(1,6)
    if (safe:=official_url(row.get('specDocFileUrl'+str(i))))]
  url=official_url(_first(row,'bfSpecInfoUrl','bfSpecRgstUrl','bfSpecDtlUrl'))
 if not ident or not title:return None
 # The official SW business flag is stronger than text, but does not establish
 # whether the procurement is *software development* rather than SW equipment.
 software_flag=_first(row,'swBizObjYn').upper()=='Y'
 subject=_first(row,'specCntnts','usgCntnts','dtilPrdctClsfcNoNm')
 product_name=_first(row,'prdctClsfcNoNm','dtilPrdctClsfcNoNm','prdctNm')
 product_code=_first(row,'dtilPrdctClsfcNo','prdctClsfcNo')
 sw=software_flag or bool(SW_RE.search(title+' '+subject+' '+product_name)) or product_code=='8111159901'
 # Keep every identified official record. SW relevance is now an optional
 # view filter, never a destructive collector-side selection.
 if stage=='plan':
  linked=_first(row,'bidNtceNoList')
 else:
  linked=_first(row,'bidNtceNoList')
 return {'id':ident[:80],'stage':stage,'kind':kind,'title':title[:350],
         'org':org[:160],'posted':posted[:30], 'budget':budget[:24],
         'plannedMonth':planned_month[:12], 'opinionDeadline':opinion[:30],
         'url':url,'files':files,'bidLinked':bool(linked),
         'swCandidate':bool(sw),
         'swFlagSource':'official' if software_flag else 'title' if sw else 'none',
         'subject':subject[:400], 'productName':product_name[:200],
         'productCode':product_code[:30]}

def connect():
 DATA.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(str(DATA),timeout=20)
 db.execute('PRAGMA busy_timeout=20000')
 db.execute('PRAGMA journal_mode=WAL')
 db.executescript("""
 CREATE TABLE IF NOT EXISTS prebid_records (
  stage TEXT NOT NULL,kind TEXT NOT NULL,item_id TEXT NOT NULL,
  payload TEXT NOT NULL,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
  PRIMARY KEY(stage,kind,item_id));
 CREATE INDEX IF NOT EXISTS prebid_by_stage_seen ON prebid_records(stage,last_seen);
 CREATE TABLE IF NOT EXISTS prebid_windows (
  stage TEXT NOT NULL,kind TEXT NOT NULL,day TEXT NOT NULL,
  last_success REAL NOT NULL DEFAULT 0,source_total INTEGER NOT NULL DEFAULT 0,
  stored INTEGER NOT NULL DEFAULT 0,failed TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(stage,kind,day));
 CREATE TABLE IF NOT EXISTS prebid_quota (
  day TEXT PRIMARY KEY,calls INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS prebid_meta (
  name TEXT PRIMARY KEY,value TEXT NOT NULL);
 """)
 # One-time additive migration. Revision 1 held only SW candidates; revision
 # 2 also retains non-SW. Successful old windows must be re-read once, within
 # the same existing 48-call daily cap, without deleting existing records.
 cols={row[1] for row in db.execute('PRAGMA table_info(prebid_windows)')}
 if 'scope_version' not in cols:
  db.execute('ALTER TABLE prebid_windows ADD COLUMN scope_version INTEGER NOT NULL DEFAULT 1')
  db.commit()
 return db

def key():
 # The bid/legacy key is NOT registered for these services. Use the same
 # operating G2B key proven live against both official endpoints.
 with KEY_PATH.open(encoding='utf-8') as fp:
  for line in fp:
   if line.startswith('G2B_STANDARD_SERVICE_KEY='):
    value=line.split('=',1)[1].strip()
    if value:return value
 raise RuntimeError('prebid_operating_key_not_available')

def reset_auth_gates_on_key_change(db,secret):
 # Never persist or print the key. A rotated key must immediately clear
 # the old key's permanent 403 hold; preserve valid snapshots and quota.
 fingerprint=hashlib.sha256(secret.encode('utf-8')).hexdigest()
 with db:
  old=db.execute("SELECT value FROM prebid_meta WHERE name='credential_sha256'").fetchone()
  if old is None or old[0]!=fingerprint:
   db.execute("""UPDATE prebid_windows SET failed=''
      WHERE failed LIKE 'prebid_official_http_40%'
         OR failed LIKE 'prebid_official_http_429'""")
   db.execute("""INSERT INTO prebid_meta(name,value) VALUES('credential_sha256',?)
      ON CONFLICT(name) DO UPDATE SET value=excluded.value""",(fingerprint,))


def reserve(db):
 today=dt.datetime.now(KST).strftime('%Y%m%d')
 db.execute('INSERT OR IGNORE INTO prebid_quota(day,calls) VALUES(?,0)',(today,))
 row=db.execute('SELECT calls FROM prebid_quota WHERE day=?',(today,)).fetchone()
 if row[0]>=LIMIT_DAY:raise RuntimeError('prebid_daily_request_budget_exhausted')
 db.execute('UPDATE prebid_quota SET calls=calls+1 WHERE day=?',(today,))
 db.commit()

def fetch_page(db,secret,stage,kind,day,page):
 base,operation=SERVICE[(stage,kind)]
 params={'serviceKey':secret,'type':'json','pageNo':str(page),
         'numOfRows':str(PAGE_SIZE),'inqryDiv':'1',
         'inqryBgnDt':day+'0000','inqryEndDt':day+'2359'}
 # Plans support both publication ranges and ordering-month search criteria.
 if stage=='plan':
  params.update(orderBgnYm=day[:6],orderEndYm=day[:6])
 reserve(db)
 url=base+'/'+operation+'?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'Accept':'application/json',
                                       'User-Agent':'WorkLinksPrebid/1.0'})
 try:
  with urllib.request.urlopen(req,timeout=28) as response:
   raw=response.read(15_000_000)
  data=json.loads(raw.decode('utf-8'))
  header=data.get('response',{}).get('header',{})
  if str(header.get('resultCode','?')) not in ('0','00'):
   raise RuntimeError('prebid_official_result_'+str(header.get('resultCode','unknown')))
  body=data.get('response',{}).get('body',{})
  total=int(body.get('totalCount') or 0)
  items=body.get('items') or []
  if isinstance(items,dict):items=items.get('item') or []
  if isinstance(items,dict):items=[items]
  if not isinstance(items,list) or (total>0 and not items):
   raise RuntimeError('prebid_official_page_incomplete')
  return total,items
 except urllib.error.HTTPError as exc:
  # Never log the signed URL or response body. HTTP status is enough to
  # distinguish authorization from a transient source outage.
  raise RuntimeError('prebid_official_http_'+str(exc.code)) from None
 except (urllib.error.URLError,ValueError,KeyError) as exc:
  # NEVER include URL or secret in logs or exceptions.
  raise RuntimeError('prebid_official_fetch_'+type(exc).__name__) from None

def collect_window(db,secret,stage,kind,day):
 now=time.time()
 prior=db.execute('SELECT last_success,failed,scope_version FROM prebid_windows WHERE stage=? AND kind=? AND day=?',
                  (stage,kind,day)).fetchone()
 # A missing permission is not a retryable parser error: never burn the
 # existing account quota every 30 minutes repeating a 401/403/429.
 today=dt.datetime.now(KST).strftime('%Y%m%d')
 blocked=db.execute("""SELECT failed FROM prebid_windows
  WHERE stage=? AND day>=? AND (failed LIKE 'prebid_official_http_40%'
   OR failed LIKE 'prebid_official_http_429')
  ORDER BY day DESC LIMIT 1""",(stage,today)).fetchone()
 if blocked:return 'blocked:'+str(blocked[0])
 retry_after=4*3600 if day==today else 24*3600
 if prior and int(prior[2] or 1)>=3 and now-float(prior[0] or 0)<retry_after:return 'skipped'
 gathered=[]
 try:
  total=None
  for page in range(1,MAX_PAGES+1):
   count,rows=fetch_page(db,secret,stage,kind,day,page)
   if total is None:total=count
   elif total!=count:raise RuntimeError('prebid_source_count_changed_mid_pagination')
   gathered.extend(rows)
   if len(gathered)>=total:break
   if page>=MAX_PAGES:raise RuntimeError('prebid_page_limit_incomplete')
  if total is None or len(gathered)<total:raise RuntimeError('prebid_pagination_incomplete')
  stamp=dt.datetime.now(KST).isoformat()
  values={}
  for raw in gathered:
   record=normalize(stage,kind,raw)
   if record is not None:values[record['id']]=record
  with db:
   for ident,record in values.items():
    db.execute("""INSERT INTO prebid_records
      (stage,kind,item_id,payload,first_seen,last_seen) VALUES (?,?,?,?,?,?)
      ON CONFLICT(stage,kind,item_id) DO UPDATE
       SET payload=excluded.payload,last_seen=excluded.last_seen""",
       (stage,kind,ident,json.dumps(record,ensure_ascii=False),stamp,stamp))
   db.execute("""INSERT INTO prebid_windows(stage,kind,day,last_success,source_total,stored,failed,scope_version)
      VALUES (?,?,?,?,?,?,'',3)
      ON CONFLICT(stage,kind,day) DO UPDATE SET
       last_success=excluded.last_success,source_total=excluded.source_total,
       stored=excluded.stored,failed='',scope_version=3""",
       (stage,kind,day,now,total,len(values)))
  return 'ok:'+str(total)+'/'+str(len(values))
 except (RuntimeError,sqlite3.Error) as exc:
  message=str(exc)[:100]
  with db:
   db.execute("""INSERT INTO prebid_windows(stage,kind,day,last_success,failed)
       VALUES (?,?,?,0,?)
       ON CONFLICT(stage,kind,day) DO UPDATE SET failed=excluded.failed""",
       (stage,kind,day,message))
  return 'failed:'+message

def run_backfill(db,secret,today):
 """Backfill unseen historic publishing windows without changing daily quota."""
 floor=today-dt.timedelta(days=BACKFILL_DAYS)
 windows=[]
 # Previously identified real missing SW prespec, published 2026-11-16.
 special=dt.date(2026,11,16)
 if floor<=special<=today-dt.timedelta(days=2):
  if not db.execute("SELECT 1 FROM prebid_records WHERE stage='prespec' AND kind='servc' AND item_id=?",
                    ('R26BD00301029',)).fetchone():
   windows.append(('prespec','servc',special.strftime('%Y%m%d')))
 for offset in range(2,BACKFILL_DAYS+1):
  day=(today-dt.timedelta(days=offset)).strftime('%Y%m%d')
  for stage,kind in SERVICE:
   record=(stage,kind,day)
   if record not in windows:windows.append(record)
 results={};attempted=0
 todaystr=today.strftime('%Y%m%d')
 for stage,kind,day in windows:
  quota=db.execute('SELECT calls FROM prebid_quota WHERE day=?',(todaystr,)).fetchone()
  if quota and quota[0]>=LIMIT_DAY-8:break
  prior=db.execute('SELECT last_success,scope_version FROM prebid_windows WHERE stage=? AND kind=? AND day=?',
                   (stage,kind,day)).fetchone()
  if prior and float(prior[0] or 0)>0 and int(prior[1] or 1)>=3:continue
  result=collect_window(db,secret,stage,kind,day)
  results[stage+'/'+kind+'/'+day]=result
  attempted+=1
  if 'prebid_daily_request_budget_exhausted' in result:break
  if attempted>=BACKFILL_PER_CYCLE:break
 return results

def run_once():
 db=connect()
 try:
  token=key()
  reset_auth_gates_on_key_change(db,token)
  today=dt.datetime.now(KST).date()
  # Today + prior day only. Each stage/kind window has a durable success clock.
  results={}
  for day in (today-dt.timedelta(days=1),today):
   for stage,kind in SERVICE:
    result=collect_window(db,token,stage,kind,day.strftime('%Y%m%d'))
    results[stage+'/'+kind+'/'+day.isoformat()]=result
    if result=='failed:prebid_daily_request_budget_exhausted':break
   if any('prebid_daily_request_budget_exhausted' in x for x in results.values()):break
  results.update(run_backfill(db,token,today))
  summary={'at':dt.datetime.now(KST).isoformat(),'results':results}
  print('PREBID_COLLECTION '+json.dumps(summary,ensure_ascii=False),flush=True)
  return not any(v.startswith(('failed:','blocked:')) for v in results.values())
 finally:db.close()

def main():
 while True:
  try:run_once()
  except (OSError,sqlite3.Error,RuntimeError) as e:
   print('PREBID_COLLECTION_RETRY '+type(e).__name__+' '+str(e)[:100],flush=True)
  if os.environ.get('WORKLINKS_PREBID_ONCE')=='1':break
  time.sleep(INTERVAL)

if __name__=='__main__':main()
