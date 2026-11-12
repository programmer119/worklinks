#!/usr/bin/env python3
"""Source-backed OPEN-bid method fallback, generated from server123's saved DB.

No government API calls and no GitHub Actions recurrence. No license verdicts.
"""
import datetime as dt
import json
import os
import pathlib
import re
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
DEST=ROOT/'startup-support/g2b-award-fields-open.json'
API=os.environ.get('WORKLINKS_G2B_API','http://127.0.0.1:18192/api/g2b').rstrip('/')
KST=dt.timezone(dt.timedelta(hours=9))


def parse_close(v):
    m=re.match(r'^(\d{4})[-./]?(\d{2})[-./]?(\d{2})(?:[ T]?(\d{2})(?::?(\d{2}))?)?',str(v or ''))
    if not m:return None
    y,mo,day=map(int,m.group(1,2,3))
    try:return dt.datetime(y,mo,day,int(m.group(4) or 23),int(m.group(5) or 59))
    except ValueError:return None


def collect(fetch=None, now=None):
    if fetch is None:
        def fetch(offset):
            url=API+'/saved?sw=1&limit=500&offset='+str(offset)
            ledger=None
            request_key=None
            if os.environ.get('WORKLINKS_RFP_LEDGER_DB'):
                from rfp_call_ledger import CallLedger,cache_key
                ledger=CallLedger(os.environ['WORKLINKS_RFP_LEDGER_DB'])
                request_key=cache_key('local_award_fallback',offset)
                cache=ledger.get_json(request_key,max_age_seconds=180)
                if (isinstance(cache,dict) and cache.get('ok') is True
                        and cache.get('persisted') is True):
                    ledger.record('local_award_fallback',request_key,'verified_snapshot_reused')
                    return cache
            req=urllib.request.Request(url,headers={'User-Agent':'WorkLinks-Server123-AwardFallback/1.0',
                                                    'Accept':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=35) as response:
                    status=getattr(response,'status',200)
                    result=json.load(response)
                if not result.get('ok') or result.get('persisted') is not True:
                    raise ValueError('saved_bid_data_not_verified')
                if ledger is not None:
                    ledger.record('local_award_fallback_http',request_key,'http_ok',
                                  http_status=status)
                    ledger.save_json(request_key,result,max_bytes=4_000_000)
                return result
            except Exception as exc:
                if ledger is not None:
                    ledger.record('local_award_fallback_http',request_key,'http_failed',
                                  http_status=getattr(exc,'code',None),
                                  error_class=type(exc).__name__)
                raise
    if now is None:
        now=dt.datetime.now(KST).replace(tzinfo=None)
    rows=[]
    total=None
    for page in range(200):
        offset=page*500
        data=fetch(offset)
        if not data.get('ok') or data.get('persisted') is not True:
            raise ValueError('saved_bid_data_not_verified')
        if total is None:total=int(data.get('totalCount') or 0)
        batch=data.get('items')
        if not isinstance(batch,list):
            raise ValueError('saved_bid_page_not_list')
        rows.extend(batch)
        if offset+len(batch)>=total:break
        if len(batch)!=500:raise ValueError('saved_bid_premature_page_end')
    else:
        raise ValueError('saved_bid_pagination_limit')
    if total is None or total<100 or len(rows)<total:
        raise ValueError('saved_bid_index_incomplete')
    out={}
    for item in rows:
        no=str(item.get('bidNo') or '')
        if not re.fullmatch(r'R\d{2}BK\d{8}',no):continue
        close=parse_close(item.get('closes'))
        if not close or close<=now:continue
        order=str(item.get('order') or '0').zfill(3)
        if not re.fullmatch(r'\d{3}',order):continue
        fields={k:str(item.get(k) or '') for k in
                ('contract','awardMethod','awardMethodCode','awardFloorRate')}
        if not any(fields.values()):continue
        out[no+':'+order]=fields
    return {'ok':True,'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
            'source':'WorkLinks server123 saved DB /saved; no direct official API call',
            'totalSavedSw':total,'count':len(out),'byNotice':out}


def main():
    data=collect()
    DEST.parent.mkdir(parents=True,exist_ok=True)
    DEST.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',
                    encoding='utf-8')
    print('WORKLINKS_OPEN_AWARD_FALLBACK',data['count'],'totalSw',data['totalSavedSw'])


if __name__=='__main__':main()
