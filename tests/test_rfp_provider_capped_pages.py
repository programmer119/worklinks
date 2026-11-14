#!/usr/bin/env python3
"""Official provider returns only 10/151 despite numOfRows=1000.

The real server123 response on 2026-11-14 showed this precise mismatch.
Test verifies actual-page inference, legacy reuse, completeness, dense-day
first, and fail-closed if provider repeats page 1 for every requested page.
"""
import datetime as dt
import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rfp_bulk_manifests as bulk
from rfp_dual_queue import RfpDualQueue

today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
day=(today-dt.timedelta(days=1)).isoformat()
sparse_day=today.isoformat()
targets=['R26BK'+str(i+10000).zfill(8) for i in range(30)]
all_rows={}
for source in bulk.SOURCES:
    all_rows[source]=[
        {'bidNo':targets[i] if i<30 else 'R26BK'+str(i+30000).zfill(8),
         'order':'000','name':str(i)+'.pdf',
         'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/'+source+'/'+str(i)+'.pdf',
         'source':source}
        for i in range(151)]
calls=[]
def capped_fetch(url):
    path=urllib.parse.urlsplit(url)
    assert path.path=='/api/g2b/rfp-attachment-batch',path
    q=dict(urllib.parse.parse_qsl(path.query))
    source=q['source']
    page=int(q['page'])
    # A provider which caps at ten rows despite the requested 1000.
    rows=all_rows[source][(page-1)*10:page*10]
    calls.append((source,page,int(q['rows'])))
    return {'ok':True,'source':source,'page':page,
            'totalCount':151,'rawCount':len(rows),'items':rows}

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    db=root/'bids.sqlite3'
    with sqlite3.connect(db) as sql:
        sql.execute('CREATE TABLE bid_notices(bid_no TEXT,bid_ord TEXT,payload TEXT,sw_candidate INTEGER)')
        for no in targets:
            sql.execute('INSERT INTO bid_notices VALUES (?,?,?,1)',
                        (no,'000',json.dumps({'posted':day+'T15:00:00'})))
        sql.execute('INSERT INTO bid_notices VALUES (?,?,?,1)',
                    ('R26BK00999999','000',json.dumps({'posted':sparse_day+'T12:00:00'})))
    queue=RfpDualQueue(root/'queue.sqlite3')
    queue.enqueue([(bid,'000','2099-12-31') for bid in targets+['R26BK00999999']],'v1')
    # A REAL legacy first page from before the fix was requested as 1000,
    # but returned 10/151. Reuse it, never redownload just to change size.
    with queue.connect() as sql:
        sql.execute('''INSERT INTO rfp_bulk_pages(
            day,source,page,total_count,raw_count,items_json,saved_at)
            VALUES(?,?,?,?,?,?,?)''',
            (day,'ordinary',1,151,10,json.dumps(all_rows['ordinary'][:10]),
             dt.datetime.now(dt.timezone.utc).isoformat()))
    planner=bulk.BulkManifestPlanner(queue,db,capped_fetch,bulk.NoDelay() if hasattr(bulk,'NoDelay') else type('Delay',(),{'acquire':lambda self:None})())
    orig_hour=bulk.HOURLY_LIMIT
    orig_day=bulk.DAILY_LIMIT
    bulk.HOURLY_LIMIT=100
    bulk.DAILY_LIMIT=200
    try:
        first=planner.populate_one_day()
        assert first['day']==day and first['new']==30,first
        assert len(calls)==47,(len(calls),calls)
        assert ('ordinary',1,1000) not in calls,'legacy full page should be reused'
        assert ('ordinary',2,10) in calls,calls
        assert ('ordinary',16,10) in calls,calls
        assert ('eorder',1,1000) in calls,calls
        assert ('detail',1,1000) in calls,calls
        assert ('detail',16,10) in calls,calls
        assert all(queue.bulk_manifest(bid+':000') is not None for bid in targets)
        assert queue.bulk_manifest('R26BK00999999:000') is None
        assert planner._cached_pages(day,'ordinary') is not None
        assert len(planner._cached_pages(day,'ordinary'))==151
        print('RFP_PROVIDER_151_ROWS_10_PER_PAGE_COMPLETE=PASS',
              {'notices':30,'actualSourceCalls':len(calls),
               'legacyFirstPageReused':True,'denseBeforeSparse':True},flush=True)
    finally:
        bulk.HOURLY_LIMIT=orig_hour
        bulk.DAILY_LIMIT=orig_day

# A provider ignoring the page number completely can return identical
# page data. Never mark that day as complete merely because counts add up.
with tempfile.TemporaryDirectory() as tmp:
    queue=RfpDualQueue(Path(tmp)/'q.sqlite3')
    for n in targets:queue.enqueue([(n,'000','2099-12-31')],'v1')
    db=Path(tmp)/'bids.sqlite3'
    with sqlite3.connect(db) as sql:
        sql.execute('CREATE TABLE bid_notices(bid_no TEXT,bid_ord TEXT,payload TEXT,sw_candidate INTEGER)')
        for n in targets:
            sql.execute('INSERT INTO bid_notices VALUES (?,?,?,1)',
                        (n,'000',json.dumps({'posted':day})))
    class FakePace:
        def acquire(self):pass
    def repeated_fetch(url):
        q=dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        page=int(q['page'])
        rows=all_rows[q['source']][:10 if page<16 else 1]
        return {'ok':True,'source':q['source'],'page':page,
                'totalCount':151,'rawCount':len(rows),'items':rows}
    planner=bulk.BulkManifestPlanner(queue,db,repeated_fetch,FakePace())
    result=planner.populate_one_day()
    assert result.get('partial') is True,result
    assert all(queue.bulk_manifest(n+':000') is None for n in targets)
    print('RFP_PROVIDER_REPEATED_PAGE_FAILS_CLOSED=PASS',flush=True)
