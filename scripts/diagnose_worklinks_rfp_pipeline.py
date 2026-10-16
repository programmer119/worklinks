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
# Identify the actual lost-coverage groups before changing qualification rules.
# Raw excerpts are short public-document diagnostics; never infer eligibility from them.
unmatched_file_kinds = collections.Counter()
unmatched_examples = []
unreadable_reasons = collections.Counter()
scan_causes = collections.Counter()
for key, notice in source.items():
    for file in notice.get("files") or []:
        suffix = Path(file.get("name") or "").suffix.lower() or "(none)"
        if file.get("readable") is not True:
            unreadable_reasons[(suffix, file.get("errorCategory") or "unknown")] += 1
            continue
        if file.get("sourceTextScanComplete") is not True:
            scan_causes["scan_false"] += 1
            samples = file.get("unmatchedAnchorSamples") or []
            if samples:
                unmatched_file_kinds[suffix] += 1
                for item in samples[:3]:
                    # Distinguish ignored guidance, missing extraction pattern,
                    # and long-fragment citation breakages.
                    text = " ".join(str(item).split())
                    if len(unmatched_examples) < 24:
                        unmatched_examples.append({"id":key, "fileType":suffix,
                                                  "text":text[:180]})
            else:
                scan_causes["no_unmatched_sample"] += 1
        if file.get("qualificationScanTruncated"):
            scan_causes["text_truncated"] += 1
emit("DIAG_SCAN_FAILURE_TYPES", dict(scan_causes))
emit("DIAG_UNMATCHED_FILE_TYPES", dict(unmatched_file_kinds))
emit("DIAG_UNREADABLE_REASONS", [
    {"fileType":ext, "error":reason, "count":n}
    for (ext,reason),n in unreadable_reasons.most_common(16)])
emit("DIAG_UNMATCHED_EXAMPLES", unmatched_examples)

# Unclassified passages are cited source text, never automatically fulfilled
# eligibility conditions. Track them apart from raw text-scan coverage.
unclassified_ids=set()
unclassified_files=0
unclassified_count=0
unclassified_sample=[]
for key,notice in source.items():
    for file in notice.get("files") or []:
        spans=[c for c in (file.get("clauseCandidates") or [])
               if c.get("type")=="unclassified_qualification"]
        if not spans:continue
        unclassified_ids.add(key)
        unclassified_files += 1
        unclassified_count += len(spans)
        if len(unclassified_sample)<8:
            unclassified_sample.append({
                "id":key,"file":str(file.get("name") or "")[:100],
                "text":str(spans[0].get("sourceText") or "")[:150]})
emit("DIAG_UNCLASSIFIED_REQUIRES_REVIEW", {
    "notices":len(unclassified_ids),"files":unclassified_files,
    "passages":unclassified_count,"examples":unclassified_sample})

emit("DIAG_RFP_STATUS", dict(status))
emit("DIAG_SOURCE_STAGE", dict(source_stages))
emit("DIAG_AI_STAGE", dict(ai_stages))
emit("DIAG_AI_CLASSIFICATION", dict(classification))
emit("DIAG_BLOCKERS", dict(blockers))
emit("DIAG_FIRST_BLOCKER", dict(first_blockers))
emit("DIAG_POTENTIALLY_PASSING_BOTH", passing[:10])
for k in samples:
    emit("DIAG_SAMPLE", digest_notice(k))

rfp_only = set(source)-set(analyzed)
rfp_text_only = [k for k in rfp_only if source[k].get("status") == "text_extracted_requires_review"]
emit("DIAG_DISJOINT", {
    "rfpOnlyStatuses": dict(collections.Counter((source[k] or {}).get("status") for k in rfp_only)),
    "rfpOnlyTextExtracted": len(rfp_text_only),
    "rfpOnlyWithClauseCandidates": sum(any(f.get("clauseCandidates") for f in source[k].get("files") or []) for k in rfp_text_only),
})
for k in sorted(source):
    if source_gate(source[k]) == "rfp_preliminary_gate_pass":
        emit("DIAG_SOURCE_PASS", {
            "key": k, "aiPresent": k in analyzed, "aiGate": audit_gate(analyzed.get(k)),
            "aiBlockers": ((analyzed.get(k) or {}).get("fullDocumentAudit") or {}).get("blockers") or [],
            "unknownClassification": sum(q.get("classification") == "unknown"
                                         for q in (analyzed.get(k) or {}).get("requirements") or []),
        })
for key in samples:
    a = analyzed.get(key) or {}
    unknown = [q for q in a.get("requirements") or []
               if q.get("classification") == "unknown"]
    emit("DIAG_UNKNOWN_EXAMPLES", {
        "key": key,
        "unknownTypeCounts": dict(collections.Counter(q.get("type") for q in unknown)),
        "examples": [
            {"type": q.get("type"),
             "codes": q.get("codes"),
             "text": " ".join(str(q.get("sourceText") or "").split())[:135]}
            for q in unknown[:12]
        ],
    })

# Frontend comparePartnerJob() unconditionally reports these mandatory types as
# pending, regardless of whether the AI/source audit succeeded.
hard_pending_types = {
    "staff_proof", "performance_proof", "bid_security",
    "registration_identity", "eligibility_cutoff", "submission_required",
}
affected = collections.Counter()
pending_by_type = collections.Counter()
any_pending = []
for key, record in analyzed.items():
    mand = [q for q in record.get("requirements") or []
            if q.get("classification") == "mandatory"
            and q.get("type") in hard_pending_types]
    if not mand:
        continue
    any_pending.append(key)
    for t in set(q.get("type") for q in mand):
        affected[t] += 1
    pending_by_type.update(q.get("type") for q in mand)
emit("DIAG_HARD_PENDING", {
    "noticesAffected": len(any_pending),
    "affectedByType": dict(affected),
    "clauseCountByType": dict(pending_by_type),
    "candidateNoticesWithoutHardPending": len(analyzed)-len(any_pending),
})
for k in samples:
    a = analyzed.get(k) or {}
    counts = collections.Counter(q.get("type") for q in a.get("requirements") or []
                                 if q.get("classification") == "mandatory"
                                 and q.get("type") in hard_pending_types)
    emit("DIAG_SAMPLE_HARD_PENDING", {"key": k, "hardPendingClauseTypes": dict(counts),
                                      "hardPendingClauseTotal": sum(counts.values())})
