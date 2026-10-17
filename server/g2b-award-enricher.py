#!/usr/bin/env python3
"""WorkLinks official historical awards: quota-bounded, restart-safe enrichment.

Runs in its OWN Docker container, talks to the existing localhost:18192 API,
and never handles an upstream service key. A missing/failed award stays UNKNOWN.
Only exact verified historical notice numbers are requested or stored.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DB = os.environ.get('G2B_DB_PATH', '/app/data/bids.sqlite3')
SNAPSHOT = os.environ.get('G2B_AWARD_SEED_PATH', '/app/official-awards-snapshot.json')
LOCAL_API = 'http://127.0.0.1:18192/api/g2b'
MAX_REQUESTS = min(3, max(1, int(os.environ.get('AWARD_MAX_REQUESTS_PER_CYCLE', '2'))))
INTERVAL = max(3600, int(os.environ.get('AWARD_INTERVAL_SECONDS', '3600')))
GAP_SECONDS = max(6, float(os.environ.get('AWARD_REQUEST_GAP_SECONDS', '12')))
FRESH_DAYS = 30
NO_DATA_RETRY_HOURS = 72
NOTICE = re.compile(r'^[A-Za-z0-9-]{8,40}$')
BIZNO = re.compile(r'^\d{10}$')
SOURCE = '나라장터 낙찰정보서비스'


class RemoteError(Exception):
    def __init__(self, reason, rate_limited=False):
        self.reason, self.rate_limited = reason, rate_limited
        super().__init__(reason)


def stamp(now=None):
    return (now or dt.datetime.now(dt.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_time(text):
    try:
        return dt.datetime.fromisoformat(str(text).replace('Z', '+00:00')).astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def init(db):
    db.execute('PRAGMA busy_timeout=30000')
    # Additive tables; do not edit existing bid_notices, recurring_projects,
    # crawler, license or any other service tables.
    db.execute('''CREATE TABLE IF NOT EXISTS bid_award_cache(
      bid_no TEXT PRIMARY KEY, payload TEXT NOT NULL, checked_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS bid_award_attempts(
      bid_no TEXT PRIMARY KEY, reason TEXT NOT NULL, retry_after TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS bid_award_worker_status(
      id INTEGER PRIMARY KEY CHECK(id=1), last_run TEXT, last_success TEXT,
      requests_last_run INTEGER NOT NULL DEFAULT 0,
      stored_last_run INTEGER NOT NULL DEFAULT 0,
      errors_last_run INTEGER NOT NULL DEFAULT 0,
      cooldown_until TEXT, message TEXT)''')
    db.commit()


def valid_record(item):
    if not isinstance(item, dict) or not NOTICE.fullmatch(str(item.get('bidNo') or '')):
        return None
    count = item.get('count')
    if type(count) is not int or not 1 <= count <= 1000000:
        return None
    biz = str(item.get('winnerBizno') or '')
    if biz and not BIZNO.fullmatch(biz):
        return None
    winner = str(item.get('winner') or '')
    if len(winner) > 100:
        return None
    amount, rate = item.get('amount'), item.get('rate')
    if amount is not None and (type(amount) is not int or not 0 < amount <= 10**15):
        return None
    if rate is not None and (type(rate) not in (float, int) or not 0 < rate <= 100):
        return None
    checked = parse_time(item.get('verifiedAt'))
    if not checked:
        return None
    return dict(bidNo=item['bidNo'], count=count, amount=amount, rate=rate,
                winner=winner, winnerBizno=biz, date=str(item.get('date') or '')[:24],
                verifiedAt=stamp(checked))


def seed_existing_official_snapshot(db, path=SNAPSHOT):
    """Reuse audited public records ONCE, never bump their verification times."""
    try:
        with open(path, encoding='utf-8') as fd:
            source = json.load(fd)
    except (OSError, ValueError):
        return 0
    if not isinstance(source, dict) or source.get('schemaVersion') != 1 or source.get('source') != SOURCE:
        return 0
    saved = 0
    for record in source.get('records', [])[:200]:
        row = dict(record)
        row.setdefault('verifiedAt', source.get('verifiedAt'))
        row = valid_record(row)
        if not row:
            continue
        with db:
            cur = db.execute('INSERT OR IGNORE INTO bid_award_cache(bid_no,payload,checked_at) VALUES(?,?,?)',
                             (row['bidNo'], json.dumps(row, ensure_ascii=False), row['verifiedAt']))
            saved += cur.rowcount
    return saved


def as_award(bid_no, response, now=None):
    """Return verified positive historical award ONLY, never a fabricated 0."""
    if response.get('ok') is not True:
        raise RemoteError('upstream_failure',
            '429' in str(response.get('error', '')) or 'rate_limited' in str(response.get('error', '')))
    items = response.get('items')
    if not isinstance(items, list):
        raise RemoteError('malformed_award_response')
    official = [x for x in items if isinstance(x, dict) and str(x.get('bidNtceNo') or '') == bid_no]
    if not official:
        return None
    if int(response.get('totalCount') or 0) > len(items):
        raise RemoteError('incomplete_award_page')
    parsed = []
    for row in official:
        raw = str(row.get('prtcptCnum') or '').strip()
        if not re.fullmatch(r'\d{1,7}', raw) or not 1 <= int(raw) <= 1000000:
            raise RemoteError('bidder_count_unverified')
        biz = re.sub(r'\D', '', str(row.get('bidwinnrBizno') or ''))
        if biz and not BIZNO.fullmatch(biz):
            raise RemoteError('winner_business_id_unverified')
        rate_raw = str(row.get('sucsfbidRate') or '').strip().rstrip('%')
        amount_raw = str(row.get('sucsfbidAmt') or '').replace(',', '').strip()
        rate = float(rate_raw) if re.fullmatch(r'\d{1,3}(?:\.\d{1,5})?', rate_raw) and 0 < float(rate_raw) <= 100 else None
        amount = int(amount_raw) if re.fullmatch(r'\d{1,15}', amount_raw) and int(amount_raw) > 0 else None
        parsed.append(dict(bidNo=bid_no, count=int(raw), winner=str(row.get('bidwinnrNm') or '')[:100],
             winnerBizno=biz, rate=rate, amount=amount,
             date=str(row.get('fnlSucsfDate') or '')[:24], verifiedAt=stamp(now)))
    # Mixed winners/counts in one exact notice are not evidence of an incumbent.
    if len({(r['count'], r['winnerBizno']) for r in parsed}) > 1:
        raise RemoteError('ambiguous_notice_award')
    return valid_record(parsed[0])


def http_awards(bid_no):
    req = Request(LOCAL_API + '/awards?bidNo=' + quote(bid_no, safe=''),
                  headers={'Accept':'application/json', 'User-Agent':'WorkLinksAwardEnricher/1.0'})
    try:
        with urlopen(req, timeout=20) as res:
            result = json.load(res)
    except HTTPError as err:
        try:
            data = json.load(err)
            code = str(data.get('error', '')).lower()
        except (ValueError, TypeError):
            code = ''
        rate = err.code == 429 or '429' in code or 'rate_limited' in code or 'limited_number' in code
        raise RemoteError('rate_limited' if rate else 'internal_api_unavailable', rate)
    except (URLError, ValueError, OSError) as exc:
        raise RemoteError('internal_api_unavailable')
    if not isinstance(result, dict):
        raise RemoteError('malformed_award_response')
    return as_award(bid_no, result)


def eligible_history_numbers(db, now=None):
    """Only exact, verified historic notices of ACTIVE recurring SW tenders."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        rows = db.execute('''SELECT b.payload, r.history_json FROM bid_notices b
          JOIN recurring_projects r ON b.kind=r.kind AND b.bid_no=r.bid_no
          WHERE b.kind='servc' AND b.sw_candidate=1 AND r.repeat_years>=2
          ORDER BY b.last_seen DESC LIMIT 2500''').fetchall()
    except sqlite3.OperationalError:
        return []
    choices = {}
    for raw, series in rows:
        try:
            current = json.loads(raw)
            history = json.loads(series)
        except (ValueError, TypeError):
            continue
        if not isinstance(history, list):
            continue
        close = parse_time(current.get('closes'))
        # An explicit closed notice must not consume official API quota.
        if close and close < now:
            continue
        # If close is unknown, keep the candidate but place it after dated ones.
        urgency = (close - now).total_seconds() if close else 10**12
        yrs = set()
        for old in history[:6]:
            if not isinstance(old, dict) or old.get('verified') is not True:
                continue
            no = str(old.get('bidNo') or '')
            try: year = int(old.get('year') or 0)
            except (ValueError, TypeError): continue
            if not NOTICE.fullmatch(no) or year >= now.year or year in yrs:
                continue
            yrs.add(year)
            rank = (max(0, urgency), -year, no)
            if no not in choices or rank < choices[no]:
                choices[no] = rank
    return [notice for notice, _ in sorted(choices.items(), key=lambda v:v[1])]


def candidates(db, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    result = []
    for notice in eligible_history_numbers(db, now):
        cached = db.execute('SELECT checked_at FROM bid_award_cache WHERE bid_no=?', (notice,)).fetchone()
        if cached:
            checked = parse_time(cached[0])
            if checked and now - checked < dt.timedelta(days=FRESH_DAYS):
                continue
        attempted = db.execute('SELECT retry_after FROM bid_award_attempts WHERE bid_no=?', (notice,)).fetchone()
        if attempted:
            retry = parse_time(attempted[0])
            if retry and retry > now:
                continue
        result.append(notice)
    return result


def write_status(db, when, requests, stored, errors, msg, cooldown=None):
    with db:
        db.execute('''INSERT INTO bid_award_worker_status
         (id,last_run,last_success,requests_last_run,stored_last_run,errors_last_run,cooldown_until,message)
         VALUES (1,?,?,?,?,?,?,?)
         ON CONFLICT(id) DO UPDATE SET last_run=excluded.last_run,
          last_success=COALESCE(excluded.last_success,bid_award_worker_status.last_success),
          requests_last_run=excluded.requests_last_run,stored_last_run=excluded.stored_last_run,
          errors_last_run=excluded.errors_last_run,cooldown_until=excluded.cooldown_until,
          message=excluded.message''',
         (stamp(when), stamp(when) if stored else None, requests, stored, errors,
          stamp(cooldown) if cooldown else None, msg))


def cycle(db, fetch=http_awards, now=None, maximum=MAX_REQUESTS, gap=GAP_SECONDS):
    now = now or dt.datetime.now(dt.timezone.utc)
    paused = db.execute('SELECT cooldown_until FROM bid_award_worker_status WHERE id=1').fetchone()
    if paused and parse_time(paused[0]) and parse_time(paused[0]) > now:
        return {'requests':0,'stored':0,'errors':0,'state':'cooldown'}
    requests = stored = errors = 0
    state = 'idle'
    for no in candidates(db, now)[:max(0, min(int(maximum), 3))]:
        if requests and gap:
            time.sleep(gap)
        requests += 1
        try:
            result = fetch(no)
        except RemoteError as exc:
            errors += 1
            rate = exc.rate_limited
            delay = dt.timedelta(minutes=75) if rate else dt.timedelta(hours=24)
            with db:
                db.execute('INSERT OR REPLACE INTO bid_award_attempts VALUES(?,?,?)',
                           (no, exc.reason, stamp(now + delay)))
            state = 'rate_limited' if rate else 'upstream_error'
            if rate:
                break
            continue
        if result is None:
            with db:
                db.execute('INSERT OR REPLACE INTO bid_award_attempts VALUES(?,?,?)',
                           (no, 'no_verified_award', stamp(now + dt.timedelta(hours=NO_DATA_RETRY_HOURS))))
            state = 'unknown_award'
            continue
        checked = valid_record(result)
        if checked is None or checked['bidNo'] != no:
            errors += 1
            state = 'malformed_verified_award'
            continue
        with db:
            db.execute('INSERT OR REPLACE INTO bid_award_cache VALUES(?,?,?)',
                       (no, json.dumps(checked, ensure_ascii=False), checked['verifiedAt']))
            db.execute('DELETE FROM bid_award_attempts WHERE bid_no=?', (no,))
        stored += 1
        state = 'verified_award'
    cooldown = now + dt.timedelta(minutes=75) if state == 'rate_limited' else None
    write_status(db, now, requests, stored, errors, state, cooldown)
    return {'requests':requests,'stored':stored,'errors':errors,'state':state}


def main():
    conn = sqlite3.connect(DB, timeout=30)
    init(conn)
    seeded = seed_existing_official_snapshot(conn)
    print('AWARD_ENRICHER_SEEDED', seeded, flush=True)
    while True:
        try:
            result = cycle(conn)
            print('AWARD_ENRICHER_CYCLE', json.dumps(result), flush=True)
        except (sqlite3.Error, ValueError, OSError) as exc:
            # No uncontrolled burst on failures; Docker auto-restarts after crashes.
            print('AWARD_ENRICHER_CYCLE_ERROR', type(exc).__name__, flush=True)
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
