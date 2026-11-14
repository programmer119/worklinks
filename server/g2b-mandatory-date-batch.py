#!/usr/bin/env python3
"""Durable period-batched collection of required A02 qualification evidence.

Every official request covers an entire posted DATE, never a bid number.
Only positive exact-notice evidence is linked; missing rows stay UNKNOWN.
A verified source page is reused on restart and failures cannot mark a window done.
"""
import datetime as dt
import json
import math
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import defaultdict

DATA=os.environ.get('G2B_DB_PATH','/app/data/bids.sqlite3')
LOCAL=os.environ.get('G2B_LOCAL_API','http://127.0.0.1:18192/api/g2b')
SOURCES=('license','serviceProducts','mandatoryJointRegion','regionalIncentives')
ROWS=999
MAX_PAGES=500
MAX_CALLS_PER_RUN=18
DAILY_CALL_BUDGET=120
HOURLY_CALL_BUDGET=24
KST=dt.timezone(dt.timedelta(hours=9))

def now():
    return dt.datetime.now(dt.timezone.utc)

def stamp():
    return now().isoformat(timespec='seconds')

def connect(path=DATA):
    db=sqlite3.connect(path,timeout=30)
    db.execute('PRAGMA busy_timeout=30000')
    db.execute('''CREATE TABLE IF NOT EXISTS mandatory_batch_pages(
       source TEXT NOT NULL,day TEXT NOT NULL,page INTEGER NOT NULL,
       total INTEGER NOT NULL,rows INTEGER NOT NULL,payload TEXT NOT NULL,
       fetched_at TEXT NOT NULL,PRIMARY KEY(source,day,page))''')
    db.execute('''CREATE TABLE IF NOT EXISTS mandatory_batch_windows(
       source TEXT NOT NULL,day TEXT NOT NULL,verified_at TEXT NOT NULL,
       total INTEGER NOT NULL,pages INTEGER NOT NULL,
       PRIMARY KEY(source,day))''')
    db.execute('''CREATE TABLE IF NOT EXISTS mandatory_batch_budget(
       id INTEGER PRIMARY KEY AUTOINCREMENT,requested_at TEXT NOT NULL,
       source TEXT NOT NULL,day TEXT NOT NULL,page INTEGER NOT NULL)''')
    db.commit()
    return db

def parse_day(raw):
    m=re.match(r'^\s*(20\d\d)[-/.]?(\d\d)[-/.]?(\d\d)',str(raw or ''))
    if not m:return None
    try:return dt.date(*map(int,m.groups()))
    except ValueError:return None

def grouped_open_notices(db, at=None):
    today=at or dt.datetime.now(KST).date()
    dates=defaultdict(set)
    for no,ordn,payload in db.execute(
            "SELECT bid_no,bid_ord,payload FROM bid_notices WHERE kind='servc' AND sw_candidate=1"):
        try:record=json.loads(payload or '{}')
        except (TypeError,ValueError):continue
        posted=parse_day(record.get('posted'))
        closes=parse_day(record.get('closes'))
        if not posted or posted>today or (closes and closes<today):continue
        order=str(ordn or '000').zfill(3)
        if not re.fullmatch(r'\d{3}',order):continue
        if not re.fullmatch(r'[A-Za-z0-9-]{8,40}',str(no)):continue
        dates[posted.strftime('%Y%m%d')].add((str(no),order))
    return dates

def choose_day(db,groups):
    # Prefer current and most recently posted open notices. All historic days
    # are visited eventually; do not silently limit older open candidates.
    for day in sorted(groups,reverse=True):
        finished=db.execute("SELECT source,verified_at FROM mandatory_batch_windows WHERE day=?",
                            (day,)).fetchall()
        states={src:when for src,when in finished}
        if any(src not in states for src in SOURCES):return day
        # The current/recent posting day can acquire late amendments.
        recent=(dt.datetime.now(KST).date()-
                dt.datetime.strptime(day,'%Y%m%d').date()).days<=1
        if recent:
            if any((now()-dt.datetime.fromisoformat(states[src])).total_seconds()>43200
                   for src in SOURCES):return day
    return None

def reserve(db,source,day,page):
    moment=now()
    hour=(moment-dt.timedelta(hours=1)).isoformat()
    midnight=moment.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
    with db:
        h=db.execute("SELECT COUNT(*) FROM mandatory_batch_budget WHERE requested_at>=?",(hour,)).fetchone()[0]
        d=db.execute("SELECT COUNT(*) FROM mandatory_batch_budget WHERE requested_at>=?",(midnight,)).fetchone()[0]
        if h>=HOURLY_CALL_BUDGET or d>=DAILY_CALL_BUDGET:
            raise RuntimeError('mandatory_batch_budget_reached')
        db.execute('''INSERT INTO mandatory_batch_budget(requested_at,source,day,page)
                      VALUES(?,?,?,?)''',(moment.isoformat(),source,day,page))
        db.execute("DELETE FROM mandatory_batch_budget WHERE requested_at<?",
                   ((moment-dt.timedelta(days=4)).isoformat(),))

def fetch_page(source,day,page,fetch=None):
    if fetch is None:
        def fetch(url):
            req=urllib.request.Request(url,headers={'Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
    args={'source':source,'from':day+'0000','to':day+'2359',
          'page':page,'rows':ROWS}
    data=fetch(LOCAL+'/mandatory-enrichment-batch?'+urllib.parse.urlencode(args))
    if not isinstance(data,dict) or data.get('ok') is not True:
        raise ValueError('mandatory_batch_unverified_source')
    if data.get('source')!=source or data.get('page')!=page:
        raise ValueError('mandatory_batch_identity_mismatch')
    total=data.get('totalCount')
    raw=data.get('rawCount')
    items=data.get('items')
    if (type(total)is not int or type(raw)is not int or total<0 or
            not 0<=raw<=ROWS or not isinstance(items,list) or raw!=len(items) or
            (total>0 and raw==0) or any(not isinstance(x,dict) for x in items)):
        raise ValueError('mandatory_batch_invalid_page')
    if any(not re.fullmatch(r'[A-Za-z0-9-]{8,40}',
             str(x.get('bidNtceNo') or '')) for x in items):
        raise ValueError('mandatory_batch_missing_bid_number')
    return total,items

def page_rows(db,day,source):
    return db.execute('''SELECT page,total,rows,payload FROM mandatory_batch_pages
                         WHERE source=? AND day=? ORDER BY page''',(source,day)).fetchall()

def collected_source(db,day,source,fetch=None,limit=MAX_CALLS_PER_RUN):
    """Return (all raw rows or None when partial, official request count)."""
    pages=page_rows(db,day,source)
    if pages and pages[0][0]!=1:raise ValueError('mandatory_batch_page_one_missing')
    total=pages[0][1] if pages else None
    effective=pages[0][2] if pages else None
    if effective is not None and total>0 and effective==0:
        raise ValueError('mandatory_batch_first_page_empty')
    expected=max(1,math.ceil(total/effective)) if total else 1
    if expected>MAX_PAGES:raise ValueError('mandatory_batch_too_many_pages')
    fetched=0
    indexed={p[0]:p for p in pages}
    for page in range(1,expected+1):
        if page in indexed:continue
        if fetched>=limit:return None,fetched
        reserve(db,source,day,page)
        result,items=fetch_page(source,day,page,fetch)
        current=len(items)
        if total is None:
            total=result
            effective=current
        if result!=total or (total and not effective):
            raise ValueError('mandatory_batch_changed_or_empty')
        expected=max(1,math.ceil(total/effective)) if total else 1
        if expected>MAX_PAGES:
            raise ValueError('mandatory_batch_too_many_pages')
        if current!=min(effective,max(0,total-(page-1)*effective)):
            raise ValueError('mandatory_batch_page_size_mismatch')
        with db:
            db.execute('''INSERT OR REPLACE INTO mandatory_batch_pages
                          VALUES(?,?,?,?,?,?,?)''',
                       (source,day,page,total,current,
                        json.dumps(items,ensure_ascii=False,separators=(',',':')),stamp()))
        indexed[page]=(page,total,current,json.dumps(items))
        fetched+=1
        if page>=expected:break
    if len(indexed)!=expected:return None,fetched
    full=[]
    for page in range(1,expected+1):
        if page not in indexed:raise ValueError('mandatory_batch_page_gap')
        _,count,n,payload=indexed[page]
        if count!=total or n!=min(effective,max(0,total-(page-1)*effective)):
            raise ValueError('mandatory_batch_page_count_inconsistent')
        full.extend(json.loads(payload))
    if len(full)!=total:raise ValueError('mandatory_batch_incomplete_source')
    return full,fetched

def key_for(row):
    no=str(row.get('bidNtceNo') or '')
    order=str(row.get('bidNtceOrd') or '000').zfill(3)
    return (no,order) if re.fullmatch(r'\d{3}',order) else None

def group_rows(rows,allowed):
    groups=defaultdict(list)
    for row in rows:
        key=key_for(row)
        if key in allowed:groups[key].append(row)
    return groups

def license_requirements(rows):
    requirements=[]
    for row in rows:
        name=str(row.get('lcnsLmtNm') or '').strip()
        industry=str(row.get('permsnIndstrytyList') or '').strip()
        found=re.findall(r'(?<!\d)\d{4}(?!\d)',industry or name)
        codes=list(dict.fromkeys(c for c in found if not re.match(r'^20\d{2}$',c)))
        description=name+' '+industry
        if re.search(r'또는|택일|중\s*(?:하나|1종)|\bOR\b',description,re.I):
            logic='OR'
        elif re.search(r'모두|동시\s*보유|각각\s*보유|\bAND\b',description,re.I):
            logic='AND'
        else:logic='UNKNOWN'
        requirements.append({
            'name':name or '면허 제한 내용 확인 필요','codes':codes,
            'logic':logic,'group':str(row.get('lmtGrpNo') or ''),
            'sequence':str(row.get('lmtSno') or ''),
            'permittedIndustries':industry,
            'fieldRestrictions':str(row.get('indstrytyMfrcFldList') or '')})
    return requirements

def save_license(db,day,rows,allowed):
    grouped=group_rows(rows,allowed)
    good=0
    with db:
        for (no,order),items in grouped.items():
            if not items:continue
            requirements=license_requirements(items)
            payload={'ok':True,'complete':True,'bidNo':no,'order':order,
                     'requirements':requirements,'count':len(requirements),
                     'totalCount':len(items),'source':'나라장터 입찰공고정보서비스 면허제한',
                     'checkedAt':stamp(),'batchDay':day,
                     'limitations':'면허제한만 확인. 그 외 공고 자격·지역·실적은 별도 검증'}
            db.execute('''INSERT INTO bid_license_cache(bid_no,bid_ord,payload,checked_at)
                VALUES(?,?,?,?) ON CONFLICT(bid_no,bid_ord) DO UPDATE SET
                payload=excluded.payload,checked_at=excluded.checked_at''',
                (no,order,json.dumps(payload,ensure_ascii=False),payload['checkedAt']))
            good+=1
    # A zero-row date source is NOT proof that all bids lack requirements.
    return good

def save_extra(db,day,rows_by_source,allowed):
    groups={source:group_rows(rows_by_source[source],allowed)
            for source in SOURCES if source!='license'}
    keys=set().union(*(set(d) for d in groups.values()))
    stored=0
    with db:
        for no,order in keys:
            existing=db.execute('''SELECT payload FROM bid_extra_cache
                         WHERE bid_no=? AND bid_ord=?''',(no,order)).fetchone()
            if existing:
                try:
                    prior=json.loads(existing[0])
                    if prior.get('complete') is True:continue
                except (ValueError,TypeError):pass
            sources={}
            for source in groups:
                items=groups[source].get((no,order),[])
                sources[source]={
                    'ok':bool(items),'complete':bool(items),'totalCount':len(items),
                    'items':[{str(k)[:72]:str(v)[:350] for k,v in list(item.items())[:42]
                              if v is not None and not str(k).lower().startswith('servicekey')}
                             for item in items[:100]],
                    'operation':source,
                    'state':'verified_row_in_date_batch' if items else 'not_returned_for_date'}
            complete=all(z['complete'] for z in sources.values())
            payload={'ok':complete,'complete':complete,'bidNo':no,'order':order,
                     'checkedAt':stamp(),'sources':sources,'batchDay':day,
                     'source':'나라장터 입찰공고정보서비스 날짜 묶음',
                     'limitations':'조회 날짜에 없는 항목은 없는 조건으로 판정하지 않음'}
            db.execute('''INSERT INTO bid_extra_cache(bid_no,bid_ord,payload,checked_at)
                VALUES(?,?,?,?) ON CONFLICT(bid_no,bid_ord) DO UPDATE SET
                payload=excluded.payload,checked_at=excluded.checked_at''',
                (no,order,json.dumps(payload,ensure_ascii=False),payload['checkedAt']))
            stored+=1
    return stored

def run_once(db,fetch=None,at=None):
    groups=grouped_open_notices(db,at)
    day=choose_day(db,groups)
    if not day:return {'day':None,'calls':0,'status':'all_open_posted_days_checked'}
    names=groups[day]
    call_count=0
    results={}
    for source in SOURCES:
        old=db.execute('''SELECT verified_at FROM mandatory_batch_windows
                           WHERE source=? AND day=?''',(source,day)).fetchone()
        if old:
            age=(now()-dt.datetime.fromisoformat(old[0])).total_seconds()
            if age<=43200 or (dt.datetime.now(KST).date()-
                dt.datetime.strptime(day,'%Y%m%d').date()).days>1:
                # Still load previously verified complete source's archived pages
                result,requests=collected_source(db,day,source,fetch,limit=0)
                if result is not None:results[source]=result
                continue
            # Recently posted day changed; remove old pages for a fresh window.
            with db:
                db.execute("DELETE FROM mandatory_batch_pages WHERE day=? AND source=?",(day,source))
                db.execute("DELETE FROM mandatory_batch_windows WHERE day=? AND source=?",(day,source))
        data,requests=collected_source(db,day,source,fetch,
                                        limit=MAX_CALLS_PER_RUN-call_count)
        call_count+=requests
        if data is None:
            return {'day':day,'calls':call_count,'status':'partial_pages',
                    'source':source}
        results[source]=data
        # Mark a date as complete only after ALL pages verify their totals.
        with db:
            pages=db.execute('''SELECT COUNT(*) FROM mandatory_batch_pages
                                 WHERE source=? AND day=?''',(source,day)).fetchone()[0]
            db.execute('''INSERT OR REPLACE INTO mandatory_batch_windows
                          VALUES(?,?,?,?,?)''',
                       (source,day,stamp(),len(data),pages))
        if source=='license':
            save_license(db,day,data,names)
    if all(src in results for src in SOURCES):
        extras=save_extra(db,day,results,names)
        return {'day':day,'calls':call_count,'status':'complete','notices':len(names),
                'licensePositive':len(group_rows(results['license'],names)),
                'extraPositive':extras}
    return {'day':day,'calls':call_count,'status':'incomplete_source'}

def run_forever():
    print('MANDATORY_DATE_BATCH_ENABLED',json.dumps({
        'sources':list(SOURCES),'requestedRows':ROWS,'maxCallsPerPass':MAX_CALLS_PER_RUN,
        'noPerNoticeUpstream':True}),flush=True)
    db=connect()
    while True:
        try:
            result=run_once(db)
            print('MANDATORY_BATCH_PROGRESS',json.dumps(result),flush=True)
            wait=(600 if result.get('status')=='complete' else
                  120 if result.get('status')=='partial_pages' else 1800)
        except Exception as exc:
            print('MANDATORY_BATCH_RETRY_LATER',type(exc).__name__,
                  str(exc)[:100],flush=True)
            wait=3600 if ('rate' in str(exc).lower() or
                          'quota' in str(exc).lower() or
                          'budget' in str(exc).lower()) else 600
        time.sleep(wait)
