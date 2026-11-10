#!/usr/bin/env python3
"""B1-B3 API is read-only, exact-bid joined, and never claims performance completion."""
import os
import runpy
import tempfile
from pathlib import Path

API = "/app/api.py" if os.path.isfile("/app/api.py") else str(
    Path(__file__).resolve().parents[1] / "server/g2b-proxy.py")
WORKER = "/app/g2b-standard-worker.py" if os.path.isfile("/app/g2b-standard-worker.py") else str(
    Path(__file__).resolve().parents[1] / "server/g2b-standard-worker.py")
api = runpy.run_path(API,run_name="read_only_standard_regression")
worker = runpy.run_path(WORKER,run_name="standard_worker_regression")
g = api["standard_bid_evidence"].__globals__
original = g["G2B_STD_DB_PATH"]
with tempfile.TemporaryDirectory() as tmp:
    g["G2B_STD_DB_PATH"] = os.path.join(tmp, "standard.sqlite3")
    assert api["standard_sync_status"]()["installed"] is False
    assert api["standard_bid_evidence"]("R26BK01806517")["installed"] is False
    try:
        api["standard_bid_evidence"]("!UNSAFE")
    except api["ApiError"] as e:
        assert e.status == 400
    else:
        raise AssertionError("unsanitized notice identifier accepted")
    db = worker["connect"](g["G2B_STD_DB_PATH"])
    bid = "R26BK01806517"
    with db:
        db.execute("INSERT INTO std_windows VALUES('B1','20261109',1,1,'2026-11-10T01:00:00Z')")
        db.execute("INSERT INTO std_windows VALUES('B2','20261109',2,1,'2026-11-10T01:00:00Z')")
        db.execute("INSERT INTO std_windows VALUES('B3','20261109',1,1,'2026-11-10T01:00:00Z')")
        db.execute("INSERT INTO std_notices VALUES(?,?,?,?,?,?,?)",
                   (bid,"000","20261109","공공 홈페이지", "서울", "제한경쟁", "협상"))
        db.execute("INSERT INTO std_awards VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (bid,"000","20261109","공공 홈페이지","용역",2,1,
                    "1112233333","실제 낙찰자",100000000,90.2,"2026-11-09",0,2))
        db.execute("INSERT INTO std_contracts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   ("R26CT1001","000","20261109",bid,"000","개발 계약",
                    "실제 계약자","1112233333",95000000,"2026-11-09",0))
        db.execute("INSERT INTO std_contracts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   ("R26CT1002","000","20261109",bid,"000","별도 업체",
                    "다른 업체","2223344444",110000000,"2026-11-09",0))
    db.close()
    result = api["standard_bid_evidence"](bid)
    assert result["installed"] is True
    assert result["notice"]["source"] == "B1"
    assert result["award"]["identifiedBidders"] == 2
    assert result["award"]["winner"] == "실제 낙찰자"
    assert len(result["contracts"]) == 2
    assert sum(bool(c["matchesAwardWinner"]) for c in result["contracts"]) == 1
    assert "이행" in result["scopeNote"]
    status = api["standard_sync_status"]()
    assert status["installed"] and status["coverage"]["B2"]["officialRows"] == 2
    assert status["stored"]["B3"] == 2
    assert "serviceKey" not in str(result)
    assert api["standard_bid_evidence"]("R26BK01806519")["award"] is None
g["G2B_STD_DB_PATH"] = original
print("WORKLINKS_B123_READONLY_API=PASS")
