#!/usr/bin/env python3
"""No-network proof for safe full-day batch metadata, caching, and pagination."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import urllib.parse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rfp_dual_queue import RfpDualQueue
import rfp_bulk_manifests as bulk

class NoDelay:
    def acquire(self):pass

today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
new_day=(today-dt.timedelta(days=1)).isoformat()
old_day=(today-dt.timedelta(days=2)).isoformat()
first='R26BK00010001'
second='R26BK00010002'
third='R26BK00010003'
other='R26BK00010004'
new_keys=[first+':000',second+':000',third+':000']
old_keys=[other+':000']
dates={first:new_day,second:new_day,third:new_day,other:old_day}

def make_items(day,source):
    if day==new_day:
        if source=='ordinary':
            return [{'bidNo':first,'order':'000','name':'first.pdf','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/first.pdf','source':'notice_attachment_api'},
                    {'bidNo':first,'order':'000','name':'second.pdf','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/second.pdf','source':'notice_attachment_api'},
                    {'bidNo':second,'order':'000','name':'other.hwp','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/other.hwp','source':'notice_attachment_api'}]
        if source=='eorder':
            return [{'bidNo':first,'order':'000','name':'first.pdf','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/first.pdf','source':'eorder'}]
        if source=='detail':
            return [{'bidNo':second,'order':'000','name':'detail.pdf','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/detail.pdf','source':'notice_detail'}]
    if day==old_day and source=='ordinary':
        return [{'bidNo':other,'order':'000','name':'old.hwp','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/old.hwp','source':'notice_attachment_api'}]
    return []

calls=[]
def fetch(url):
    parts=urllib.parse.urlparse(url)
    q=dict(urllib.parse.parse_qsl(parts.query))
    if parts.path=='/api/g2b/rfp-attachment-single':
        assert q['bidNo']==third,q
        calls.append((new_day,'single',0))
        return {'ok':True,'bidNo':third,'order':'000',
                'attachments':{'ok':True,'complete':True,'items':[],
                               'count':0},
                'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
    assert parts.path=='/api/g2b/rfp-attachment-batch',parts.path
    assert 'bidNo' not in q and q['rows']=='2'
    day=dt.datetime.strptime(q['from'],'%Y%m%d%H%M').date().isoformat()
    assert q['to'].endswith('2359')
    source=q['source']
    all_items=make_items(day,source)
    page=int(q['page'])
    rows=all_items[(page-1)*2:page*2]
    calls.append((day,source,page))
    return {'ok':True,'source':source,'totalCount':len(all_items),
            'page':page,'rawCount':len(rows),'items':rows}

with tempfile.TemporaryDirectory() as tmp:
    db=Path(tmp)/'bids.sqlite3'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE bid_notices (bid_no TEXT,bid_ord TEXT,payload TEXT,sw_candidate INTEGER)')
        for no,day in dates.items():
            con.execute('INSERT INTO bid_notices VALUES (?,?,?,1)',
                        (no,'000',json.dumps({'posted':day+'T10:00:00'})))
    queue=RfpDualQueue(Path(tmp)/'queue.sqlite3')
    queue.enqueue([(no,'000','2099-12-31') for no in dates],'reader-v3')
    assert queue.claim_download(ready_manifest=True) is None

    original_rows=bulk.ROWS
    original_pass=bulk.MAX_FETCH_PER_PASS
    bulk.ROWS=2
    planner=bulk.BulkManifestPlanner(queue,db,fetch,NoDelay())
    try:
        # Crash simulation: only page 1 is stored. Do not publish partial
        # metadata when more pages exist or any source remains incomplete.
        bulk.MAX_FETCH_PER_PASS=1
        partial=planner.populate_one_day()
        assert partial.get('probed') is True,partial
        assert queue.bulk_manifest(new_keys[0]) is None
        assert len(calls)==1,calls
        bulk.MAX_FETCH_PER_PASS=18
        complete=planner.populate_one_day()
        assert complete['new']==3,complete
        assert calls.count((new_day,'ordinary',1))==1,calls
        assert calls.count((new_day,'ordinary',2))==1,calls
        a=queue.bulk_manifest(new_keys[0])
        b=queue.bulk_manifest(new_keys[1])
        c=queue.bulk_manifest(new_keys[2])
        assert a['attachments']['complete'] and a['noticeDocuments']['complete']
        assert len(a['attachments']['items'])==2,a
        assert len(b['attachments']['items'])==2,b
        assert c['attachments']['items']==[],c
        assert a['region']['ok'] is False,'region must NOT have been queried'
        assert queue.claim_download(ready_manifest=True)[0] in new_keys
        calls_after_new=len(calls)
        older_probe=planner.populate_one_day()
        assert older_probe.get('probed') is True,older_probe
        older=planner.populate_one_day()
        assert older['new']==1,older
        assert queue.bulk_manifest(old_keys[0])['attachments']['count']==1
        assert len(calls)>calls_after_new
        assert planner.populate_one_day()['new']==0
        assert queue.stats()['download']['done']==0
        print('RFP_BULK_3_SOURCES_ALL_PAGES_PERSISTED_NO_REGION=PASS',
              {'notices':4,'totalOfficialProxyCalls':len(calls)},flush=True)

        # An invalid provider count must never be treated as an empty
        # successful attachment list or a completed scan.
        with sqlite3.connect(queue.path) as con:
            con.execute('DELETE FROM rfp_bulk_pages')
            con.execute('DELETE FROM rfp_bulk_manifests')
        def bad_fetch(url):
            q=dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
            return {'ok':True,'source':q['source'],'page':int(q['page']),
                    'totalCount':5,'rawCount':0,'items':[]}
        broken=bulk.BulkManifestPlanner(queue,db,bad_fetch,NoDelay())
        try:broken.populate_one_day()
        except bulk.BulkManifestError as ex:
            assert 'batch_invalid_provider_pagination' in str(ex)
        else:raise AssertionError('invalid provider page was accepted')
        assert queue.bulk_manifest(new_keys[0]) is None
        print('RFP_BULK_INCOMPLETE_PAGINATION_FAIL_CLOSED=PASS',flush=True)
    finally:
        bulk.ROWS=original_rows
        bulk.MAX_FETCH_PER_PASS=original_pass

# Proxy adapter uses exactly one official source operation per page and
# refuses ranges over seven days before spending an upstream request.
spec=importlib.util.spec_from_file_location('rfp_batch_proxy',ROOT/'server'/'g2b-proxy.py')
proxy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)
g=proxy.rfp_attachment_batch_page.__globals__
saved=g['request_api']
seen=[]
def fake_request(base,operation,params):
    seen.append((operation,params))
    return {'items':[{'bidNtceNo':first,'bidNtceOrd':'000','atchFileNm':'first.pdf',
                      'atchFileUrl':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/first.pdf'}],
            'totalCount':1}
g['request_api']=fake_request
try:
    start=new_day.replace('-','')+'0000'
    end=new_day.replace('-','')+'2359'
    result=proxy.rfp_attachment_batch_page('ordinary',start,end,1,1000)
    assert result['ok'] and result['rawCount']==1
    assert result['items'][0]['bidNo']==first
    assert len(seen)==1 and seen[0][0]=='getBidPblancListInfoAtchFileInfo02'
    assert seen[0][1]['inqryDiv']==1 and seen[0][1]['numOfRows']==1000
    assert 'bidNtceNo' not in seen[0][1],seen
    try:
        proxy.rfp_attachment_batch_page('ordinary','202610010000','202610102359',1,1000)
    except proxy.ApiError as ex:assert ex.status==400
    else:raise AssertionError('provider 7-day bound not enforced')
    assert len(seen)==1
    single=proxy.rfp_attachment_single(first,'000')
    assert single['ok'] is True and single['attachments']['complete']
    assert single['region']['ok'] is False
    assert len(seen)==4,seen  # one batch + exactly THREE doc operations
    assert set(op for op,_ in seen[1:])==set(proxy.RFP_BATCH_SOURCES.values())
    assert not any('PrtcptPsblRgn' in op for op,_ in seen)
finally:
    g['request_api']=saved
print('RFP_BULK_OFFICIAL_DATE_RANGE_ADAPTER_AND_THREE_SOURCE_FALLBACK=PASS',flush=True)
