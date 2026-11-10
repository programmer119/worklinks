#!/usr/bin/env python3
"""One-off, quota-aware fill of official award fields for unexpired WorkLinks SW notices.

Only notices already in the WorkLinks SW database with a parseable deadline
strictly later than current KST are eligible. Does not download or parse RFPs.
Only merges nonempty official API fields; never changes expired notices or
overwrites other notice fields. Summarizes verified results after attempting one pass.
"""
import datetime as dt
import json
import os
import re
import runpy
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

SOURCE = '/app/g2b-full-crawler.py'
KST = dt.timezone(dt.timedelta(hours=9))
PINNED = ()  # Grouped A02 refresh covers all active notices without per-notice requests.
MAX_REQUESTS = int(os.environ.get('OPEN_AWARD_MAX_REQUESTS','120'))
MAX_SECONDS = int(os.environ.get('OPEN_AWARD_MAX_SECONDS','510'))
MAX_WINDOW_PAGES = int(os.environ.get('OPEN_AWARD_MAX_WINDOW_PAGES','35'))
FIELDS = (
    ('contract', 'cntrctCnclsMthdNm'),
    ('awardMethod', 'sucsfbidMthdNm'),
    ('awardMethodCode', 'sucsfbidMthdCd'),
    ('awardFloorRate', 'sucsfbidLwltRate'),
)
ROOT = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService02'
OPS = {
 'servc': 'getBidPblancListInfoServcPPSSrch02',
 'thng': 'getBidPblancListInfoThngPPSSrch02',
 'cnstwk': 'getBidPblancListInfoCnstwkPPSSrch02',
 'frgcpt': 'getBidPblancListInfoFrgcptPPSSrch02',
}
class UpstreamError(Exception):
    pass
def now_kst():
    return dt.datetime.now(KST).replace(tzinfo=None)
def parse_kst(value, end=False):
    v = str(value or '').strip()
    m = re.match(r'^(\d{4})[-./]?(\d{2})[-./]?(\d{2})(?:[ T]?(\d{2})(?::?(\d{2}))?(?::?(\d{2}))?)?',v)
    if not m:
        return None
    y,mo,d = map(int, m.group(1,2,3))
    hour=int(m.group(4)) if m.group(4) is not None else (23 if end else 0)
    minute=int(m.group(5)) if m.group(5) is not None else (59 if end else 0)
    second=int(m.group(6)) if m.group(6) is not None else (59 if end else 0)
    try:
        return dt.datetime(y,mo,d,hour,minute,second)
    except ValueError:
        return None
def ordinal(value):
    s=str(value if value is not None else '0').strip()
    return s.zfill(3) if s.isdigit() else s
def read_rows(db):
    now=now_kst()
    excluded=defaultdict(int)
    candidates={}
    for kind,no,order,raw in db.execute(
      "SELECT kind,bid_no,bid_ord,payload FROM bid_notices WHERE sw_candidate=1"):
        try:
            obj=json.loads(raw)
        except (TypeError,ValueError):
            excluded['bad_json']+=1
            continue
        close=parse_kst(obj.get('closes'),end=True)
        if close is None:
            excluded['deadline_unknown']+=1
            continue
        if close <= now:
            excluded['deadline_passed']+=1
            continue
        if kind not in OPS:
            excluded['unsupported_kind']+=1
            continue
        if obj.get('awardMethod') and obj.get('awardMethodCode'):
            excluded['already_complete']+=1
            continue
        posted=parse_kst(obj.get('posted'))
        if posted is None or posted > now:
            excluded['posted_unknown_or_future']+=1
            continue
        candidates[(kind,str(no),ordinal(order))]={
            'deadline':close,'posted':posted.date().strftime('%Y%m%d')}
    return candidates,dict(excluded)
def official_request(key, operation, args):
    params=dict(args,serviceKey=key,type='json',pageNo=args.get('pageNo',1),
                numOfRows=args.get('numOfRows',999))
    url=ROOT+'/'+operation+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        'Accept':'application/json','User-Agent':'WorkLinksOpenAwardOnePass/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=22) as resp:
            doc=json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise UpstreamError('HTTP_'+str(exc.code)) from None
    except (OSError,TimeoutError,ValueError,UnicodeError):
        raise UpstreamError('network_or_json_error') from None
    response=doc.get('response',{})
    header=response.get('header',{})
    code=str(header.get('resultCode','MISSING'))
    if code not in ('0','00'):
        raise UpstreamError('api_code_'+re.sub('[^A-Za-z0-9]','',code)[:20])
    body=response.get('body',{})
    entries=body.get('items') or []
    if isinstance(entries,dict):
        entries=entries.get('item') or []
    if not isinstance(entries,list):
        entries=[entries]
    try: total=int(body.get('totalCount') or 0)
    except (ValueError,TypeError): total=0
    return total,[x for x in entries if isinstance(x,dict)]
def merge(db, targets, items, kind, stats):
    found={}
    for item in items:
        key=(kind,str(item.get('bidNtceNo') or ''),ordinal(item.get('bidNtceOrd')))
        if key in targets:
            found[key]=item
    for key,item in found.items():
        oldrow=db.execute('SELECT payload FROM bid_notices WHERE kind=? AND bid_no=? AND bid_ord=?',
                          key).fetchone()
        if not oldrow:
            continue
        obj=json.loads(oldrow[0])
        close=parse_kst(obj.get('closes'),end=True)
        if close is None or close<=now_kst():
            stats['deadline_rejected_on_write']+=1
            continue
        delta=False
        for field,api_field in FIELDS:
            value=item.get(api_field)
            if value is not None and str(value).strip():
                if str(obj.get(field) or '') != str(value):
                    obj[field]=value
                    delta=True
        if delta:
            with db:
                db.execute('UPDATE bid_notices SET payload=? WHERE kind=? AND bid_no=? AND bid_ord=?',
                            (json.dumps(obj,ensure_ascii=False,separators=(',',':')),*key))
            stats['updated']+=1
        else:
            stats['unchanged_api_empty']+=1
        targets.pop(key,None)
        stats['found_official']+=1
    return len(found)
def run():
    crawler=runpy.run_path(SOURCE,run_name='onepass')
    key=crawler['secret']()
    db=crawler['connect']()
    targets,excluded=read_rows(db)
    total=len(targets)
    stats=defaultdict(int)
    print('OPEN_AWARD_START',json.dumps({
        'as_of_kst':now_kst().isoformat(timespec='seconds'),
        'eligible_missing':total,'excluded':excluded,
        'max_requests':MAX_REQUESTS,'max_seconds':MAX_SECONDS},
        ensure_ascii=False),flush=True)
    if not targets:
        db.close()
        print('OPEN_AWARD_DONE status=nothing_missing',flush=True)
        return
    started=time.monotonic()
    def budget():
        return (stats['requests']<MAX_REQUESTS and
                time.monotonic()-started<MAX_SECONDS)
    def call(operation,args):
        if not budget():
            raise UpstreamError('time_or_request_budget')
        stats['requests']+=1
        try:
            return official_request(key,operation,args)
        finally:
            time.sleep(0.27)

    # Four screenshot notices: exactly one official request each while still open.
    for num in PINNED:
        chosen=[k for k in targets if k[0]=='servc' and k[1]==num]
        if not chosen:
            print('OPEN_AWARD_PINNED_SKIP',num,'already_complete_or_expired',flush=True)
            continue
        try:
            total_count,items=call('getBidPblancListInfoServc',{
                'inqryDiv':2,'bidNtceNo':num,'numOfRows':10})
        except UpstreamError as exc:
            print('OPEN_AWARD_PINNED_ERROR',num,str(exc),flush=True)
            if '429' in str(exc):
                stats['rate_limit_429']+=1
                break
            continue
        merge(db,targets,items,'servc',stats)
        print('OPEN_AWARD_PINNED_RESULT',num,
              'matched',len([x for x in items if str(x.get('bidNtceNo'))==num]),
              'still_missing',any(k[1]==num for k in targets),flush=True)

    groups=defaultdict(list)
    for k,x in targets.items():
        groups[(k[0],x['posted'])].append((k,x['deadline']))
    # Expiring soon first; fewer pages earlier.
    ordered=sorted(groups.items(),key=lambda v:(
      min(x[1] for x in v[1]), -len(v[1])))
    print('OPEN_AWARD_GROUPS',len(ordered),'remaining_notices',len(targets),flush=True)
    group_limited=False
    for (kind,day),members in ordered:
        if not budget():
            break
        # Use known official crawl-window page counts to avoid huge windows.
        row=db.execute("SELECT pages FROM crawl_windows WHERE kind=? AND day=?",
                       (kind,day)).fetchone()
        if row and int(row[0] or 1)>MAX_WINDOW_PAGES:
            stats['large_group_skipped']+=1
            continue
        current={(k):x for k,x in targets.items() if k[0]==kind and x['posted']==day}
        if not current:
            continue
        collected=[]
        try:
            first_count,first=call(OPS[kind],{'inqryDiv':1,
                   'inqryBgnDt':day+'0000','inqryEndDt':day+'2359','numOfRows':999})
            pages=max(1,(first_count+998)//999)
            if pages>MAX_WINDOW_PAGES:
                stats['large_group_skipped']+=1
                continue
            collected.extend(first)
            for page in range(2,pages+1):
                _,rows=call(OPS[kind],{'inqryDiv':1,'inqryBgnDt':day+'0000',
                         'inqryEndDt':day+'2359','numOfRows':999,'pageNo':page})
                collected.extend(rows)
            # The full window must be fetched before applying DB changes,
            # and no other unrelated or expired notice may be updated.
            if first_count>0 and len(collected)<first_count:
                stats['incomplete_groups']+=1
                print('OPEN_AWARD_WINDOW_INCOMPLETE',kind,day,
                      len(collected),first_count,flush=True)
                continue
            merge(db,targets,collected,kind,stats)
            stats['group_windows_complete']+=1
            if stats['group_windows_complete']<=6:
                print('OPEN_AWARD_WINDOW_OK',kind,day,'api_rows',len(collected),
                      'targets_left',len(targets),flush=True)
        except UpstreamError as exc:
            print('OPEN_AWARD_WINDOW_ERROR',kind,day,str(exc),flush=True)
            stats['group_errors']+=1
            if '429' in str(exc):
                stats['rate_limit_429']+=1
                group_limited=True
            if 'time_or_request_budget' in str(exc):
                break
            # Only one failed group probe before switching to proven direct lookup.
            if group_limited:
                break

    # Never fall back to ~1,000 per-notice API calls if grouped lookup is limited.
    if group_limited:
        print('OPEN_AWARD_QUOTA_STOP_NO_SINGLE_FALLBACK',flush=True)
    remaining,_=read_rows(db)
    after=len(remaining)
    pinned={}
    for num in PINNED:
        row=db.execute('SELECT payload FROM bid_notices WHERE kind="servc" AND bid_no=?',
                       (num,)).fetchone()
        if not row:
            pinned[num]='not_in_db'
        else:
            ob=json.loads(row[0])
            pinned[num]={k:str(ob.get(k) or '') for k,_ in FIELDS}
    result={
        'as_of_kst':now_kst().isoformat(timespec='seconds'),
        'initial_missing':total,
        'final_missing':after,
        'resolved':max(0,total-after),
        'requests':stats['requests'],
        'group_windows_complete':stats['group_windows_complete'],
        'single_requests':stats['single_requests'],
        'updated_rows':stats['updated'],
        'rate_limit_429':stats['rate_limit_429'],
        'group_errors':stats['group_errors'],
        'remaining_incomplete_or_quota':after,
        'budget_exhausted':not budget(),
        'pinned':pinned,
    }
    print('OPEN_AWARD_FINAL',json.dumps(result,ensure_ascii=False),flush=True)
    db.close()

if __name__=='__main__':
    run()
