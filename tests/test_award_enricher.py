#!/usr/bin/env python3
"""Guard verified historical award enrichment and shared API quota safety."""
import datetime as dt
import json
import os
import runpy
import sqlite3
import tempfile
from pathlib import Path

WORKER = ('/app/g2b-award-enricher.py' if os.path.isfile('/app/g2b-award-enricher.py')
          else str(Path(__file__).resolve().parents[1] / 'server/g2b-award-enricher.py'))
p = runpy.run_path(WORKER, run_name='worklinks_test')
now = dt.datetime(2026, 10, 17, 7, tzinfo=dt.timezone.utc)
timestamp = p['stamp'](now)
with tempfile.TemporaryDirectory() as tmp:
    conn = sqlite3.connect(os.path.join(tmp,'test.sqlite3'))
    p['init'](conn)
    conn.execute('''CREATE TABLE bid_notices(kind TEXT, bid_no TEXT, bid_ord TEXT,
      payload TEXT, sw_candidate INTEGER, last_seen TEXT)''')
    conn.execute('''CREATE TABLE recurring_projects(kind TEXT,bid_no TEXT,
      history_json TEXT, repeat_years INTEGER)''')
    notices = [
       {'bidNo':'R26BK01700001', 'closes':'2026-11-05 10:00:00', 'kind':'servc'},
       {'bidNo':'R26BK01700002', 'closes':'2026-10-01 10:00:00', 'kind':'servc'},
       {'bidNo':'R26BK01700003', 'closes':'2026-11-20 10:00:00', 'kind':'servc'},
       {'bidNo':'R26BK01700004', 'closes':'2026-11-22 10:00:00', 'kind':'servc'},
    ]
    def add_notice(item, history):
        conn.execute('INSERT INTO bid_notices VALUES(?,?,?,?,?,?)',
            ('servc',item['bidNo'],'000',json.dumps(item),1,timestamp))
        conn.execute('INSERT INTO recurring_projects VALUES(?,?,?,?)',
            ('servc',item['bidNo'],json.dumps(history),2))
    h1=[{'year':2026,'verified':True},
        {'year':2025,'bidNo':'R25BK01000001','verified':True},
        {'year':2024,'bidNo':'20241000001','verified':True},
        {'year':2023,'bidNo':'20231000001','verified':False}]
    add_notice(notices[0],h1)
    add_notice(notices[1],[{'year':2025,'bidNo':'R25BK01000002','verified':True}])
    add_notice(notices[2],[{'year':2025,'bidNo':'R25BK01000003','verified':True}])
    add_notice(notices[3],[{'year':2025,'bidNo':'R25BK01000004','verified':True}])
    conn.commit()
    found=p['eligible_history_numbers'](conn,now)
    assert 'R25BK01000001' in found and '20241000001' in found
    assert 'R25BK01000002' not in found,'closed notices must be skipped'
    assert '20231000001' not in found,'unverified historic association must be skipped'
    assert len(found)==4
    assert p['valid_record']({'bidNo':'R25BK01000001','count':0,'verifiedAt':timestamp}) is None
    assert p['valid_record']({'bidNo':'R25BK01000001','count':2,
        'winnerBizno':'123','verifiedAt':timestamp}) is None
    assert p['as_award']('R25BK01000001', {'ok':True,'items':[], 'totalCount':0}) is None
    rows=[{'bidNtceNo':'R25BK01000001','prtcptCnum':'1',
        'bidwinnrBizno':'3058195207','bidwinnrNm':'실제 낙찰업체',
        'sucsfbidRate':'99.993','sucsfbidAmt':'123456789'}]
    parsed=p['as_award']('R25BK01000001', {'ok':True,'items':rows,
        'totalCount':1},now=now)
    assert parsed['count']==1 and parsed['winnerBizno']=='3058195207'
    assert parsed['rate']==99.993 and parsed['amount']==123456789
    assert parsed['verifiedAt']==timestamp
    # Do not accept awards from a different notice or contradictory legal IDs.
    assert p['as_award']('R25BK01000001',{'ok':True,'items':[{
        **rows[0],'bidNtceNo':'R25BK09000009'}],'totalCount':1}) is None
    try:
        p['as_award']('R25BK01000001',{'ok':True,'items':[
            rows[0],{**rows[0],'bidwinnrBizno':'3148187981'}], 'totalCount':2})
    except p['RemoteError'] as e:
        assert e.reason=='ambiguous_notice_award'
    else:
        raise AssertionError('conflicting winner legal IDs cannot be called verified')

    seeded={'schemaVersion':1,'source':p['SOURCE'],'verifiedAt':timestamp,
        'records':[{'bidNo':'R25BK01000001','count':1,'rate':99.993,
        'amount':123456789,'winner':'실제 낙찰업체','winnerBizno':'3058195207',
        'verifiedAt':timestamp},
        {'bidNo':'R25BK01000004','count':0,'rate':None,'amount':None,'winner':'',
        'winnerBizno':'','verifiedAt':timestamp}]}
    seed_file=os.path.join(tmp,'official.json')
    with open(seed_file,'w',encoding='utf-8') as f:json.dump(seeded,f)
    assert p['seed_existing_official_snapshot'](conn,seed_file)==1
    assert p['seed_existing_official_snapshot'](conn,seed_file)==0,'restart must not double seed'
    assert 'R25BK01000001' not in p['candidates'](conn,now)

    calls=[]
    def fake(no):
        calls.append(no)
        if no=='20241000001':
            return {'bidNo':no,'count':1,'rate':100.0,'amount':11200,'winner':'다른업체',
                'winnerBizno':'3148187981','date':'','verifiedAt':timestamp}
        return None
    c=p['cycle'](conn,fetch=fake,now=now,maximum=2,gap=0)
    assert c['requests']==2 and c['stored']==1 and c['errors']==0
    assert len(calls)==2 and calls[0]=='20241000001'
    assert conn.execute('SELECT COUNT(*) FROM bid_award_cache').fetchone()[0]==2
    assert conn.execute('SELECT reason FROM bid_award_attempts').fetchone()[0]=='no_verified_award'
    assert calls[1] not in p['candidates'](conn,now),'empty provider answer must use retry delay'
    assert 'R25BK01000001' not in p['candidates'](conn,now)

    # Explicitly test provider quota exhaustion stops this cycle without
    # creating zero-bidder cache entries, and next cycle honors cooldown.
    def rate_limited(no):
        raise p['RemoteError']('rate_limited',True)
    later=now+dt.timedelta(hours=1)
    bad=p['cycle'](conn,fetch=rate_limited,now=later,maximum=2,gap=0)
    assert bad=={'requests':1,'stored':0,'errors':1,'state':'rate_limited'}
    after=p['cycle'](conn,fetch=rate_limited,now=later+dt.timedelta(minutes=10),gap=0)
    assert after['state']=='cooldown' and after['requests']==0
    assert conn.execute('SELECT COUNT(*) FROM bid_award_cache').fetchone()[0]==2
    status=conn.execute('SELECT requests_last_run,errors_last_run FROM bid_award_worker_status').fetchone()
    assert status==(1,1)
    conn.close()
print('WORKLINKS_OFFICIAL_AWARD_ENRICHER=PASS')
