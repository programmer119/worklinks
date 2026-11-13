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
from staffing_facts import extract_staffing_facts

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
        if "북한정보분석시스템" in title:
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
                            count=docs.get("count"),
                            names=[str(x.get("name") or "") for x in docs.get("items") or []])
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
        if not manifest and meta.get("ok") and meta.get("complete"):
            manifest=meta.get("names") or []
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
                row.update(bytes=len(raw),sha256=newsha,sha256prefix=newsha[:16],
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
                # Focused official-source diagnostic. Print role table context,
                # not the full proposal or unrelated personal information.
                if (name=="yongin" and "공내역서" in f["name"]):
                    print("STAFFING_TABLE_DIAG "+json.dumps({
                        "case":name,"file":f["name"],"allLines":text.splitlines()[:90]
                    },ensure_ascii=False),flush=True)
                if ((name=="north" or name=="exercise") and "제안요청서" in f["name"]):
                    lines=text.splitlines()
                    terms=re.compile(
                        r"월평균.{0,12}인력|총\s*8\s*명|PM\s*[0-9]|PL\s*[0-9]|"
                        r"인원\s*(?:수|구성|계획)|포털\s*개발|AI\s*전문|"
                        r"상주\s*인력|전문\s*기술\s*인력|투입.{0,12}인원|"
                        r"분야별\s*인원|인력\s*구성",re.I)
                    indices=[i for i,line in enumerate(lines) if terms.search(line)]
                    # Inspect the full extracted staffing table region rather
                    # than the first broad keyword matches.
                    spans=([(825,900)] if name=="north" else [(325,365),(645,673)])
                    table=[{"line":i+1,"text":" ".join(lines[i].split())[:330]}
                           for low,high in spans
                           for i in range(max(0,low-1),min(len(lines),high))
                           if lines[i].strip()]
                    print("STAFFING_TABLE_REGION "+json.dumps({
                        "case":name,"file":f["name"],"lines":table
                    },ensure_ascii=False),flush=True)
                    excerpts=[{"line":i+1,"context":" | ".join(
                        " ".join(z.split())[:250] for z in lines[max(0,i-1):i+2]
                    )[:620]} for i in indices[:38]]
                    print("STAFFING_TABLE_DIAG "+json.dumps({
                        "case":name,"file":f["name"],"matches":len(indices),
                        "excerpts":excerpts
                    },ensure_ascii=False),flush=True)
                facts=extract_staffing_facts(text,f["name"],f["url"])
                roles=p.extract_staffing_roles(text,f["name"],f["url"])
                row.update(status="PARSED",chars=len(text),roleCount=len(roles),
                           facts=[{k:v for k,v in x.items() if k!="sourceUrl"} for x in facts],
                           relevantLines=excerpt_lines(text))
                for x in roles:
                    signature=(x["role"],x["grade"],x["count"],x["sourceFile"],x.get("onsite"))
                    if signature in seen_roles:continue
                    seen_roles.add(signature)
                    report["roleEvidence"].append({k:x.get(k) for k in
                        ("role","grade","count","countKind","onsite","manMonths",
                         "sourceFile","sourceLine","sourceText")})
                report.setdefault("facts",[]).extend(facts)
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
        kinds=[x.get("kind") for x in report.get("facts") or []]
        if name=="yongin":
            report["factsOk"]=bool(
                "workload_total" in kinds and
                len([f for f in report.get("facts") or []
                     if f["kind"]=="workload_role"])>=5 and
                any(abs(f.get("manMonths",0)-11.522)<.0001
                    for f in report.get("facts") or []
                    if f["kind"]=="workload_total"))
        elif name=="north":
            report["factsOk"]=bool(
                any(x.get("kind")=="headcount_recommended" and
                    x.get("count")==8 and x.get("mandatory") is False
                    for x in report.get("facts") or []) and
                len([x for x in report.get("facts") or []
                     if x.get("kind")=="role_unspecified"])>=4)
        else:
            report["factsOk"]=any(
                x.get("kind")=="staffing_plan_required" and
                x.get("headcount") is None
                for x in report.get("facts") or [])
        all_results.append(report)
    for result in all_results:
        print("REAL_STAFFING_REPORT "+json.dumps(result,ensure_ascii=False),flush=True)
    print("REAL_STAFFING_SUMMARY "+json.dumps({"factsOkCases":sum(x.get("factsOk") is True for x in all_results),
        "realParsedCases":sum(
        x["realDocumentsParsed"]>0 for x in all_results),
        "completeCases":sum(x["verified"] for x in all_results),
        "cases":len(all_results)},ensure_ascii=False),flush=True)
    if sum(x.get("factsOk") is True for x in all_results)!=3:
        raise SystemExit("REAL_STAFFING_FACTS_INCOMPLETE")

if __name__=="__main__":
    run()
