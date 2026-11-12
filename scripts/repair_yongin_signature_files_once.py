#!/usr/bin/env python3
"""One-off, evidence-preserving repair of two mislabeled Yongin attachments.

Does not query G2B notice APIs or re-fetch three already-readable documents.
Never upgrades the archived notice to a final bidder-eligibility verdict.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from refresh_worklinks_rfp import (
    download, extract, normalize_extracted_text, parse_clauses,
    extract_rule_candidates, preserve_unclassified_qualification,
    compact_changcom_evidence, CLASSIFICATION_VERSION
)

NOTICE="R26BK01807134:000"
FILES={
 "입찰공고문(지방,협상,1468.20억미만,유지,서면,기술지원).hwpx":{
    "url":"https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01807134&bidPbancOrd=000&fileType=&fileSeq=1&prcmBsneSeCd=03",
    "shaPrefix":"0c461b5fa78b75dcd6c2", "magic":bytes.fromhex("D0CF11E0A1B11AE1")
 },
 "물품공급 및 기술지원 협약서(2027년 용인시 홈페이지 기능개선 및 유지관리).pdf":{
    "url":"https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadRfpFile.do?rfpNo=R26DH00062317&rfpOrd=000&rfpUntyAtchFileNo=13",
    "shaPrefix":"7f95ac288cb653e8eb37", "magic":bytes.fromhex("504b0304")
 }
}
def safe_write(path,raw):
    fd,temp=tempfile.mkstemp(dir=str(path.parent),prefix=path.name+".",suffix=".tmp")
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def repair(data_dir):
    directory=Path(data_dir)/"snapshots"
    file=directory/"rfp-coverage-index.json"
    data=json.loads(file.read_text(encoding="utf-8"))
    notices=data.get("byNotice")
    if not isinstance(notices,dict) or NOTICE not in notices:
        raise RuntimeError("YONGIN_INDEX_RECORD_UNAVAILABLE")
    record=notices[NOTICE]
    files=record.get("files")
    if not (record.get("manifestComplete") is True and isinstance(files,list) and len(files)==5):
        raise RuntimeError("YONGIN_ATTACHMENT_MANIFEST_CHANGED")
    matching={f.get("name"):f for f in files}
    if not set(FILES).issubset(matching):
        raise RuntimeError("YONGIN_ATTACHMENT_IDENTITIES_CHANGED")
    # Never lose a successfully read sibling just to repair two failed files.
    good_siblings=[f for f in files if f.get("name") not in FILES]
    if len(good_siblings)!=3 or not all(
        f.get("readable") is True and
        f.get("sourceTextScanComplete") is True for f in good_siblings):
        raise RuntimeError("YONGIN_EXISTING_THREE_READABLE_SIBLINGS_NOT_CONFIRMED")
    if all(matching[k].get("readable") is True and
           matching[k].get("sourceTextScanComplete") is True for k in FILES):
        print("YONGIN_SIGNATURE_REPAIR_ALREADY_COMPLETE 5/5",flush=True)
        return
    newly=[]
    for filename,source in FILES.items():
        if matching[filename].get("readable") is True and matching[filename].get("sourceTextScanComplete") is True:
            continue
        # One official GET per unreadable file; verify it is exactly the binary
        # tested earlier. An unexpected new revision requires fresh investigation.
        raw=download(source["url"])
        signature=hashlib.sha256(raw).hexdigest()
        if not raw.startswith(source["magic"]) or not signature.startswith(source["shaPrefix"]):
            raise RuntimeError("YONGIN_OFFICIAL_ATTACHMENT_CHANGED "+filename)
        text=normalize_extracted_text(extract(filename,raw))
        if len(text.strip())<100:
            raise RuntimeError("YONGIN_TEXT_TOO_SHORT "+filename)
        triggers,snippets=parse_clauses(text)
        rules=extract_rule_candidates(text,filename)
        scan=preserve_unclassified_qualification(text,filename,rules)
        if scan.get("sourceTextScanComplete") is not True:
            raise RuntimeError("YONGIN_QUALIFICATION_SOURCE_SCAN_INCOMPLETE "+filename)
        if len(text)>350000:
            raise RuntimeError("YONGIN_TEXT_TRUNCATION_REQUIRES_REVIEW "+filename)
        matching[filename].update({
            "readable":True,"sourceSha256":signature,"sourceTextScanComplete":True,
            "qualificationScanTruncated":False,
            "unmatchedQualificationAnchorCount":scan.get("unmatchedQualificationAnchorCount",0),
            "clauseCandidateCount":len(rules),"textChars":len(text),
            "sourceUrl":source["url"],"actualFormat":"HWP5" if filename.endswith(".hwpx") else "ZIP(PDFx2)"
        })
        matching[filename].pop("errorCategory",None)
        newly.append({"name":filename,"sourceUrl":source["url"],"readable":True,
                      "sourceSha256":signature,"clauseCandidates":rules})
        print("YONGIN_SIGNATURE_FILE_OK",json.dumps({
            "name":filename,"bytes":len(raw),"textChars":len(text),
            "sha256":signature[:20],"clauses":len(rules)},ensure_ascii=False),flush=True)
    if sum(f.get("readable") is True and f.get("sourceTextScanComplete") is True
            for f in files)!=5:raise RuntimeError("YONGIN_REPAIR_NOT_5_OF_5")
    # Retain the old three files' official excerpts and add newly extracted
    # evidence. Do not claim every requirement was legally reviewed.
    if newly:
        new_evidence=compact_changcom_evidence({"files":newly,"status":"text_extracted_requires_review",
            "checkedAt":dt.datetime.now(dt.timezone.utc).isoformat()})
        prior=record.get("changcomClauseEvidence") or {}
        prior_types=prior.get("clauseCandidates") or {}
        combined={kind:list(items) for kind,items in prior_types.items()
                  if isinstance(items,list)}
        for typ,items in (new_evidence.get("clauseCandidates") or {}).items():
            dest=combined.setdefault(typ,[])
            seen={(e.get("sourceFile"),e.get("text")) for e in dest}
            for item in items:
                key=(item.get("sourceFile"),item.get("text"))
                if key not in seen:
                    dest.append(item);seen.add(key)
        prior_links=list(prior.get("files") or [])
        existing_urls={a.get("url") for a in prior_links}
        for link in new_evidence.get("files") or []:
            if link.get("url") not in existing_urls:
                prior_links.append(link);existing_urls.add(link.get("url"))
        prior.update({"clauseCandidates":combined,"files":prior_links[:12],
                      "manifestComplete":True,"readableDocumentCount":5,
                      "unreadableDocumentCount":0,
                      "status":"text_extracted_requires_review",
                      "reviewComplete":False,"eligibilityVerified":False})
        record["changcomClauseEvidence"]=prior
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    record.update({"status":"text_extracted_requires_review",
                   "readableDocumentCount":5,"unreadableDocumentCount":0,
                   "checkedAt":now,"signatureReaderRepair":"2026-11-12",
                   "classificationVersion":CLASSIFICATION_VERSION,
                   "reviewComplete":False})
    data["generatedAt"]=now
    safe_write(file,(json.dumps(data,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    # The API prefers a .gz snapshot when the browser sends Accept-Encoding.
    gzfile=Path(str(file)+".gz")
    safe_write(gzfile,gzip.compress(file.read_bytes(),compresslevel=5,mtime=0))
    print("YONGIN_SIGNATURE_REPAIR_PUBLISHED 5/5",flush=True)
    print("YONGIN_REVIEW_COMPLETE_FALSE",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-dir",required=True)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not args.execute:
        raise SystemExit("YONGIN_SIGNATURE_REPAIR_DRY_RUN: supply --execute on server123")
    repair(args.data_dir)
