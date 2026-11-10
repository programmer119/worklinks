#!/usr/bin/env python3
"""WorkLinks B1/B2/B3 daily standard-service collection (separate from A02).

Three completely independent official datasets. Fetch complete 1-day windows
before committing; record only source-backed facts, never invent a winner,
contract performance or a zero-bidder conclusion. No upstream key in logs.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KST = dt.timezone(dt.timedelta(hours=9))
ROOT = "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService/"
DB_PATH = os.environ.get("G2B_STANDARD_DB", "/app/data/g2b-standard.sqlite3")
SECRET_PATH = os.environ.get("G2B_STANDARD_KEY_PATH", "/run/secrets/g2b-standard.env")
PAGE_ROWS = 999
MAX_PAGES = 25
OPERATIONS = {
    "B1": "getDataSetOpnStdBidPblancInfo",
    "B2": "getDataSetOpnStdScsbidInfo",
    "B3": "getDataSetOpnStdCntrctInfo",
}
NOTICE = re.compile(r"^[A-Za-z0-9-]{8,40}$")
BIZNO = re.compile(r"^\d{10}$")


class ProviderFailure(Exception):
    def __init__(self, reason, limited=False):
        super().__init__(reason)
        self.reason = reason
        self.limited = limited


def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def get_key(path=SECRET_PATH):
    with open(path, encoding="utf-8") as handle:
        found = [line.split("=", 1)[1].strip().strip('"\x27')
                 for line in handle if line.startswith("G2B_STANDARD_SERVICE_KEY=")]
    if len(found) != 1 or not found[0]:
        raise RuntimeError("standard_key_missing")
    return found[0]


def ordinal(value):
    s = str(value or "000").strip()
    return s.zfill(3) if s.isdigit() else s[:12]


def clean(value, maxlen=180):
    return str(value or "").strip()[:maxlen]


def valid_notice(value):
    value = clean(value, 40)
    return value if NOTICE.fullmatch(value) else ""


def valid_biz(value):
    value = re.sub(r"\D", "", str(value or ""))
    return value if BIZNO.fullmatch(value) else ""


def money(value):
    raw = str(value or "").replace(",", "").strip()
    return int(raw) if raw.isdigit() and 0 < int(raw) <= 10**15 else None


def percentage(value):
    raw = str(value or "").replace("%", "").strip()
    try:
        result = float(raw)
        return result if 0 < result <= 100 else None
    except (ValueError, TypeError):
        return None


def params(service, day):
    common = {"pageNo": 1, "numOfRows": PAGE_ROWS}
    if service == "B1":
        return dict(common, bidNtceBgnDt=day + "0000", bidNtceEndDt=day + "2359")
    if service == "B2":
        # The official B2 service requires a 12-digit datetime and a 1-day range.
        return dict(common, bsnsDivCd="5", opengBgnDt=day + "0000", opengEndDt=day + "2359")
    return dict(common, cntrctCnclsBgnDate=day, cntrctCnclsEndDate=day)


def request_page(service, day, page, key, fetch=None):
    query = dict(params(service, day), pageNo=page, serviceKey=key, type="json")
    url = ROOT + OPERATIONS[service] + "?" + urllib.parse.urlencode(query)
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json", "User-Agent": "WorkLinksStandardDaily/1.0"})
        if fetch is None:
            with urllib.request.urlopen(req, timeout=36) as r:
                doc = json.load(r)
        else:
            doc = fetch(service, day, page, query)
    except urllib.error.HTTPError as err:
        raise ProviderFailure("upstream_http_" + str(err.code), err.code == 429) from None
    except (OSError, ValueError, UnicodeError, TimeoutError):
        raise ProviderFailure("upstream_transport_or_json") from None
    if not isinstance(doc, dict):
        raise ProviderFailure("non_object_response")
    if "nkoneps.com.response.ResponseError" in doc:
        h = (doc["nkoneps.com.response.ResponseError"] or {}).get("header") or {}
        code = re.sub(r"\W", "", str(h.get("resultCode") or ""))[:15]
        raise ProviderFailure("provider_result_" + code)
    response = doc.get("response") or {}
    header = response.get("header") or {}
    if str(header.get("resultCode")) not in ("00", "0"):
        raise ProviderFailure("provider_result_" + re.sub(r"\W", "", str(header.get("resultCode")))[:15])
    body = response.get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if not isinstance(items, list):
        raise ProviderFailure("malformed_items")
    try:
        total = int(body.get("totalCount") or 0)
    except (TypeError, ValueError):
        raise ProviderFailure("invalid_total") from None
    if total < 0 or total > MAX_PAGES * PAGE_ROWS or len(items) > PAGE_ROWS:
        raise ProviderFailure("unbounded_window")
    return total, [x for x in items if isinstance(x, dict)]


def collect_window(service, day, key, budget, fetch=None):
    total, first = request_page(service, day, 1, key, fetch)
    budget[0] += 1
    pages = max(1, (total + PAGE_ROWS - 1) // PAGE_ROWS)
    if pages > MAX_PAGES:
        raise ProviderFailure("window_too_large")
    rows = list(first)
    for page in range(2, pages + 1):
        if budget[0] >= budget[1]:
            raise ProviderFailure("request_budget_exhausted")
        time.sleep(0.18 if fetch is None else 0)
        page_total, items = request_page(service, day, page, key, fetch)
        budget[0] += 1
        if page_total != total or not items:
            raise ProviderFailure("pagination_changed_or_empty")
        rows.extend(items)
    if len(rows) != total:
        raise ProviderFailure("incomplete_window")
    return rows, pages


def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path, timeout=25)
    db.execute("PRAGMA busy_timeout=25000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS std_windows(
      service TEXT NOT NULL, day TEXT NOT NULL, received INTEGER NOT NULL,
      pages INTEGER NOT NULL, refreshed_at TEXT NOT NULL,
      PRIMARY KEY(service,day));
    CREATE TABLE IF NOT EXISTS std_notices(
      bid_no TEXT NOT NULL, bid_ord TEXT NOT NULL, day TEXT NOT NULL,
      title TEXT, agency TEXT, contract_method TEXT, decision_method TEXT,
      PRIMARY KEY(bid_no,bid_ord,day));
    CREATE INDEX IF NOT EXISTS std_notices_by_bid ON std_notices(bid_no);
    CREATE TABLE IF NOT EXISTS std_awards(
      bid_no TEXT NOT NULL, bid_ord TEXT NOT NULL, day TEXT NOT NULL,
      title TEXT, division TEXT, identified_bidders INTEGER,
      all_bidders_identified INTEGER NOT NULL DEFAULT 0,
      winner_bizno TEXT, winner_name TEXT, winner_amount INTEGER,
      winner_rate REAL, winner_date TEXT, winner_conflict INTEGER NOT NULL DEFAULT 0,
      sample_rows INTEGER NOT NULL,
      PRIMARY KEY(bid_no,bid_ord,day));
    CREATE INDEX IF NOT EXISTS std_awards_by_bid ON std_awards(bid_no);
    CREATE TABLE IF NOT EXISTS std_contracts(
      contract_no TEXT NOT NULL, contract_ord TEXT NOT NULL, day TEXT NOT NULL,
      bid_no TEXT NOT NULL, bid_ord TEXT NOT NULL,
      contract_name TEXT, company TEXT, company_bizno TEXT,
      amount INTEGER, signed_date TEXT, conflict INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(contract_no,contract_ord,day));
    CREATE INDEX IF NOT EXISTS std_contracts_by_bid ON std_contracts(bid_no);
    CREATE TABLE IF NOT EXISTS std_run_status(
      id INTEGER PRIMARY KEY CHECK(id=1), last_run TEXT, last_success TEXT,
      requests INTEGER NOT NULL DEFAULT 0,
      windows INTEGER NOT NULL DEFAULT 0,
      message TEXT);
    INSERT OR IGNORE INTO std_run_status (id,requests,windows,message)
       VALUES(1,0,0,'initialized');
    """)
    return db


def normalize_notices(rows, day):
    result = []
    seen = set()
    for item in rows:
        no = valid_notice(item.get("bidNtceNo"))
        if not no:
            continue
        order = ordinal(item.get("bidNtceOrd"))
        key = (no, order, day)
        if key in seen:
            continue
        seen.add(key)
        result.append((no, order, day, clean(item.get("bidNtceNm"), 220),
                       clean(item.get("ntceInsttNm"), 150),
                       clean(item.get("cntrctCnclsMthdNm"), 120),
                       clean(item.get("bidwinrDcsnMthdNm"), 120)))
    return result


def normalize_awards(rows, day):
    grouped = collections.defaultdict(list)
    for item in rows:
        no = valid_notice(item.get("bidNtceNo"))
        if no:
            grouped[(no, ordinal(item.get("bidNtceOrd")))].append(item)
    output = []
    for (no, order), items in grouped.items():
        bidders = set()
        missing_bidder = False
        winners = {}
        for item in items:
            biz = valid_biz(item.get("bidprcCorpBizrno"))
            if biz:
                bidders.add(biz)
            else:
                missing_bidder = True
            won = valid_biz(item.get("fnlSucsfCorpBizrno"))
            won_date = clean(item.get("fnlSucsfDate"), 24)
            if won and won_date:
                fact = (clean(item.get("fnlSucsfCorpNm"), 150),
                        money(item.get("fnlSucsfAmt")),
                        percentage(item.get("fnlSucsfRt")), won_date)
                if won in winners and winners[won] != fact:
                    # Repeated official winner with conflicting amounts: do not guess.
                    winners[(won, len(winners))] = fact
                else:
                    winners[won] = fact
        verified = len(winners) == 1 and isinstance(next(iter(winners), None), str)
        winner_biz = next(iter(winners)) if verified else ""
        winner_data = winners.get(winner_biz) if verified else None
        first = items[0]
        output.append((
            no, order, day, clean(first.get("bidNtceNm"), 220),
            clean(first.get("bsnsDivNm"), 40),
            len(bidders) if bidders else None,
            int(bool(bidders) and not missing_bidder),
            winner_biz, winner_data[0] if winner_data else "",
            winner_data[1] if winner_data else None,
            winner_data[2] if winner_data else None,
            winner_data[3] if winner_data else "",
            int(len(winners) > 1), len(items)))
    return output


def normalize_contracts(rows, day):
    output = {}
    for item in rows:
        contract_no = clean(item.get("cntrctNo"), 70)
        no = valid_notice(item.get("bidNtceNo"))
        if not contract_no or not no:
            # Contracts without an explicit tender reference must not be linked.
            continue
        order = ordinal(item.get("cntrctOrd"))
        key = (contract_no, order, day)
        datum = (contract_no, order, day, no,
                 ordinal(item.get("bidNtceOrd")),
                 clean(item.get("cntrctNm"), 220),
                 clean(item.get("rprsntCorpNm"), 150),
                 valid_biz(item.get("rprsntCorpBizrno")),
                 money(item.get("cntrctAmt")),
                 clean(item.get("cntrctCnclsDate"), 24),
                 0)
        previous = output.get(key)
        if previous is not None and (previous[3] != no or previous[8] != datum[8]):
            output[key] = previous[:8] + (None, previous[9], 1)
        else:
            output[key] = datum
    return list(output.values())


def save_window(db, service, day, rows, pages):
    if service == "B1":
        values = normalize_notices(rows, day)
        table = "std_notices"
        insert = """INSERT OR REPLACE INTO std_notices
          (bid_no,bid_ord,day,title,agency,contract_method,decision_method)
          VALUES(?,?,?,?,?,?,?)"""
    elif service == "B2":
        values = normalize_awards(rows, day)
        table = "std_awards"
        insert = """INSERT OR REPLACE INTO std_awards
          (bid_no,bid_ord,day,title,division,identified_bidders,all_bidders_identified,
           winner_bizno,winner_name,winner_amount,winner_rate,winner_date,winner_conflict,sample_rows)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    else:
        values = normalize_contracts(rows, day)
        table = "std_contracts"
        insert = """INSERT OR REPLACE INTO std_contracts
          (contract_no,contract_ord,day,bid_no,bid_ord,contract_name,company,
           company_bizno,amount,signed_date,conflict)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)"""
    with db:
        db.execute("DELETE FROM " + table + " WHERE day=?", (day,))
        if values:
            db.executemany(insert, values)
        db.execute("""INSERT OR REPLACE INTO std_windows(service,day,received,pages,refreshed_at)
                      VALUES(?,?,?,?,?)""", (service, day, len(rows), pages, now_utc()))
    return len(values)


def run(days=2, max_requests=90, fetch=None, db_path=DB_PATH, key=None):
    key = key or get_key()
    db = connect(db_path)
    budget = [0, int(max_requests)]
    windows_done = 0
    errors = []
    today = dt.datetime.now(KST).date()
    try:
        with db:
            db.execute("UPDATE std_run_status SET last_run=?,message=? WHERE id=1",
                       (now_utc(), "running"))
        # Always start with the latest *completed* KST day.
        for offset in range(1, int(days) + 1):
            day = (today - dt.timedelta(days=offset)).strftime("%Y%m%d")
            for service in ("B1", "B2", "B3"):
                exists = db.execute("SELECT received,refreshed_at FROM std_windows WHERE service=? AND day=?",
                                    (service, day)).fetchone()
                if exists:
                    try:
                        previous = dt.datetime.fromisoformat(exists[1].replace("Z", "+00:00"))
                        fresh = dt.datetime.now(dt.timezone.utc) - previous < dt.timedelta(hours=12)
                    except (TypeError,ValueError):
                        fresh = False
                    if fresh:
                        print("STD_WINDOW_ALREADY_FRESH " + service + " " + day, flush=True)
                        continue
                if budget[0] >= budget[1]:
                    errors.append("request_budget_exhausted")
                    break
                try:
                    rows, pages = collect_window(service, day, key, budget, fetch)
                    count = save_window(db, service, day, rows, pages)
                    windows_done += 1
                    print("STD_WINDOW_OK " + json.dumps({
                        "service": service, "day": day,
                        "official_rows": len(rows), "stored_records": count,
                        "pages": pages, "requests": budget[0],
                        "full_window": True}, ensure_ascii=False), flush=True)
                except ProviderFailure as exc:
                    errors.append(service + ":" + day + ":" + exc.reason)
                    print("STD_WINDOW_FAILED " + service + " " + day + " " + exc.reason, flush=True)
                    if exc.limited or exc.reason == "request_budget_exhausted":
                        break
            if errors:
                # Fail closed without moving on to fresh API windows after errors.
                break
        outcome = "completed" if not errors else "partial:" + errors[0]
        with db:
            db.execute("""UPDATE std_run_status SET last_success=CASE WHEN ? THEN ? ELSE last_success END,
               requests=?, windows=?, message=? WHERE id=1""",
                       (int(not errors), now_utc(), budget[0], windows_done, outcome))
        totals = {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                  for table in ("std_windows", "std_notices", "std_awards", "std_contracts")}
        print("STD_SYNC_FINAL " + json.dumps({
            "status": outcome, "requests": budget[0],
            "new_windows": windows_done, "tables": totals,
            "errors": errors[:3]}, ensure_ascii=False), flush=True)
        return 0 if not errors else 2
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-requests", type=int, default=90)
    arg = parser.parse_args()
    if not (1 <= arg.days <= 7 and 3 <= arg.max_requests <= 150):
        raise SystemExit("invalid_bounds")
    try:
        sys.exit(run(days=arg.days, max_requests=arg.max_requests))
    except (OSError, ValueError, sqlite3.Error) as exc:
        print("STD_SYNC_FATAL " + type(exc).__name__, flush=True)
        sys.exit(3)
