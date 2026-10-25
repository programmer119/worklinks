#!/usr/bin/env python3
"""Offline, source-bound Changcom RFP evidence audit; no API/download access.

Counts extracted references separately from legally VERIFIED eligibility.
Run against committed files only. This script never edits input records.
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"startup-support"
PRIORITIES=("R26BK01765310","R26BK01779843","R26BK01777288",
            "R26BK01777538","R26BK01765541")


def load(name):
    document=json.loads((BASE/name).read_text(encoding="utf-8"))
    if not isinstance(document,dict):raise ValueError("invalid "+name)
    return document


def valid_evidence(entry):
    """An excerpt counts only with official URL, text, and document ID."""
    if not isinstance(entry,dict):return False
    url=str(entry.get("url") or "")
    text=str(entry.get("text") or entry.get("sourceText") or "").strip()
    name=str(entry.get("sourceFile") or "").strip()
    return url.startswith("https://www.g2b.go.kr/") and bool(text and name)


def classify(record):
    """Proof-link ≠ legal qualification verdict."""
    if not isinstance(record,dict):return "not_indexed"
    if record.get("status")=="text_extracted_requires_review":
        return "scan_completed_manual_review_required"
    return str(record.get("status") or "unknown")


def evidence_stats(record):
    compact=(record or {}).get("changcomClauseEvidence") or {}
    clauses=compact.get("clauseCandidates") or {}
    entries=[c for values in clauses.values() if isinstance(values,list) for c in values]
    valid=[c for c in entries if valid_evidence(c)]
    return {
        "stored":len(entries),
        "citable":len(valid),
        "uncitable":len(entries)-len(valid),
        "types":sorted(k for k,v in clauses.items() if isinstance(v,list) and v),
        "officialLinks":sum(
            str(f.get("url") or "").startswith("https://www.g2b.go.kr/")
            for f in compact.get("files") or [] if isinstance(f,dict))
    }


def audit(actionable,index,detail,review):
    bids=actionable.get("bids") or []
    index_rows=index.get("byNotice") or {}
    detail_rows=detail.get("byNotice") or {}
    review_rows=review.get("byNotice") or {}
    candidate_keys={
        str(b.get("bidNo") or "")+":"+str(b.get("order") or "0").zfill(3)
        for b in bids if isinstance(b,dict) and b.get("bidNo")
    }
    if not candidate_keys:raise ValueError("no Changcom bid candidates")
    evidence_count=0
    citable_count=0
    scans=0
    for key in candidate_keys:
        row=index_rows.get(key)
        if isinstance(row,dict):
            scans+=int(row.get("status")=="text_extracted_requires_review")
            stats=evidence_stats(row)
            evidence_count+=int(stats["stored"]>0)
            citable_count+=int(stats["citable"]>0)
    priorities=[]
    for no in PRIORITIES:
        key=no+":000"
        indexed=index_rows.get(key)
        detailed=detail_rows.get(key) or {}
        reviewed=review_rows.get(key) or {}
        stats=evidence_stats(indexed)
        priorities.append({
            "bidNo":no,"inCandidateList":key in candidate_keys,
            "indexedStatus":classify(indexed),"inDetailCache":bool(detailed),
            "readableSources":(indexed or {}).get("readableDocumentCount",0),
            "officialClauseExcerpts":stats["stored"],
            "citableExcerpts":stats["citable"],
            "uncitableExcerpts":stats["uncitable"],
            "evidenceTypes":stats["types"],
            "reviewState":reviewed.get("state") or "not_reviewed",
            "eligibilityVerified":reviewed.get("legalEligibilityVerified") is True,
            "profitabilityVerified":reviewed.get("profitability") not in (None,"not_verified"),
        })
    if any(p["eligibilityVerified"] for p in priorities):
        raise AssertionError("offline source presence must not imply eligibility")
    return {
        "generatedFrom":{
            "actionable":actionable.get("generatedAt"),
            "rfpIndex":index.get("generatedAt"),
            "rfpDetail":detail.get("generatedAt")
        },
        "indexedSW":(actionable.get("counts") or {}).get("indexedSWTotal"),
        "changcomCandidates":len(candidate_keys),
        "rfpIndexedTotal":len(index_rows),
        "rfpDetailedCache":len(detail_rows),
        "candidateSuccessfulScans":scans,
        "candidateWithOfficialExcerpts":evidence_count,
        "candidateWithCitableExcerpts":citable_count,
        "finalQualificationVerifiedInFive":sum(p["eligibilityVerified"] for p in priorities),
        "priorities":priorities
    }


def self_test():
    good={"url":"https://www.g2b.go.kr/pn/example","sourceFile":"official.hwpx","text":"직접생산 필수"}
    assert valid_evidence(good)
    assert not valid_evidence({**good,"url":"https://example.org/notice"})
    assert not valid_evidence({**good,"text":" "})
    assert not valid_evidence({**good,"sourceFile":""})
    assert evidence_stats({"changcomClauseEvidence":{"clauseCandidates":{
        "industry_code":[good,{**good,"url":"https://example.org/notice"}]}}})["citable"]==1
    print("WORKLINKS_CHANGCOM_OFFLINE_EVIDENCE_UNIT=PASS")


if __name__=="__main__":
    self_test()
    result=audit(load("changcom-actionable.json"),
                 load("rfp-coverage-index.json"),
                 load("rfp-clauses.json"),
                 load("changcom-bid-review.json"))
    print("WORKLINKS_CHANGCOM_OFFLINE_AUDIT",json.dumps(result,ensure_ascii=False,separators=(",",":")))
