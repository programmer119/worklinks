#!/usr/bin/env python3
"""Source-bound inventory of OPEN Changcom bids, API status and RFP file completeness.

This is an ENRICHMENT queue, not a bidder-eligibility ruling. Never convert
missing/failed official API data into a 'no restriction' assertion.
"""
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "startup-support"
OUT = BASE / "audits"
OUT.mkdir(parents=True,exist_ok=True)
PRIOR_IDS = ("R26BK01816467:000", "R26BK01816907:000", "R26BK01804703:000")

def read(name):
    doc=json.loads((BASE/name).read_text(encoding="utf-8"))
    if not isinstance(doc,dict) or doc.get("ok") is not True:
        raise RuntimeError("incomplete_source:"+name)
    return doc

def rfp_state(record):
    if not isinstance(record,dict) or not record:
        return "not_scanned"
    if record.get("status") != "text_extracted_requires_review":
        return "no_readable_text:"+str(record.get("status") or "unknown")
    files=record.get("files") or []
    if record.get("manifestChangePending"):
        return "manifest_change_pending"
    if int(record.get("unreadableDocumentCount") or 0)>0:
        return "attachments_unreadable"
    if files and any(not f.get("sourceTextScanComplete") for f in files):
        return "qualification_excerpt_incomplete"
    if files and any(f.get("qualificationScanTruncated") for f in files):
        return "qualification_excerpt_truncated"
    if record.get("manifestComplete") is False:
        return "manifest_incomplete"
    if record.get("manifestComplete") is None:
        return "manifest_status_unknown_legacy"
    if not files or int(record.get("readableDocumentCount") or 0)<=0:
        return "source_count_inconsistent"
    return "text_scanned_all_files_not_legally_reviewed"

def main():
    bids=read("changcom-actionable.json")
    coverage=read("rfp-coverage-index.json")
    if bids.get("bizno")!="1308185973":
        raise RuntimeError("wrong_company")
    rows=bids.get("bids")
    indexed=coverage.get("byNotice")
    if not isinstance(rows,list) or len(rows)<50 or not isinstance(indexed,dict):
        raise RuntimeError("incomplete_candidate_or_rfp_index")
    output=[];count=Counter();by_error=Counter();seen=set()
    for bid in rows:
        if bid.get("deadlineState") not in ("open","unknown"):continue
        key=str(bid.get("bidNo") or "")+":"+str(bid.get("order") or "000").zfill(3)
        if key in seen:raise RuntimeError("duplicate_bid:"+key)
        seen.add(key)
        source=indexed.get(key) or {}
        status=rfp_state(source)
        screening=str(bid.get("screening") or "unknown")
        missing=[]
        for name,label in (("title","공고명"),("org","발주기관"),("budget","예산")):
            val=str(bid.get(name) or "").strip()
            if not val or (name=="budget" and not val.isdigit()):missing.append(label)
        if bid.get("deadlineState")=="unknown" or not bid.get("closes"):missing.append("마감시각")
        license_state=("confirmed_basic_code_match" if screening=="published_industry_codes_match" else
                       "needs_official_license_api_or_rule_review" if screening in (
                          "official_license_unavailable","official_license_ambiguous",
                          "industry_rule_conflict_review") else
                       "no_published_license_restriction_detected_unverified" if screening=="no_license_restriction_detected"
                       else "unknown")
        supplement=bid.get("supplementalBidFacts") or {}
        extra=str(supplement.get("state") or "not_collected")
        record={
            "공고번호":key,
            "공고명":str(bid.get("title") or ""),
            "마감":str(bid.get("closes") or ""),
            "예산":str(bid.get("budget") or ""),
            "기본공고누락필드":";".join(missing),
            "업종API기본판정":license_state,
            "업종API상태":screening,
            "업종조회시각":str(bid.get("industryCheckedAt") or ""),
            "선택API추가정보":extra,
            "RFP상태":status,
            "RFP마지막추출":str(source.get("checkedAt") or ""),
            "RFP첨부전체":str(source.get("attachmentManifestCount") or ""),
            "RFP판독":str(source.get("readableDocumentCount") or 0),
            "RFP미판독":str(source.get("unreadableDocumentCount") or 0),
            "RFP최종오류":str(source.get("reasonCode") or source.get("lastAttemptStatus") or ""),
            "첨부별오류":";".join(sorted({str(f.get("errorCategory")) for f in source.get("files") or []
                         if not f.get("readable") and f.get("errorCategory")})),
            "원문수집완료와법적검토구분":"법적적격 미확정",
        }
        output.append(record)
        count["active"]+=1
        count["rfp_"+status]+=1
        count["license_"+license_state]+=1
        count["extra_"+extra]+=1
        if missing:count["missing_core_notice_fields"]+=1
        if status!="text_scanned_all_files_not_legally_reviewed":count["rfp_needs_followup"]+=1
        if license_state=="needs_official_license_api_or_rule_review":count["license_needs_followup"]+=1
        if extra!="collected":count["supplemental_not_complete_or_missing"]+=1
        if key in PRIOR_IDS:count["previous_recommendations_present"]+=1
        for f in source.get("files") or []:
            if not f.get("readable"):
                by_error[str(f.get("errorCategory") or "unknown")]+=1
    if len(output)!=len(rows):
        raise RuntimeError("non_open_bid_present")
    csvfile=OUT/"changcom-live-information-gaps-20261111.csv"
    with csvfile.open("w",encoding="utf-8-sig",newline="") as out:
        writer=csv.DictWriter(out,fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    summary=[
        "# 창컴 마감 전 후보 API·RFP 데이터 완전성 점검",
        "",
        "생성 기준: "+str(bids.get("generatedAt")),
        "",
        "이 보고서는 **원문 수집 상태**만 점검하며 투찰 자격의 법적 확정이 아니다.",
        "API 정보 누락은 '제한 없음'이 아니고, 파일 일부 텍스트 판독은 RFP 전체 검토 완료가 아니다.",
        "",
        "## 집계",
        "",
        "| 상태 | 건수 |","|---|---:|",
        *("| "+label+" | "+str(value)+" |" for label,value in sorted(count.items())),
        "",
        "## 판독 실패 세부 원인",
        "",
        "| 에러 코드 | 파일 수 |","|---|---:|",
        *("| "+k+" | "+str(v)+" |" for k,v in by_error.most_common(30)),
        "",
        "## 과거 유망 후보 세 건",
        "",
    ]
    sourceByKey={x["공고번호"]:x for x in output}
    for key in PRIOR_IDS:
        if key in sourceByKey:
            entry=sourceByKey[key]
            summary.append("- "+key+" : "+entry["공고명"]+
                           " / API "+entry["업종API상태"]+" / RFP "+entry["RFP상태"])
        else:
            summary.append("- "+key+" : 현재 창컴 후보 목록에 없음 (별도 복원 대상)")
    summary+=["", "## 세부 목록","",
        "[전수 CSV](changcom-live-information-gaps-20261111.csv) — 공고별 필드 누락, API 신뢰 상태, RFP 첨부 수 및 미판독 원인.",
        "",
        "수집 배치 상한은 API 전체 사용량에 맞춰 별도 조정해야 하며, 실패 또는 파일 용량 초과를 단순 반복 요청으로 해결할 수 없다.",
    ]
    (OUT/"changcom-live-information-gaps-20261111.md").write_text(
        "\n".join(summary)+"\n",encoding="utf-8")
    print("CHANGCOM_LIVE_DATA_AUDIT",json.dumps(dict(count),ensure_ascii=False))
    print("CHANGCOM_LIVE_RFP_FILE_ERRORS",json.dumps(dict(by_error),ensure_ascii=False))
    print("CHANGCOM_LIVE_AUDIT_FILES",csvfile)
if __name__=="__main__":main()
