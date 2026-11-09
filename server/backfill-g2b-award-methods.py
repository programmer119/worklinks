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
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

SOURCE = os.environ.get('G2B_CRAWLER_SOURCE', '/app/g2b-full-crawler.py')
LIMIT_WINDOWS = max(1, min(16, int(os.environ.get('G2B_METHOD_REPAIR_WINDOWS', '8'))))
MAX_PAGES = max(1, min(40, int(os.environ.get('G2B_METHOD_REPAIR_PAGE_LIMIT', '18'))))
MAX_AGE_DAYS = max(7, min(120, int(os.environ.get('G2B_METHOD_REPAIR_AGE_DAYS', '75'))))
PINNED = ('R26BK01777538', 'R26BK01765541', 'R26BK01807134', 'R26BK01797629')

def stamp_day(value):
    m = re.search(r'(20\d{2})[-./]?(\d{2})[-./]?(\d{2})', str(value or ''))
    return ''.join(m.groups()) if m else ''


def refresh_exact_notice(db, key, crawler, bid_no):
    """One official API lookup for an existing visible notice, no document parsing."""
    operation = 'getBidPblancListInfoServc'
    params = {'serviceKey': key, 'type': 'json', 'pageNo': 1,
              'numOfRows': 10, 'inqryDiv': 2, 'bidNtceNo': bid_no}
    url = crawler['API_ROOT'] + '/' + operation + '?' + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            'Accept': 'application/json', 'User-Agent': 'WorkLinksMethodRepair/1.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            doc = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise RuntimeError('official_api_http_' + str(exc.code)) from None
    except (OSError, ValueError, UnicodeError):
        raise RuntimeError('official_api_unreachable_or_invalid_json') from None
    response = doc.get('response', {})
    result_code = str(response.get('header', {}).get('resultCode', 'missing'))
    if result_code not in ('0', '00'):
        raise RuntimeError('official_api_result_' + re.sub(r'[^0-9A-Za-z]', '', result_code)[:12])
    items = response.get('body', {}).get('items') or []
    if isinstance(items, dict):
        items = items.get('item') or []
    if not isinstance(items, list):
        items = [items]
    for item in items:
        if str(item.get('bidNtceNo') or '') != bid_no:
            continue
        if not str(item.get('sucsfbidMthdNm') or item.get('sucsfbidMthdCd') or '').strip():
            print('REPAIR_SINGLE_OFFICIAL_METHOD_EMPTY',bid_no,flush=True)
            return False
        # Only update a matching source-backed notice; no fallbacks or guesses.
        compact = crawler['compact'](item, 'servc')
        if compact.get('bidNo') != bid_no:
            raise RuntimeError('official_identity_mismatch')
        crawler['save'](db,[compact])
        print('REPAIR_SINGLE_UPDATED',bid_no,'method',repr(compact.get('awardMethod','')),
              'code',repr(compact.get('awardMethodCode','')),flush=True)
        return True
    print('REPAIR_SINGLE_NOT_FOUND',bid_no,flush=True)
    return False

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
    # outage. Limit retries to at most once per 30-minute check.
    last_failed = db.execute(
        "SELECT checked_at,note FROM award_method_repair_windows "
        "WHERE status='failed' ORDER BY checked_at DESC LIMIT 1").fetchone()
    if last_failed:
        try:
            checked_at = dt.datetime.fromisoformat(last_failed[0])
            if (dt.datetime.now(dt.timezone.utc) - checked_at).total_seconds() < 1800:
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
    # Fix currently visible stale notices first with a single call each.
    # Use day-window replay only afterward to replenish the rest of the corpus.
    for notice in PINNED:
        row = db.execute(
          "SELECT payload FROM bid_notices WHERE kind='servc' AND bid_no=? "
          "ORDER BY last_seen DESC LIMIT 1", (notice,)).fetchone()
        if not row:
            continue
        original = json.loads(row[0])
        if str(original.get('awardMethod') or '').strip():
            continue
        single_status = db.execute(
            "SELECT checked_at,status FROM award_method_repair_windows "
            "WHERE kind='servc' AND day=?", ('single-'+notice,)).fetchone()
        if single_status and single_status[1]=='complete':
            try:
                if (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(single_status[0])).total_seconds() < 86400:
                    print('REPAIR_SINGLE_OFFICIAL_CHECK_RECENT',notice,flush=True)
                    continue
            except (TypeError,ValueError):
                pass
        try:
            updated=refresh_exact_notice(db,key,crawler,notice)
            if not updated:
                with db:
                    db.execute('INSERT OR REPLACE INTO award_method_repair_windows '
                      '(kind,day,checked_at,status,note) VALUES (?,?,?,?,?)',
                      ('servc','single-'+notice,dt.datetime.now(dt.timezone.utc).isoformat(),
                       'complete','official_method_missing_or_not_found'))
        except RuntimeError as exc:
            print('REPAIR_SINGLE_FAILED', notice, str(exc)[:90],flush=True)
            with db:
                db.execute('INSERT OR REPLACE INTO award_method_repair_windows '
                 '(kind,day,checked_at,status,note) VALUES (?,?,?,?,?)',
                 ('servc','single-'+notice,dt.datetime.now(dt.timezone.utc).isoformat(),
                  'failed',str(exc)[:90]))
            if '429' in str(exc) or 'LIMIT' in str(exc).upper():
                print('REPAIR_UPSTREAM_QUOTA_STOP',flush=True)
                db.close()
                return
        time.sleep(0.5)
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
