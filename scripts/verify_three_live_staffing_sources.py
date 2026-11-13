#!/usr/bin/env python3
"""Read-only, real-source regression: three reported staffing omissions.

Runs the actual production extractor on exact official attachment bytes.
Synthetic samples, remembered snippets and prior OCR results are NOT accepted
as a successful real-source test.
"""
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import refresh_worklinks_rfp as p

def read_json(name):
    with (ROOT/"startup-support"/name).open(encoding="utf-8") as handle:
        return json.load(handle)

def safe_url(value):
    value=str(value or "")
    parts=urllib.parse.urlsplit(value)
    return (parts.scheme=="https" and
            parts.hostname in ("www.g2b.go.kr","g2b.go.kr")
            and parts.path.startswith("/pn/"))

def to_key(item):
    return str(item.get("bidNo") or "")+":"+str(item.get("order") or "000").zfill(3)

def notice_targets(actionable):
    names={
      "yongin":("R26BK01807134:000","용인시 홈페이지"),
      "exercise":("R26BK01797739:000","지휘훈련시스템")
    }
    hits=[]
    for item in actionable.get("bids") or []:
        title=str(item.get("title") or "")
        if "북한" in title and ("정보" in title or "분석" in title):
            hits.append({"id":to_key(item),"title":title})
    chosen=list({row["id"]:row for row in hits}.values())
    print("REAL_STAFFING_NORTH_CANDIDATES "+json.dumps(chosen[:20],ensure_ascii=False),flush=True)
    if len(chosen)==1:
        names["north"]=(chosen[0]["id"],chosen[0]["title"])
    else:
        names["north"]=("", "북한정보분석시스템 (공지 ID 조회 미완료)")
    return names

def official_sources(key,record,detail,government_api_fallback=True):
    source_by_name={}
    def add(name,url,sha="",readable=None):
        name=str(name or "").strip()
        url=str(url or "").strip()
        if not (name and safe_url(url)):return
        row=source_by_name.setdefault(name,{"name":name,"url":url,"sha":str(sha or ""),
            "wasReadable":readable})
        if sha and not row.get("sha"):row["sha"]=str(sha)
    for row in (detail.get("files") or []):
        add(row.get("name"),row.get("sourceUrl"),row.get("sourceSha256"),row.get("readable"))
    for row in ((record.get("changcomClauseEvidence") or {}).get("files") or []):
        add(row.get("name"),row.get("url"))
    for row in (record.get("files") or []):
        add(row.get("name"),row.get("sourceUrl"),row.get("sourceSha256"),row.get("readable"))
    metadata={"attempted":False}
    inventory=[str(x.get("name") or "") for x in record.get("files") or []]
    if government_api_fallback and (not source_by_name or
            (inventory and len(source_by_name)<len(inventory))):
        metadata["attempted"]=True
        no,ordn=key.split(":")
        try:
            data=p.fetch_json(p.BASE+"bid-evidence?"+urllib.parse.urlencode({"bidNo":no,"order":ordn}))
            docs=data.get("attachments") or {}
            metadata.update(ok=bool(docs.get("ok")),complete=bool(docs.get("complete")),
                            count=docs.get("count"))
            for item in docs.get("items") or []:
                direct=p.legal_file(item)
                if direct:
                    name,url=direct
                    prior=next((x for x in record.get("files") or []
                               if x.get("name")==name),{})
                    add(name,url,prior.get("sourceSha256"),prior.get("readable"))
        except Exception as exc:
            metadata["error"]=type(exc).__name__+":"+str(exc)[:160]
    return list(source_by_name.values()),inventory,metadata

def excerpt_lines(text):
    lines=text.splitlines()
    expressions=re.compile(r"(?i)인력|인원|개발|PM|PL|DBA|AI.?전문|투입|상주|MM|기술자|인프라")
    matched=[]
    for line in lines:
        clean=" ".join(line.split())
        if len(clean)>6 and expressions.search(clean):
            matched.append(clean[:220])
        if len(matched)>=6:break
    return matched

def run():
    archive=read_json("rfp-coverage-index.json").get("byNotice") or {}
    detailed=read_json("rfp-clauses.json").get("byNotice") or {}
    actionable=read_json("changcom-actionable.json")
    targets=notice_targets(actionable)
    print("REAL_STAFFING_PARSER_VERSION "+str(p.STAFFING_ROLE_SCAN_VERSION),flush=True)
    all_results=[]
    for name,(key,title) in targets.items():
        report={"case":name,"key":key,"title":title,"realDocumentsParsed":0,
                "roleEvidence":[],"fileResults":[],"verified":False}
        if not key:
            report["status"]="NOTICE_ID_NOT_FOUND"
            all_results.append(report)
            continue
        record=archive.get(key) or {}
        detail=detailed.get(key) or {}
        report.update(archived=bool(record),detailAvailable=bool(detail),
                      priorRecordedRoles=(record.get("staffingRoles") or [])[:8],
                      priorScanComplete=record.get("staffingRoleScanComplete"))
        sources,manifest,meta=official_sources(key,record,detail)
        report["sourceManifestNames"]=manifest[:24]
        report["linkCount"]=len(sources)
        report["metadataLookup"]=meta
        if not sources:
            report["status"]="OFFICIAL_SOURCE_URL_NOT_AVAILABLE"
            all_results.append(report)
            continue
        # Source files: use official URLs and exactly current extractor, never fixtures.
        ordered=sorted(sources,key=lambda x: (
            0 if re.search(r"제안요청|과업|공내역|인력|사업수행",x["name"]) else
            1 if x["name"].lower().endswith(".pdf") else 2, x["name"]))
        seen_roles=set()
        for f in ordered[:24]:
            row={"name":f["name"],"previouslyReadable":f["wasReadable"]}
            try:
                raw=p.download(f["url"])
                newsha=hashlib.sha256(raw).hexdigest()
                row.update(bytes=len(raw),sha256prefix=newsha[:16],
                           priorShaMatches=(None if not f["sha"] else
                                            newsha==f["sha"]))
                if f["sha"] and newsha!=f["sha"]:
                    row["status"]="SOURCE_BYTES_CHANGED"
                    report["fileResults"].append(row)
                    continue
                parsed,audit=p.extract_with_source_status(f["name"],raw)
                text=p.normalize_extracted_text(parsed)
                if not audit.get("sourceComplete"):
                    row["status"]="TEXT_EXTRACTION_INCOMPLETE"
                    row["sourceComplete"]=False
                    report["fileResults"].append(row)
                    continue
                roles=p.extract_staffing_roles(text,f["name"],f["url"])
                row.update(status="PARSED",chars=len(text),roleCount=len(roles),
                           relevantLines=excerpt_lines(text))
                for x in roles:
                    signature=(x["role"],x["grade"],x["count"],x["sourceFile"],x.get("onsite"))
                    if signature in seen_roles:continue
                    seen_roles.add(signature)
                    report["roleEvidence"].append({k:x.get(k) for k in
                        ("role","grade","count","countKind","onsite","manMonths",
                         "sourceFile","sourceLine","sourceText")})
                report["realDocumentsParsed"]+=1
            except Exception as exc:
                row.update(status="SOURCE_OR_PARSER_ERROR",error=type(exc).__name__,
                           message=str(exc)[:180])
            report["fileResults"].append(row)
            print("REAL_STAFFING_FILE "+json.dumps({"case":name,**row},
                  ensure_ascii=False),flush=True)
        names=set(manifest)
        analyzed={f["name"] for f in report["fileResults"] if f["status"]=="PARSED"}
        report["manifestCoverage"]={
            "documentCount":len(names),"parsedFromManifest":len(names&analyzed),
            "unparsedNames":list(names-analyzed)[:20]}
        report["verified"]=(bool(names) and names.issubset(analyzed) and
                            len(ordered)<=24)
        report["status"]="ALL_MANIFEST_SOURCE_PARSED" if report["verified"] else (
            "PARTIAL_REAL_SOURCE_PARSED" if report["realDocumentsParsed"]
            else "NO_REAL_SOURCE_PARSED")
        all_results.append(report)
    for result in all_results:
        print("REAL_STAFFING_REPORT "+json.dumps(result,ensure_ascii=False),flush=True)
    print("REAL_STAFFING_SUMMARY "+json.dumps({"realParsedCases":sum(
        x["realDocumentsParsed"]>0 for x in all_results),
        "completeCases":sum(x["verified"] for x in all_results),
        "cases":len(all_results)},ensure_ascii=False),flush=True)

if __name__=="__main__":
    run()
