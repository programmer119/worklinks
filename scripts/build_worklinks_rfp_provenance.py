#!/usr/bin/env python3
"""Publish a small per-notice RFP parser version inventory, with no network calls.

The cumulative RFP index is the authority for parser provenance. This inventory
does not promote "text extracted" into a current staffing/onsite decision.
"""
import argparse
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path


def read_latest(script):
    source = Path(script).read_text(encoding="utf-8")
    result = {}
    for variable in ("CLASSIFICATION_VERSION", "HWPX_READER_VERSION",
                     "STAFFING_ROLE_SCAN_VERSION", "STAFFING_FACT_SCAN_VERSION"):
        matched = re.search(r"(?m)^" + variable + r"\s*=\s*(\d+)\s*$", source)
        if not matched:
            raise ValueError("missing current parser version: " + variable)
        result[variable] = int(matched.group(1))
    return result


def build(index, versions):
    source = index.get("byNotice")
    if index.get("ok") is not True or not isinstance(source, dict):
        raise ValueError("invalid RFP index")
    result = {}
    counters = Counter()
    for key, row in source.items():
        if not re.fullmatch(r"(?:R\d{2}BK\d{8}|\d{11}):\d{3}", key):
            raise ValueError("invalid notice key: " + key)
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "unknown")
        files = [f for f in (row.get("files") or []) if isinstance(f, dict)]
        readable = [f for f in files if f.get("readable") is True]
        classification = int(row.get("classificationVersion") or 0)
        hwpx = int(row.get("hwpxReaderVersion") or 0)
        role_versions = sorted({int(f.get("staffingRoleScanVersion") or 0) for f in readable})
        fact_versions = sorted({int(f.get("staffingFactScanVersion") or 0) for f in readable})
        staffing_current = (
            status == "text_extracted_requires_review"
            and row.get("staffingRoleScanComplete") is True
            and bool(readable)
            and all(f.get("sourceTextScanComplete") is True
                    and int(f.get("staffingRoleScanVersion") or 0) >= versions["STAFFING_ROLE_SCAN_VERSION"]
                    and int(f.get("staffingFactScanVersion") or 0) >= versions["STAFFING_FACT_SCAN_VERSION"]
                    for f in readable if f.get("staffingScopeExcluded") is not True)
            and any(f.get("staffingScopeExcluded") is not True for f in readable)
        )
        current = (
            staffing_current
            and classification >= versions["CLASSIFICATION_VERSION"]
            and hwpx >= versions["HWPX_READER_VERSION"]
        )
        if status != "text_extracted_requires_review":
            outcome = "unscanned" if status in ("not_scanned", "unscanned") else "failed"
        elif current:
            outcome = "current"
        elif classification < versions["CLASSIFICATION_VERSION"] or hwpx < versions["HWPX_READER_VERSION"] or (
                readable and any(int(f.get("staffingRoleScanVersion") or 0) < versions["STAFFING_ROLE_SCAN_VERSION"]
                                 or int(f.get("staffingFactScanVersion") or 0) < versions["STAFFING_FACT_SCAN_VERSION"]
                                 for f in readable)):
            outcome = "legacy"
        else:
            outcome = "incomplete"
        item = {
            "status": status, "checkedAt": str(row.get("checkedAt") or ""),
            "classificationVersion": classification, "hwpxReaderVersion": hwpx,
            "staffingRoleVersions": role_versions, "staffingFactVersions": fact_versions,
            "staffingScanComplete": bool(row.get("staffingRoleScanComplete")),
            "staffingCurrent": bool(staffing_current), "current": bool(current),
            "manifestComplete": row.get("manifestComplete") is True,
            "readableFiles": len(readable), "totalFiles": len(files),
            "outcome": outcome,
        }
        result[key] = item
        counters[outcome] += 1
    output = {
        "ok": True, "schemaVersion": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sourceGeneratedAt": str(index.get("generatedAt") or ""),
        "latest": versions, "total": len(result),
        "summary": dict(sorted(counters.items())),
        "byNotice": result
    }
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--index", type=Path, default=Path("startup-support/rfp-coverage-index.json"))
    p.add_argument("--reader", type=Path, default=Path("scripts/refresh_worklinks_rfp.py"))
    p.add_argument("--output", type=Path, default=Path("startup-support/rfp-scan-provenance.json"))
    args = p.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    result = build(index, read_latest(args.reader))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("RFP_PROVENANCE_PUBLISHED", json.dumps({
        "count": result["total"], "summary": result["summary"], "latest": result["latest"],
        "bytes": args.output.stat().st_size
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
