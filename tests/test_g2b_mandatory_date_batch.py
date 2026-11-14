#!/usr/bin/env python3
"""A02 four-source date batch: all pages, durable resume and no false absences."""
import datetime as dt
import importlib.util
import json
import sqlite3
import tempfile
import urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'server/g2b-mandatory-date-batch.py'
spec=importlib.util.spec_from_file_location('mandatory_date_batch',p)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
bid='R26BK12345678'
other='R26BK12345679'
day=(dt.datetime.now(mod.KST).date()-dt.timedelta(days=1)).strftime('%Y%m%d')
calls=[]
def fake(url):
    parsed=urllib.parse.urlparse(url)
    assert parsed.path.endswith('/mandatory-enrichment-batch')
    args=dict(urllib.parse.parse_qsl(parsed.query))
    assert 'bidNo' not in args and 'bidNtceNo' not in args
    assert args['from']==day+'0000' and args['to']==day+'2359'
    assert args['rows']=='999'
    source=args['source']
    page=int(args['page'])
    calls.append((source,page))
    if source=='license':
        # Provider clamps pages to two rows despite request of 999.
        rows=[{'bidNtceNo':bid,'bidNtceOrd':'000','lcnsLmtNm':'소프트웨어사업자',
               'permsnIndstrytyList':'1468'},
              {'bidNtceNo':other,'bidNtceOrd':'000','lcnsLmtNm':'시설업',
               'permsnIndstrytyList':'9999'},
              {'bidNtceNo':bid,'bidNtceOrd':'000','lcnsLmtNm':'정보통신',
               'permsnIndstrytyList':'0045'}]
        rows=rows[(page-1)*2:page*2]
        total=3
    elif source=='regionalIncentives':
        rows=[{'bidNtceNo':bid,'bidNtceOrd':'000','incentive':'official'}]
        total=1
    else:rows=[];total=0
    return {'ok':True,'source':source,'page':page,'totalCount':total,
            'rawCount':len(rows),'items':rows}

with tempfile.TemporaryDirectory() as folder:
    db=mod.connect(str(Path(folder)/'bid.sqlite3'))
    db.executescript("""
      CREATE TABLE bid_notices(
        bid_no TEXT,bid_ord TEXT,payload TEXT,kind TEXT,sw_candidate INTEGER
      );
      CREATE TABLE bid_license_cache(
        bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,
        payload TEXT NOT NULL,checked_at TEXT NOT NULL,
        PRIMARY KEY(bid_no,bid_ord)
      );
      CREATE TABLE bid_extra_cache(
        bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,
        payload TEXT NOT NULL,checked_at TEXT NOT NULL,
        PRIMARY KEY(bid_no,bid_ord)
      );
    """)
    dashes=dt.datetime.strptime(day,'%Y%m%d').date().isoformat()
    db.execute("INSERT INTO bid_notices VALUES (?,?,?,'servc',1)",
               (bid,'000',json.dumps({'posted':dashes,'closes':'2099-12-31'})))
    db.execute("INSERT INTO bid_notices VALUES (?,?,?,'servc',1)",
               ('R26BK11111111','000',
                json.dumps({'posted':dashes,'closes':'2099-12-31'})))
    db.commit()
    # A first interrupted pass does not mark the window complete.
    partial,requests=mod.collected_source(db,day,'license',fake,limit=1)
    assert partial is None and requests==1,(partial,requests)
    assert db.execute("SELECT COUNT(*) FROM mandatory_batch_windows").fetchone()[0]==0
    state=mod.run_once(db,fake)
    assert state['status']=='complete' and state['calls']==5,state
    assert calls.count(('license',1))==1,calls
    assert calls.count(('license',2))==1,calls
    assert len(calls)==6,calls  # 1 partial + 1 license resume + 3 other sources + one? 
    cached=db.execute("SELECT payload FROM bid_license_cache WHERE bid_no=?",(bid,)).fetchone()
    assert cached, 'verified license row missing'
    value=json.loads(cached[0])
    assert value['complete'] is True and value['count']==2,value
    assert set(value['requirements'][0]['codes'])=={'1468'}
    missing=db.execute("SELECT payload FROM bid_license_cache WHERE bid_no=?",('R26BK11111111',)).fetchone()
    assert missing is None,'no date batch row cannot assert no requirement'
    extra=json.loads(db.execute("SELECT payload FROM bid_extra_cache WHERE bid_no=?",(bid,)).fetchone()[0])
    assert extra['complete'] is False and extra['sources']['regionalIncentives']['complete'] is True,extra
    assert extra['sources']['serviceProducts']['state']=='not_returned_for_date'
    assert db.execute("SELECT COUNT(*) FROM mandatory_batch_windows").fetchone()[0]==4
    again=mod.run_once(db,fake)
    assert again['calls']==0 and len(calls)==6,(again,calls)
    # A prior confirmed source is preserved when another date has no row.
    old_source={'ok':True,'complete':True,'items':[{'some':'verified'}],
                'totalCount':1}
    older={**extra,'sources':{**extra['sources'],
            'serviceProducts':old_source}}
    db.execute("UPDATE bid_extra_cache SET payload=? WHERE bid_no=?",
               (json.dumps(older),bid));db.commit()
    mod.save_extra(db,day,{'serviceProducts':[],'mandatoryJointRegion':[],
                           'regionalIncentives':[{'bidNtceNo':bid,'bidNtceOrd':'000'}]},
                   {(bid,'000')})
    saved=json.loads(db.execute("SELECT payload FROM bid_extra_cache WHERE bid_no=?",(bid,)).fetchone()[0])
    assert saved['sources']['serviceProducts']==old_source
    db.close()
print('MANDATORY_FOUR_DATE_BATCH_PAGINATION_CACHE_UNKNOWN=PASS',flush=True)
