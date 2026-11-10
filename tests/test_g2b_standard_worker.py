#!/usr/bin/env python3
"""Offline regression for quota-bounded, source-exact WorkLinks B1/B2/B3 sync."""
import importlib.util
import os
import sqlite3
import tempfile
from pathlib import Path

SRC = ("/app/g2b-standard-worker.py" if os.path.isfile("/app/g2b-standard-worker.py")
       else str(Path(__file__).resolve().parents[1] / "server/g2b-standard-worker.py"))
spec = importlib.util.spec_from_file_location("stdworker", SRC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

assert set(m.OPERATIONS) == {"B1", "B2", "B3"}
assert m.PAGE_ROWS == 999
assert m.params("B2", "20261109")["opengBgnDt"] == "202611090000"
assert m.params("B3", "20261109")["cntrctCnclsBgnDate"] == "20261109"

bidno = "R26BK01806517"
other = "R26BK01806518"
rows = {
    "B1": [{
        "bidNtceNo": bidno, "bidNtceOrd": "000", "bidNtceNm": "공공 홈페이지 운영",
        "cntrctCnclsMthdNm": "제한경쟁", "bidwinrDcsnMthdNm": "협상에 의한 계약"}],
    "B2": [
        {"bidNtceNo": bidno, "bidNtceOrd": "000", "bidprcCorpBizrno": "1112233333",
         "fnlSucsfCorpBizrno": "1112233333", "fnlSucsfCorpNm": "정상낙찰사",
         "fnlSucsfAmt": "100000000", "fnlSucsfRt": "91.5",
         "fnlSucsfDate": "2026-11-09"},
        {"bidNtceNo": bidno, "bidNtceOrd": "000", "bidprcCorpBizrno": "2223344444",
         "fnlSucsfCorpBizrno": "1112233333", "fnlSucsfCorpNm": "정상낙찰사",
         "fnlSucsfAmt": "100000000", "fnlSucsfRt": "91.5", "fnlSucsfDate": "2026-11-09"},
    ],
    "B3": [
        {"cntrctNo": "R26CT1001", "cntrctOrd": "000", "bidNtceNo": bidno,
         "rprsntCorpBizrno": "1112233333", "rprsntCorpNm": "정상낙찰사",
         "cntrctAmt": "100000000", "cntrctCnclsDate": "2026-11-09"},
        {"cntrctNo": "R26CT1002", "cntrctOrd": "000", "bidNtceNo": "",
         "rprsntCorpBizrno": "2223344444", "cntrctAmt": "90000000"}
    ]
}

def fetch(service, day, page, query):
    assert page == 1 and query["serviceKey"] == "mock"
    assert query["numOfRows"] == 999
    if service == "B2":
        assert len(query["opengBgnDt"]) == 12
        assert query["bsnsDivCd"] == "5"
    return {"response": {"header": {"resultCode": "00"}, "body": {
        "items": rows[service], "totalCount": len(rows[service])}}}

with tempfile.TemporaryDirectory() as work:
    path = os.path.join(work, "std.sqlite3")
    assert m.run(days=1, max_requests=20, fetch=fetch, db_path=path, key="mock") == 0
    db = sqlite3.connect(path)
    assert db.execute("SELECT COUNT(*) FROM std_windows").fetchone()[0] == 3
    a = db.execute("""SELECT identified_bidders,all_bidders_identified,winner_bizno,
                             winner_amount,winner_conflict,sample_rows
                      FROM std_awards WHERE bid_no=?""", (bidno,)).fetchone()
    assert a == (2, 1, "1112233333", 100000000, 0, 2), a
    assert db.execute("SELECT COUNT(*) FROM std_contracts WHERE bid_no=?", (bidno,)).fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM std_contracts").fetchone()[0] == 1
    assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    db.close()

    def should_not_call(*args):
        raise AssertionError("duplicate completed window must be skipped")
    assert m.run(days=1, max_requests=20, fetch=should_not_call, db_path=path, key="mock") == 0

    def broken(service, day, page, query):
        if service == "B2":
            raise m.ProviderFailure("upstream_http_429", limited=True)
        return fetch(service, day, page, query)
    newer = os.path.join(work, "rate-limited.sqlite3")
    assert m.run(days=1, max_requests=20, fetch=broken, db_path=newer, key="mock") == 2
    db = sqlite3.connect(newer)
    assert db.execute("SELECT COUNT(*) FROM std_windows").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM std_awards").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM std_contracts").fetchone()[0] == 0
    db.close()

bad = list(rows["B2"])
bad.append({**rows["B2"][0], "fnlSucsfCorpBizrno": "2223344444",
            "fnlSucsfCorpNm": "다른 낙찰사"})
parsed = m.normalize_awards(bad, "20261109")
assert parsed[0][7] == "" and parsed[0][12] == 1
assert m.normalize_awards([{"bidNtceNo": other}], "20261109")[0][5] is None
print("WORKLINKS_G2B_STANDARD_OFFLINE_REGRESSION=PASS")
