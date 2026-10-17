#!/usr/bin/env python3
"""The public official-award cache must never spend quota or invent evidence."""
import datetime
import json
import os
import runpy
import sqlite3
import tempfile
from pathlib import Path

API='/app/api.py' if os.path.isfile('/app/api.py') else str(
    Path(__file__).resolve().parents[1]/'server/g2b-proxy.py')
p=runpy.run_path(API,run_name='worklinks_award_cache_api_test')
g=p['cached_historic_awards'].__globals__
old=g['G2B_DB_PATH']
with tempfile.TemporaryDirectory() as tmp:
    g['G2B_DB_PATH']=os.path.join(tmp,'bids.sqlite3')
    try:
        result=p['cached_historic_awards']()
        assert result['ok'] and result['installed'] is False and result['records']==[]
        assert p['award_enricher_status']()['installed'] is False
        db=p['open_bid_db']()
        db.execute('''CREATE TABLE bid_award_cache(
          bid_no TEXT PRIMARY KEY,payload TEXT NOT NULL,checked_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE bid_award_attempts(
          bid_no TEXT PRIMARY KEY,reason TEXT NOT NULL,retry_after TEXT NOT NULL)''')
        db.execute('''CREATE TABLE bid_award_worker_status(
          id INTEGER PRIMARY KEY CHECK(id=1),last_run TEXT,last_success TEXT,
          requests_last_run INTEGER NOT NULL DEFAULT 0,
          stored_last_run INTEGER NOT NULL DEFAULT 0,
          errors_last_run INTEGER NOT NULL DEFAULT 0,
          cooldown_until TEXT,message TEXT)''')
        now=datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        record={'bidNo':'R25BK01241784','count':1,'rate':99.9,
           'amount':123456789,'winner':'검증업체','winnerBizno':'3058195207',
           'verifiedAt':now}
        db.execute('INSERT INTO bid_award_cache VALUES(?,?,?)',
                   (record['bidNo'],json.dumps(record),now))
        db.execute('INSERT INTO bid_award_attempts VALUES(?,?,?)',
                   ('R25BK00000000','no_verified_award','2031-01-01T00:00:00Z'))
        db.execute('INSERT INTO bid_award_worker_status VALUES(1,?,?,?,?,?,?,?)',
                   (now,now,2,1,0,None,'verified_award'))
        db.commit()
        # Raw official data stays on the private server: the public API returns
        # only confirmed data and counts, no bidder identity guess or secret.
        r=p['cached_historic_awards']()
        assert r['persisted'] and r['installed']
        assert r['totalCount']==1 and len(r['records'])==1
        assert r['records'][0]['count']==1
        assert r['records'][0]['winnerBizno']=='3058195207'
        assert 'serviceKey' not in json.dumps(r)
        state=p['award_enricher_status']()
        assert state['state']=='verified_award' and state['verifiedAwards']==1
        assert state['deferredUnknowns']==1
        assert state['requestsLastRun']==2 and state['storedLastRun']==1
        assert p['cached_historic_awards'](1,1)['records']==[]
        db.close()
    finally:g['G2B_DB_PATH']=old
print('WORKLINKS_AWARD_CACHE_READ_ONLY_API=PASS')
