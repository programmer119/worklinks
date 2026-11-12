#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkLinks G2B full-page nationwide crawler (Python 3 stdlib, server123).
Runs continuously: backfill most recent 14 days then recheck last 3 days hourly.
Source: Korea G2B procurement notice APIs (services, goods, construction, foreign).
All notices are stored; filtering to SW/DB/AI is a *separate* UI operation.
"""
import calendar
import datetime as dt
import json
import os
import random
import re
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import hashlib

_G2B_LEDGER=None
def shared_ledger():
    global _G2B_LEDGER
    if not os.environ.get('WORKLINKS_RFP_LEDGER_DB'):return None
    if _G2B_LEDGER is None:
        from rfp_call_ledger import CallLedger
        _G2B_LEDGER=CallLedger(os.environ['WORKLINKS_RFP_LEDGER_DB'])
    return _G2B_LEDGER

DB_PATH=os.environ.get('G2B_DB_PATH','/app/data/bids.sqlite3')
KEY_FILE=os.environ.get('G2B_SECRET_PATH','/run/secrets/g2b.env')
API_ROOT='https://apis.data.go.kr/1230000/ad/BidPublicInfoService02'
OPERATIONS={
 'servc':'getBidPblancListInfoServcPPSSrch02',
 'thng':'getBidPblancListInfoThngPPSSrch02',
 'cnstwk':'getBidPblancListInfoCnstwkPPSSrch02',
 'frgcpt':'getBidPblancListInfoFrgcptPPSSrch02'
}
BACKFILL_DAYS=max(7,min(30,int(os.environ.get('G2B_BACKFILL_DAYS','14'))))
REFRESH_DAYS=max(2,min(7,int(os.environ.get('G2B_REFRESH_DAYS','3'))))
INTERVAL=max(900,int(os.environ.get('G2B_INTERVAL_SECONDS','3600')))
ROWS=999
PER_REQUEST_DELAY=0.22
SHUTDOWN=False

def log(*args):
    print(dt.datetime.now(dt.timezone.utc).isoformat(),*args,flush=True)

def shutdown(*_):
    global SHUTDOWN
    SHUTDOWN=True
signal.signal(signal.SIGTERM,shutdown)
signal.signal(signal.SIGINT,shutdown)

def secret():
    value=os.environ.get('G2B_SERVICE_KEY','').strip()
    if value:return value
    with open(KEY_FILE,encoding='utf-8') as f:
        for line in f:
            if line.startswith('G2B_SERVICE_KEY='):
                return line.split('=',1)[1].strip()
    raise RuntimeError('g2b_api_key_missing')

def connect():
    folder=os.path.dirname(DB_PATH)
    os.makedirs(folder,exist_ok=True)
    db=sqlite3.connect(DB_PATH,timeout=30)
    db.execute('PRAGMA busy_timeout=30000')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS bid_notices (kind TEXT NOT NULL,bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,payload TEXT NOT NULL,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,PRIMARY KEY(kind,bid_no,bid_ord))')
    db.execute('CREATE INDEX IF NOT EXISTS bid_notices_seen_idx ON bid_notices(last_seen DESC)')
    cols=[r[1] for r in db.execute('PRAGMA table_info(bid_notices)').fetchall()]
    if 'sw_candidate' not in cols:
        db.execute('ALTER TABLE bid_notices ADD COLUMN sw_candidate INTEGER NOT NULL DEFAULT 0')
        with db:
            for kind,no,order,payload in db.execute('SELECT kind,bid_no,bid_ord,payload FROM bid_notices').fetchall():
                try: flag=is_sw(json.loads(payload))
                except Exception: flag=0
                db.execute('UPDATE bid_notices SET sw_candidate=? WHERE kind=? AND bid_no=? AND bid_ord=?',(flag,kind,no,order))
    # A change marker is advanced only when the original notice payload changes,
    # never merely because the same notice was polled again.
    if 'changed_at' not in [r[1] for r in db.execute('PRAGMA table_info(bid_notices)').fetchall()]:
        db.execute("ALTER TABLE bid_notices ADD COLUMN changed_at TEXT NOT NULL DEFAULT ''")
    db.execute('CREATE INDEX IF NOT EXISTS bid_notices_sw_seen_idx ON bid_notices(sw_candidate,last_seen DESC)')
    db.execute('CREATE TABLE IF NOT EXISTS crawl_windows (kind TEXT NOT NULL,day TEXT NOT NULL,expected INTEGER NOT NULL,received INTEGER NOT NULL,pages INTEGER NOT NULL,checked_at TEXT NOT NULL,PRIMARY KEY(kind,day))')
    db.execute('CREATE TABLE IF NOT EXISTS crawl_status (id INTEGER PRIMARY KEY CHECK(id=1),state TEXT NOT NULL,run_started TEXT,run_finished TEXT,last_success TEXT,request_count INTEGER NOT NULL DEFAULT 0,error_count INTEGER NOT NULL DEFAULT 0,message TEXT)')
    db.execute("INSERT OR IGNORE INTO crawl_status (id,state,request_count,error_count) VALUES(1,'pending',0,0)")
    db.commit()
    return db

def ts():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def state(db,value,message='',finished=False,success=False):
    moment=ts()
    db.execute('UPDATE crawl_status SET state=?,message=?,run_finished=CASE WHEN ? THEN ? ELSE run_finished END,last_success=CASE WHEN ? THEN ? ELSE last_success END WHERE id=1',(value,message,int(finished),moment,int(success),moment))
    db.commit()

def call(key,kind,day,page):
    params={'serviceKey':key,'type':'json','pageNo':page,'numOfRows':ROWS,'inqryDiv':1,
            'inqryBgnDt':day+'0000','inqryEndDt':day+'2359'}
    url=API_ROOT+'/'+OPERATIONS[kind]+'?'+urllib.parse.urlencode(params)
    ledger=shared_ledger()
    request_key=None
    if ledger is not None:
        from rfp_call_ledger import cache_key
        request_key=cache_key('crawler_v1',kind,day,page,ROWS)
        max_age=(3600 if day==dt.datetime.now(
            dt.timezone(dt.timedelta(hours=9))).strftime('%Y%m%d') else 24*3600)
        cached=ledger.get_json(request_key,max_age_seconds=max_age)
        if (isinstance(cached,dict) and isinstance(cached.get('total'),int)
                and isinstance(cached.get('items'),list)):
            ledger.record('crawler',request_key,'verified_page_reused',
                          detail=kind+':'+day+':'+str(page))
            return cached['total'],cached['items']
    last=None
    for attempt in range(1,5):
        if SHUTDOWN:raise RuntimeError('stopping')
        try:
            req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'WorkLinksCollector/1.0'})
            with urllib.request.urlopen(req,timeout=24) as response:
                status=getattr(response,'status',200)
                raw=response.read()
                doc=json.loads(raw.decode('utf-8'))
            header=doc.get('response',{}).get('header',{})
            if str(header.get('resultCode','?')) not in ('0','00'):
                raise ValueError('G2B_result_'+str(header.get('resultCode','unknown')))
            body=doc.get('response',{}).get('body',{})
            items=body.get('items') or []
            if isinstance(items,dict):items=items.get('item') or []
            if not isinstance(items,list):items=[items]
            total=int(body.get('totalCount') or 0)
            if ledger is not None:
                ledger.record('crawler_http',request_key,'http_ok',http_status=status,
                              response_sha256=hashlib.sha256(raw).hexdigest(),
                              detail=kind+':'+day+':'+str(page))
                ledger.save_json(request_key,{'total':total,'items':items},
                                 max_bytes=20_000_000)
            return total,items
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,KeyError,OSError) as e:
            if ledger is not None:
                ledger.record('crawler_http',request_key,'http_failed',
                              http_status=getattr(e,'code',None),
                              error_class=type(e).__name__,
                              detail=kind+':'+day+':'+str(page))
            # Never include URL: it contains the service key.
            if isinstance(e,urllib.error.HTTPError) and e.code == 429:
                # Quota exhaustion: no retries, and no further date/kind requests this cycle.
                raise RuntimeError('g2b_rate_limited_429') from None
            last=type(e).__name__+((':'+str(getattr(e,'code',''))) if isinstance(e,urllib.error.HTTPError) else '')
            if attempt<4:time.sleep(min(8,attempt*1.7)+random.random())
    raise RuntimeError('upstream_error_'+str(last))

# Broad, title/subject-based preliminary relevance. Archive ALL bid notices either way.
SW_TERMS=re.compile(r'(소프트웨어|정보.?시스템|통합.?시스템|시스템|인공지능|머신러닝|딥러닝|기계학습|LLM|RAG|AI|ICT|IT서비스|빅데이터|데이터|데이타|디비|DB|정보화|디지털|전자문서|전자세금계산서|플랫폼|웹사이트|홈페이지|웹서비스|웹페이지|클라우드|서버|네트워크|인터넷|앱개발|모바일앱|애플리케이션|어플리케이션|SW|S/W|CCTV|보안솔루션|정보보호|사이버보안|API|GIS|ERP|CRM|RPA|메타버스|VR|AR|블록체인|영상인식|OCR|디지털콘텐츠)',re.I)
SW_BOUNDARY=re.compile(r'\b(IT|AI|DB|SW|API|ICT|ERP|CRM|RPA|LLM|RAG|GIS|OCR)\b',re.I)
def is_sw(bid):
    subject=bid.get('purchsObjPrdctList') or ''
    if isinstance(subject,(list,dict)):
        subject=json.dumps(subject,ensure_ascii=False)
    txt=str(bid.get('title') or '')+' '+str(subject)
    return int(bool(SW_TERMS.search(txt) or SW_BOUNDARY.search(txt)))

def compact(x,kind):
    def get(*names):
        for name in names:
            v=x.get(name)
            if v is not None and v!='':return v
        return ''
    return {'kind':kind,'bidNo':str(get('bidNtceNo')),'order':str(get('bidNtceOrd')),
      'title':get('bidNtceNm'),'org':get('ntceInsttNm','dminsttNm'),'agency':get('dminsttNm'),
      'posted':get('bidNtceDt'),'closes':get('bidClseDt'),'budget':get('asignBdgtAmt','presmptPrce'),
      'url':get('bidNtceDtlUrl'),'state':get('bidNtceSttusNm'),
      'contract':get('cntrctCnclsMthdNm'),
      'awardMethodCode':get('sucsfbidMthdCd'),'awardMethod':get('sucsfbidMthdNm'),
      'awardFloorRate':get('sucsfbidLwltRate'),'awardFieldsVerified':True,
      'purchsObjPrdctList':get('purchsObjPrdctList'),
      'category':kind}

def save(db,items):
    now=ts()
    values=[]
    for x in items:
        kind=x.get('kind','')
        no=x.get('bidNo','')
        if kind not in OPERATIONS or not no:continue
        values.append((kind,str(no),str(x.get('order','0')),json.dumps(x,ensure_ascii=False,separators=(',',':')),now,now))
    if not values:return 0
    with db:
        db.executemany('INSERT OR IGNORE INTO bid_notices (kind,bid_no,bid_ord,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?)',values)
        db.executemany('''UPDATE bid_notices
          SET changed_at=CASE WHEN payload<>? THEN ? ELSE changed_at END,
              payload=?,last_seen=?,sw_candidate=?
          WHERE kind=? AND bid_no=? AND bid_ord=?''',
          [(v[3],now,v[3],now,is_sw(json.loads(v[3])),v[0],v[1],v[2]) for v in values])
    return len(values)

def scan_day(db,key,kind,day):
    expected,first=call(key,kind,day,1)
    db.execute('UPDATE crawl_status SET request_count=request_count+1 WHERE id=1')
    received=save(db,[compact(x,kind) for x in first])
    if expected==0:
        pages=0
    else:
        if not first:
            raise RuntimeError('empty_first_page_while_total_nonzero')
        pages=(expected+ROWS-1)//ROWS
        if pages>1000:raise RuntimeError('daily_result_exceeds_1000_pages')
        for page in range(2,pages+1):
            if SHUTDOWN:raise RuntimeError('stopping')
            time.sleep(PER_REQUEST_DELAY)
            reported,items=call(key,kind,day,page)
            db.execute('UPDATE crawl_status SET request_count=request_count+1 WHERE id=1')
            if not items:raise RuntimeError('missing_page_'+str(page))
            received+=save(db,[compact(x,kind) for x in items])
            if reported>expected:expected=reported
    if received<expected:raise RuntimeError('incomplete_day_%d_of_%d'%(received,expected))
    with db:
        db.execute('INSERT OR REPLACE INTO crawl_windows(kind,day,expected,received,pages,checked_at) VALUES(?,?,?,?,?,?)',
                   (kind,day,expected,received,pages,ts()))
    log('WINDOW_OK',kind,day,'received',received,'reported',expected,'pages',pages)
    return received

def dates(count):
    kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    return [(kst-dt.timedelta(days=i)).strftime('%Y%m%d') for i in range(count-1,-1,-1)]

def window_due(db,kind,day,today,at=None):
    """Retry incomplete windows; do not re-fetch finalized historical days hourly.

    The current day stays fresh hourly; each of the previous REFRESH_DAYS-1
    days is checked once every 24 hours for retrospective corrections.
    Completed older backfill windows are immutable for this collector.
    """
    found=db.execute('SELECT checked_at FROM crawl_windows WHERE kind=? AND day=?',
                     (kind,day)).fetchone()
    if not found:return True
    if day < (today-dt.timedelta(days=REFRESH_DAYS-1)).strftime('%Y%m%d'):
        return False
    try:
        checked=dt.datetime.fromisoformat(str(found[0]).replace('Z','+00:00'))
        right_now=at or dt.datetime.now(dt.timezone.utc)
        interval=INTERVAL if day==today.strftime('%Y%m%d') else 24*3600
        return checked.tzinfo is None or (right_now-checked).total_seconds()>=interval
    except (ValueError,TypeError):
        return True


def scan(db,key,days,reason):
    state(db,'running',reason)
    db.execute('UPDATE crawl_status SET run_started=?,request_count=0,error_count=0 WHERE id=1',(ts(),))
    db.commit()
    errors=[]
    scanned=0
    due_windows=0
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    for day in dates(days):
        for kind in OPERATIONS:
            if not window_due(db,kind,day,today):continue
            due_windows+=1
            if SHUTDOWN:
                state(db,'stopping','received_signal',finished=True)
                return False
            try:
                scanned+=scan_day(db,key,kind,day)
            except Exception as e:
                err=kind+':'+day+':'+str(e)[:100]
                errors.append(err)
                db.execute('UPDATE crawl_status SET error_count=error_count+1 WHERE id=1')
                db.commit()
                log('WINDOW_FAILED',err)
                if 'g2b_rate_limited_429' in str(e):
                    state(db,'partial','g2b_rate_limited_429;paused_until_next_cycle',finished=True)
                    log('QUOTA_STOPPED_FURTHER_REQUESTS')
                    return False
            time.sleep(PER_REQUEST_DELAY)
    total=db.execute('SELECT COUNT(*) FROM bid_notices').fetchone()[0]
    message='reason=%s;windows=%d;received=%d;unique_total=%d;errors=%d'%(reason,due_windows,scanned,total,len(errors))
    if errors:
        state(db,'partial',message+';first='+errors[0],finished=True)
        return False
    state(db,'completed',message,finished=True,success=True)
    log('RUN_COMPLETE',message)
    return True

def main():
    key=secret()
    db=connect()
    try:
        # First launch or incomplete initial backfill: repeat until all windows pass.
        while not SHUTDOWN:
            start=dt.datetime.now(dt.timezone.utc)
            windows=db.execute('SELECT COUNT(*) FROM crawl_windows').fetchone()[0]
            # All historical windows remain visible: a failed one is retried,
            # while every already completed window is skipped until due.
            success=scan(db,key,BACKFILL_DAYS,
                         'initial_backfill' if windows<4*BACKFILL_DAYS else 'incremental_refresh')
            if not success:log('RETRY_ON_NEXT_CYCLE')
            remaining=INTERVAL-(dt.datetime.now(dt.timezone.utc)-start).total_seconds()
            # Never spin after long runs; wait at least 90 seconds.
            pause=max(90,int(remaining))
            log('NEXT_SCAN_IN_SECONDS',pause)
            for _ in range(pause):
                if SHUTDOWN:break
                time.sleep(1)
    finally:db.close()

if __name__=='__main__':
    try:main()
    except Exception as e:
        log('COLLECTOR_FATAL',type(e).__name__,str(e)[:180])
        sys.exit(1)
