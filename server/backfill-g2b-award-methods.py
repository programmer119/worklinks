#!/usr/bin/env python3
"""Bounded one-time repair of missing award-method metadata on still-open G2B notices.

Reuses the existing official listing API and existing crawler compact()/save().
Never parses RFP documents and never fabricates missing API fields.
Runs in the isolated crawler Python container with a shared SQLite WAL database.
Successful day/kind windows are checkpointed to avoid repeated API calls.
"""
import datetime as dt
import json
import os
import re
import runpy
import sqlite3
import time
from collections import defaultdict

SOURCE = os.environ.get('G2B_CRAWLER_SOURCE', '/app/g2b-full-crawler.py')
LIMIT_WINDOWS = max(1, min(16, int(os.environ.get('G2B_METHOD_REPAIR_WINDOWS', '8'))))
MAX_PAGES = max(1, min(40, int(os.environ.get('G2B_METHOD_REPAIR_PAGE_LIMIT', '18'))))
MAX_AGE_DAYS = max(7, min(120, int(os.environ.get('G2B_METHOD_REPAIR_AGE_DAYS', '75'))))
PINNED = ('R26BK01777538', 'R26BK01765541', 'R26BK01807134', 'R26BK01797629')

def stamp_day(value):
    m = re.search(r'(20\d{2})[-./]?(\d{2})[-./]?(\d{2})', str(value or ''))
    return ''.join(m.groups()) if m else ''

def main():
    crawler = runpy.run_path(SOURCE, run_name='award_method_repair')
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    today = now.strftime('%Y%m%d')
    cutoff = (now - dt.timedelta(days=MAX_AGE_DAYS)).strftime('%Y%m%d')
    db = crawler['connect']()
    db.execute('CREATE TABLE IF NOT EXISTS award_method_repair_windows ('
               'kind TEXT NOT NULL, day TEXT NOT NULL, checked_at TEXT NOT NULL,'
               'status TEXT NOT NULL, note TEXT NOT NULL DEFAULT "",'
               'PRIMARY KEY(kind,day))')
    db.commit()
    # A transient provider failure can mean a shared daily quota or upstream
    # outage. Do not retry all missing windows every 30 minutes.
    last_failed = db.execute(
        "SELECT checked_at,note FROM award_method_repair_windows "
        "WHERE status='failed' ORDER BY checked_at DESC LIMIT 1").fetchone()
    if last_failed:
        try:
            checked_at = dt.datetime.fromisoformat(last_failed[0])
            if (dt.datetime.now(dt.timezone.utc) - checked_at).total_seconds() < 4 * 3600:
                print('REPAIR_PROVIDER_COOLDOWN',str(last_failed[1])[:100],flush=True)
                db.close()
                return
        except (TypeError, ValueError):
            pass
    grouped = defaultdict(list)
    rows = db.execute('SELECT kind,bid_no,bid_ord,payload FROM bid_notices WHERE sw_candidate=1').fetchall()
    checked = set((kind, day) for kind, day in db.execute(
        "SELECT kind,day FROM award_method_repair_windows WHERE status='complete'").fetchall())
    missing = 0
    for kind, bid_no, order, raw in rows:
        if kind not in crawler['OPERATIONS']:
            continue
        try: data = json.loads(raw)
        except (ValueError, TypeError): continue
        if str(data.get('awardMethod') or '').strip():
            continue
        post = stamp_day(data.get('posted'))
        close = stamp_day(data.get('closes'))
        if not post or not close or close < today or not cutoff <= post <= today:
            continue
        missing += 1
        grouped[(kind, post)].append((bid_no, close))
    work = []
    for (kind, day), bids in grouped.items():
        if (kind, day) in checked:
            continue
        stored = db.execute('SELECT pages FROM crawl_windows WHERE kind=? AND day=?',
                            (kind,day)).fetchone()
        pages = stored[0] if stored else 1
        # A very large day is not safe to recrawl under a bounded daily quota.
        if pages > MAX_PAGES:
            print('REPAIR_SKIPPED_LARGE_WINDOW', kind, day, 'pages', pages, flush=True)
            continue
        pinned = any(bid_no in PINNED for bid_no, _ in bids)
        urgent = min(close for _, close in bids)
        work.append((0 if pinned else 1, urgent, -len(bids), kind, day, pages))
    work.sort()
    print('REPAIR_PLAN', 'missing_open_sw_notices', missing, 'uncached_windows', len(work),
          'max_windows', LIMIT_WINDOWS, flush=True)
    if not work:
        db.close()
        return
    try: key = crawler['secret']()
    except (OSError, RuntimeError):
        db.close()
        raise
    started = time.monotonic()
    for _, urgent, num, kind, day, pages in work[:LIMIT_WINDOWS]:
        if time.monotonic() - started > 420:
            print('REPAIR_TIME_BUDGET_REACHED', flush=True)
            break
        print('REPAIR_BEGIN', kind, day, 'estimated_pages', pages, flush=True)
        try:
            processed = crawler['scan_day'](db,key,kind,day)
            with db:
                db.execute('INSERT OR REPLACE INTO award_method_repair_windows '
                    '(kind,day,checked_at,status,note) VALUES (?,?,?,?,?)',
                    (kind,day,dt.datetime.now(dt.timezone.utc).isoformat(),
                     'complete', 'api_rows='+str(processed)))
            print('REPAIR_DAY_COMPLETE',kind,day,'rows',processed,flush=True)
        except Exception as exc:
            # Failed windows remain retryable, but never log URLs or API secrets.
            reason = (type(exc).__name__ + ':' + str(exc))[:120]
            with db:
                db.execute('INSERT OR REPLACE INTO award_method_repair_windows '
                    '(kind,day,checked_at,status,note) VALUES (?,?,?,?,?)',
                    (kind,day,dt.datetime.now(dt.timezone.utc).isoformat(),
                     'failed', reason))
            print('REPAIR_DAY_FAILED',kind,day,reason,flush=True)
            if '429' in str(exc) or 'upstream' in str(exc).lower():
                print('REPAIR_STOP_ON_UPSTREAM_ERROR',flush=True)
                break
        time.sleep(0.5)
    for bid_no in PINNED:
        row = db.execute("SELECT payload FROM bid_notices WHERE bid_no=? AND kind='servc' "
                         "ORDER BY last_seen DESC LIMIT 1",(bid_no,)).fetchone()
        if not row:
            print('REPAIR_PINNED_NOT_FOUND',bid_no,flush=True)
            continue
        data = json.loads(row[0])
        print('REPAIR_PINNED_RESULT',bid_no,'contract',repr(data.get('contract','')),
            'award_method',repr(data.get('awardMethod','')),
            'award_code',repr(data.get('awardMethodCode','')),
            'floor_rate',repr(data.get('awardFloorRate','')),flush=True)
    db.close()

if __name__=='__main__':
    main()
