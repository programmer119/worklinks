#!/usr/bin/env python3
"""No-network regression for quota-safe incremental G2B notice collection."""
import datetime as dt
import os
from pathlib import Path
import runpy
import tempfile

with tempfile.TemporaryDirectory(prefix='g2b-incremental-') as directory:
    os.environ['G2B_DB_PATH']=str(Path(directory)/'bids.sqlite3')
    mod=runpy.run_path(str(Path(__file__).resolve().parents[1]/
                           'server/g2b-full-crawler.py'),run_name='incremental_test')
    conn=mod['connect']()
    utc=dt.datetime.now(dt.timezone.utc)
    today=utc.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
    current=today.strftime('%Y%m%d')
    yesterday=(today-dt.timedelta(days=1)).strftime('%Y%m%d')
    old=(today-dt.timedelta(days=6)).strftime('%Y%m%d')
    due=mod['window_due']
    def set_window(kind,day,when):
        with conn:
            conn.execute('''INSERT OR REPLACE INTO crawl_windows
                (kind,day,expected,received,pages,checked_at)
                VALUES(?,?,?,?,?,?)''',(kind,day,1,1,1,when.isoformat()))
    set_window('servc',current,utc)
    assert not due(conn,'servc',current,today,utc),'current-day reread without interval'
    assert due(conn,'servc',current,today,utc+dt.timedelta(hours=2))
    assert due(conn,'thng',current,today,utc),'a missing window must be retried'
    set_window('servc',yesterday,utc-dt.timedelta(hours=20))
    assert not due(conn,'servc',yesterday,today,utc),'yesterday reread hourly'
    assert due(conn,'servc',yesterday,today,utc+dt.timedelta(hours=5))
    set_window('servc',old,utc-dt.timedelta(days=30))
    assert not due(conn,'servc',old,today,utc),'completed backfill reread'
    assert due(conn,'cnstwk',old,today,utc),'failed historical window lost'
    bid={'kind':'servc','bidNo':'R26BK00000042','order':'000',
         'title':'정보시스템 유지관리','closes':(today+dt.timedelta(days=4)).isoformat()}
    mod['save'](conn,[bid])
    def revision():
        return conn.execute("SELECT changed_at FROM bid_notices WHERE bid_no=?",
                            (bid['bidNo'],)).fetchone()[0]
    assert revision()=='','new notice must not look like a changed notice'
    mod['save'](conn,[bid])
    assert revision()=='','unchanged notice invalidated cache'
    updated={**bid,'title':'정보시스템 유지관리 정정 공고'}
    mod['save'](conn,[updated])
    assert revision(),'changed notice did not invalidate completed source evidence'
    conn.close()
    print('G2B_INCREMENTAL_WINDOW_AND_SOURCE_REVISION_NO_NETWORK=PASS')
