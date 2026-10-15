#!/usr/bin/env python3
"""Read-only WorkLinks RFP gate census. Prints aggregates, never raw attachments."""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "startup-support"
RFP = json.loads((ROOT / "rfp-clauses.json").read_text(encoding="utf-8"))
AI = json.loads((ROOT / "ai-qualification.json").read_text(encoding="utf-8"))
source = RFP.get("byNotice") or {}
analyzed = AI.get("byNotice") or {}
samples = (
    "R26BK01756420:000", "R26BK01753188:000",
    "R26BK01755213:000", "R26BK01747543:000",
)

def audit_gate(a):
    if not a: return "ai_not_in_snapshot"
    if a.get("analysisStatus") not in ("classified", "rule_based"):
        return "ai_not_classified"
    d = a.get("fullDocumentAudit") or {}
    if d.get("complete") is not True:
        return "audit_incomplete"
    if not all(a.get(k) is True for k in
               ("reviewComplete", "requiredConditionsComplete",
                "documentInterpretationReviewed")):
        return "ai_review_flag_incomplete"
    if a.get("sourceTruncated") is True:
        return "source_truncated"
    return "ai_audit_pass"

def source_gate(s):
    if not s: return "rfp_not_in_snapshot"
    if s.get("status") != "text_extracted_requires_review":
        return "rfp_not_extracted"
    files = s.get("files") or []
    if s.get("manifestComplete") is not True:
        return "manifest_incomplete"
    if not files or len(files) != s.get("attachmentManifestCount"):
        return "document_count_mismatch"
    if any(f.get("readable") is not True for f in files):
        return "unreadable_file"
    if any(f.get("sourceTextScanComplete") is not True or
           f.get("unmatchedQualificationAnchorCount") != 0
           for f in files):
        return "source_scan_incomplete"
    if any(f.get("qualificationScanTruncated") or
           f.get("clauseCandidatesTruncated") for f in files):
        return "source_truncated"
    return "rfp_preliminary_gate_pass"

def digest_notice(key):
    s = source.get(key)
    a = analyzed.get(key)
    files = (s or {}).get("files") or []
    requirements = (a or {}).get("requirements") or []
    counts = collections.Counter(x.get("classification", "missing") for x in requirements)
    typed = collections.Counter(x.get("type", "missing") for x in requirements
                                if x.get("classification") == "mandatory")
    return {
        "key": key, "rfpPresent": bool(s), "aiPresent": bool(a),
        "rfpStatus": (s or {}).get("status"), "sourceGate": source_gate(s),
        "manifestComplete": (s or {}).get("manifestComplete"),
        "manifestCount": (s or {}).get("attachmentManifestCount"),
        "files": len(files), "readable": sum(f.get("readable") is True for f in files),
        "scanComplete": sum(f.get("sourceTextScanComplete") is True for f in files),
        "unmatchedAnchors": sum(f.get("unmatchedQualificationAnchorCount") or 0 for f in files),
        "candidateCount": sum(len(f.get("clauseCandidates") or []) for f in files),
        "filesPreview": [{
            "name": f.get("name"), "readable": f.get("readable"),
            "errorCategory": f.get("errorCategory"),
            "scanComplete": f.get("sourceTextScanComplete"),
            "unmatchedAnchors": f.get("unmatchedQualificationAnchorCount"),
        } for f in files[:8]],
        "aiGate": audit_gate(a), "aiMode": (a or {}).get("analysisStatus"),
        "auditComplete": ((a or {}).get("fullDocumentAudit") or {}).get("complete"),
        "auditBlockers": ((a or {}).get("fullDocumentAudit") or {}).get("blockers") or [],
        "reviewComplete": (a or {}).get("reviewComplete"),
        "requirements": len(requirements),
        "classes": dict(counts), "mandatoryTypes": dict(typed),
        "verified": sum(q.get("sourceVerified") is True for q in requirements),
        "fullReviewFalse": sum(q.get("documentFullyReviewed") is False for q in requirements),
        "qualificationExamples": [{
            "type": q.get("type"), "class": q.get("classification"),
            "relation": q.get("relation"), "codes": q.get("codes")
        } for q in requirements if q.get("classification") == "mandatory"][:8],
    }

def emit(tag, value):
    print(tag + " " + json.dumps(value, ensure_ascii=False, sort_keys=True))

status = collections.Counter((r or {}).get("status", "missing") for r in source.values())
source_stages = collections.Counter(source_gate(s) for s in source.values())
ai_stages = collections.Counter(audit_gate(a) for a in analyzed.values())
blockers = collections.Counter(b for a in analyzed.values()
                               for b in (((a or {}).get("fullDocumentAudit") or {}).get("blockers") or []))
first_blockers = collections.Counter(
    (((a or {}).get("fullDocumentAudit") or {}).get("blockers") or ["none"])[0]
    for a in analyzed.values())
classification = collections.Counter((a or {}).get("analysisStatus", "missing") for a in analyzed.values())
overlap = set(source) & set(analyzed)
passing = [k for k in overlap if source_gate(source[k]) == "rfp_preliminary_gate_pass"
           and audit_gate(analyzed[k]) == "ai_audit_pass"]
# Even a passing RFP+AI gate does not establish current G2B and SME checks.
emit("DIAG_TOTAL", {
    "rfpNotices": len(source), "aiNotices": len(analyzed),
    "overlap": len(overlap), "onlyRfp": len(set(source)-set(analyzed)),
    "onlyAI": len(set(analyzed)-set(source)),
    "aiPassingWithinOverlap": sum(audit_gate(analyzed[k]) == "ai_audit_pass" for k in overlap),
    "rfpPassingWithinOverlap": sum(source_gate(source[k]) == "rfp_preliminary_gate_pass" for k in overlap),
    "passingBothPrerequisites": len(passing),
    "rfpGeneratedAt": RFP.get("generatedAt"), "aiGeneratedAt": AI.get("generatedAt"),
})
emit("DIAG_RFP_STATUS", dict(status))
emit("DIAG_SOURCE_STAGE", dict(source_stages))
emit("DIAG_AI_STAGE", dict(ai_stages))
emit("DIAG_AI_CLASSIFICATION", dict(classification))
emit("DIAG_BLOCKERS", dict(blockers))
emit("DIAG_FIRST_BLOCKER", dict(first_blockers))
emit("DIAG_POTENTIALLY_PASSING_BOTH", passing[:10])
for k in samples:
    emit("DIAG_SAMPLE", digest_notice(k))
