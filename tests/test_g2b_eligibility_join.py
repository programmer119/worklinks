"""Local regression: cached notice ordinal '000' must join DB ordinal '0'.

Run: python3 tests/test_g2b_eligibility_join.py
Uses only temporary SQLite, never touches production DB or credentials.
"""
import datetime
import json
import os
import pathlib
import runpy
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="worklinks-g2b-") as tmp:
    old = os.environ.get("G2B_DB_PATH")
    os.environ["G2B_DB_PATH"] = os.path.join(tmp, "bids.sqlite3")
    try:
        api = runpy.run_path(str(ROOT / "server" / "g2b-proxy.py"), run_name="regression_test")
        bids = [
            {"kind": "servc", "bidNo": "R26BK12345678", "order": "0",
             "title": "공공 정보시스템 구축", "posted": "202610120800", "closes": "202610151700"},
            {"kind": "servc", "bidNo": "R26BK12345679", "order": "001",
             "title": "AI 데이터 시스템 개발", "posted": "202610120800", "closes": "202610161700"},
        ]
        assert api["persist_bids"](bids)["storedTotal"] == 2
        db = api["open_bid_db"]()
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result = {"ok": True, "complete": True, "requirements": [
                {"name": "컴퓨터관련서비스사업", "codes": ["1468"], "logic": "AND"}]}
            with db:
                db.executemany(
                    "INSERT INTO bid_license_cache (bid_no,bid_ord,payload,checked_at) VALUES (?,?,?,?)",
                    [(n, order, json.dumps(result), now) for n, order in
                     [("R26BK12345678", "000"), ("R26BK12345679", "001")]])
        finally:
            db.close()
        saved = api["query_saved_bids"](20, 0, True)
        assert saved["candidateTotal"] == 2, saved
        assert saved["eligibilityChecked"] == 2, saved
        assert saved["eligibilityLinked"] == 2, saved
        assert len(saved["items"]) == 2
        assert all(x.get("bidEligibility", {}).get("requirements") for x in saved["items"]), saved
        print("G2B_ELIGIBILITY_NORMALIZED_ORDINAL=PASS")
    finally:
        if old is None:
            os.environ.pop("G2B_DB_PATH", None)
        else:
            os.environ["G2B_DB_PATH"] = old
