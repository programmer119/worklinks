#!/usr/bin/env python3
"""No-network regression for per-notice parser provenance and safe status."""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(root / "scripts/build_worklinks_rfp_provenance.py"))
build = module["build"]
latest = module["read_latest"](root / "scripts/refresh_worklinks_rfp.py")
base = {
    "status": "text_extracted_requires_review", "checkedAt": "2026-11-14T02:00:00Z",
    "classificationVersion": latest["CLASSIFICATION_VERSION"],
    "hwpxReaderVersion": latest["HWPX_READER_VERSION"],
    "manifestComplete": True, "staffingRoleScanComplete": True,
    "files": [
        {"name": "proposal.pdf", "readable": True, "sourceTextScanComplete": True,
         "staffingRoleScanVersion": latest["STAFFING_ROLE_SCAN_VERSION"],
         "staffingFactScanVersion": latest["STAFFING_FACT_SCAN_VERSION"]}
    ],
}
rows = {
    "R26BK00000001:000": base,
    "R26BK00000002:000": {**base, "classificationVersion": latest["CLASSIFICATION_VERSION"] - 1},
    "R26BK00000003:000": {**base, "files": [{**base["files"][0], "staffingRoleScanVersion": 0}]},
    "R26BK00000004:000": {**base, "staffingRoleScanComplete": False},
    "R26BK00000005:000": {"status": "no_official_attachment_metadata", "files": []},
    "R26BK00000006:000": {"status": "not_scanned", "files": []},
    "R26BK00000007:000": {**base, "files": [base["files"][0], {
        "name": "duplicate.hwpx", "readable": False, "staffingRoleScanVersion": 0,
        "skippedDuplicateFormat": True}]}
}
out = build({"ok": True, "generatedAt": "2026-11-14T02:00:00Z", "byNotice": rows}, latest)
expected = ["current", "legacy", "legacy", "incomplete", "failed", "unscanned", "current"]
assert [out["byNotice"][k]["outcome"] for k in rows] == expected, out["summary"]
assert out["byNotice"]["R26BK00000003:000"]["current"] is False
assert out["byNotice"]["R26BK00000004:000"]["current"] is False
assert out["byNotice"]["R26BK00000007:000"]["current"] is True
assert out["total"] == len(rows)
print("RFP_PARSER_VERSION_PROVENANCE_REGRESSION=PASS", out["summary"])
