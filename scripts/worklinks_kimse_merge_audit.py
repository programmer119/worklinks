"""Merge only independently verified KIMSE deadlines into WorkLinks safely.

A deep audit does not establish the applicant's eligibility. Every candidate
stays marked as requiring eligibility confirmation until source documents prove
otherwise. This module never writes application/hidden/applied state.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re
from urllib.parse import parse_qs, urlsplit

from worklinks_priority_health import SOURCES, valid_official_link
from worklinks_health_sources import SOURCES as KHIS_SOURCES

KST=dt.timezone(dt.timedelta(hours=9))
SPECS={spec[0]:spec for spec in SOURCES+KHIS_SOURCES}
ACCEPTED={"expired_confirmed","deadline_verified_eligibility_pending"}

def safe_official_url(url,source):
    spec=SPECS.get(source)
    if not spec or not url or not isinstance(url,str):
        return False
    if spec[2] not in ("0001","0009"):
        return valid_official_link(url,spec[1],spec[2])==url
    p=urlsplit(url)
    q=parse_qs(p.query)
    board=spec[2]
    mid="a10301000000" if board=="0001" else "a10304000000"
    return (p.scheme=="https" and p.hostname=="www.khis.kr"
        and p.path=="/board.es" and q.get("act")==["view"]
        and q.get("bid")==[board] and q.get("mid")==[mid]
        and len(q.get("list_no",[]))==1
        and bool(re.fullmatch(r"\d{1,8}",q["list_no"][0])))

def stamp(value):
    try:
        result=dt.datetime.fromisoformat(str(value))
        return result if result.tzinfo else None
    except (TypeError,ValueError):
        return None

def safe_deadline(value):
    try:
        if not isinstance(value,str):
            return None
        if len(value)==10:
            return dt.datetime.fromisoformat(value+"T23:59:59+09:00")
        return dt.datetime.fromisoformat(value)
    except (ValueError,TypeError):
        return None

def merge_verified_deadlines(rows,audit,now):
    """Returns (new_rows, metadata) with proof-preserving, conservative merge."""
    if not isinstance(audit,dict) or audit.get("schemaVersion")!=1:
        return rows,{"accepted":0,"skipped":"invalid_schema"}
    checked=stamp(audit.get("generatedAt"))
    if not checked:
        return rows,{"accepted":0,"skipped":"missing_timestamp"}
    age=(now-checked).total_seconds()
    if not -600<=age<=48*3600:
        return rows,{"accepted":0,"skipped":"stale_audit"}
    original=list(rows)
    byurl={r.get("url"):r for r in original if isinstance(r,dict)}
    accepted=added=updated=conflicts=0
    for row in audit.get("results",[]):
        if not isinstance(row,dict) or row.get("status") not in ACCEPTED:
            continue
        url=row.get("url")
        source=row.get("source")
        if not safe_official_url(url,source):
            continue
        if row.get("deadlineEvidenceSource") not in (
            "official_listing_application_period",
            "official_title_explicit_cutoff",
            "official_article_application_period",
        ):
            continue
        # A previous JSON description is NOT a live observed application-
        # period column; do not upgrade that to official proof.
        if (row.get("deadlineEvidenceSource")=="official_listing_application_period"
            and row.get("evidence")=="previous_verified_snapshot"):
            continue
        date=row.get("applicationDeadline")
        cutoff=safe_deadline(date)
        if not cutoff or not cutoff.tzinfo:
            continue
        closed=cutoff<now
        # An audited "expired" state must correspond to an actual past date.
        # An audited future date may legitimately expire before this refresh.
        if row["status"]=="expired_confirmed" and not closed:
            continue
        prior=byurl.get(url)
        if prior:
            last=stamp(prior.get("lastSeenAt"))
            if last and last>checked and prior.get("deadline") and prior["deadline"]!=date:
                conflicts+=1
                continue
            if prior.get("deadline") and prior["deadline"]!=date:
                conflicts+=1
                continue
            if not prior.get("deadline"):
                prior["deadline"]=date
                prior["deadlineEvidence"]="독립 공고 정밀검사에서 신청마감 원문 확인"
                prior["reviewStatus"]="마감 확인·자격 재검증 필요"
                prior["sourceStatus"]="closed" if closed else "unknown"
                prior["review"]="접수마감 원문 확인. 상세 지원자격 및 첨부요건 재확인 필요"
                updated+=1
            accepted+=1
            continue
        sha=hashlib.sha1(url.encode()).hexdigest()[:18]
        entry={"id":"kimse-audit-"+sha,
            "title":str(row.get("title") or "")[:180],
            "url":url,"source":source,
            "category":"창업지원·공모",
            "deadline":date,"deadlineEvidence":"독립 공고 정밀검사에서 신청마감 원문 확인",
            "eligibility":"자격 확인 필요",
            "description":str(row.get("detailExcerpt") or "공식 상세공고 확인·참가요건 재검증 필요")[:400],
            "sourceKind":"공식 정밀검사·자격확인 필요",
            "sourceStatus":"closed" if closed else "unknown",
            "reviewStatus":"마감 확인·자격 재검증 필요",
            "kimseFit":str(row.get("kimseFit") or "검토"),
            "lastSeenAt":checked.isoformat(timespec="seconds"),
            "review":"원문 신청마감 검증 완료. 신청자격·필요서류 별도 검토 필요"}
        if not entry["title"]:
            continue
        original.append(entry)
        byurl[url]=entry
        accepted+=1
        added+=1
    return original,{"accepted":accepted,"added":added,"updated":updated,
                     "conflicts":conflicts,"auditGeneratedAt":checked.isoformat()}
