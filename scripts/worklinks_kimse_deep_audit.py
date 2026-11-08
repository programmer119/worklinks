#!/usr/bin/env python3
"""Independent, evidence-only KIMSE deep audit of observed official notices.

This audit never treats an HTML 200, an event date, or the occurrence of an
eligibility keyword as proof that an application is open or permitted.
It does not modify the main WorkLinks support list or applied/hidden records.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import requests
import time
from urllib.parse import urljoin, urlsplit, parse_qs

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from worklinks_priority_health import (
    HEADERS, KST, SOURCES, clean, eligibility_signal, explicit_deadline,
    kimse_fit, observed_links, observed_listing_pages, row_deadline,
    verified_public_get, valid_official_link,
)

from worklinks_health_sources import (
    SOURCES as KHIS_SOURCES, candidate_links, application_deadline,
    official_rss_listing, KHIS_TENDER_RSS,
)
ALL_SOURCES=tuple(SOURCES)+tuple(KHIS_SOURCES)

ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT=ROOT/"startup-support/investment-opportunities.json"
OUTPUT=ROOT/"startup-support/kimse-deep-audit.json"
MAX_PAGES_PER_SOURCE=80
MAX_DETAILS=250
MAX_RUNTIME_SECONDS=900
MAX_LISTING_SECONDS=470
KHIDI_SEM=threading.BoundedSemaphore(2)
OFFICIAL_HOSTS={urlsplit(url).hostname for _,url,_ in ALL_SOURCES}
START=time.monotonic()

def utc_now():
    return dt.datetime.now(KST)

def read_snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))

def get_soup(url):
    hostname=urlsplit(url).hostname
    if hostname not in OFFICIAL_HOSTS:
        raise ValueError("Non-official URL rejected")
    def do_get():
        response=verified_public_get(url, headers=HEADERS, timeout=(5,10))
        response.raise_for_status()
        if urlsplit(getattr(response,"url",url)).hostname != hostname:
            raise ValueError("Cross-host redirect")
        if len(response.content)>3_000_000:
            raise ValueError("Official HTML response too large")
        return BeautifulSoup(response.text,"html.parser")
    if hostname in ("www.khidi.or.kr","khidi.or.kr"):
        with KHIDI_SEM:
            return do_get()
    if url==KHIS_SOURCES[1][1]:
        try:
            return do_get()
        except requests.RequestException:
            feed=verified_public_get(KHIS_TENDER_RSS,headers=HEADERS,timeout=(5,10))
            feed.raise_for_status()
            if urlsplit(getattr(feed,"url",KHIS_TENDER_RSS)).hostname!=hostname:
                raise ValueError("KHIS feed cross-host redirect")
            return official_rss_listing(feed.content)
    return do_get()

def source_entries(soup,base,kind):
    if kind in ("0001","0009"):
        entries=candidate_links(soup,base,kind)
        return [{"url":url,"title":title,"context":""}
                for url,(title,_) in entries.items()],len(entries)
    return observed_links(soup,base,kind)


def crawl_source(source, fetch=get_soup, page_cap=MAX_PAGES_PER_SOURCE):
    """Never manufacture a page number; only follow links seen in real HTML."""
    name,base,kind=source
    visited=set()
    pending=[base]
    queued={base}
    rows={}
    failed=[]
    page_rows=[]
    while pending and len(visited)<page_cap:
        if time.monotonic()-START>MAX_LISTING_SECONDS:
            break
        url=pending.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            soup=fetch(url)
            entries,count=source_entries(soup,url,kind)
            page_rows.append({"url":url,"articleLinks":count,
                              "matchingNotices":len(entries)})
            for item in entries:
                rows.setdefault(item["url"],{**item,"source":name,"kind":kind,
                                               "listingEvidence":url})
            for next_page in observed_listing_pages(soup,url):
                if next_page not in queued:
                    pending.append(next_page)
                    queued.add(next_page)
        except Exception as exc:
            failed.append({"url":url,"error":type(exc).__name__+": "+clean(exc,150)})
    # Queued-but-unvisited pages and failed ones are all explicitly unresolved.
    return {"source":name,"board":base,"visited":len(visited),
            "observedPages":page_rows,"pendingPages":pending,
            "failedPages":failed,"candidates":list(rows.values())}

def likely_historical(title, clock):
    """Historical triage only; never assert that application has closed."""
    years=[int(v) for v in re.findall(r"(?<!\d)(20[12]\d)(?!\d)",title)]
    return bool(years) and max(years)<clock.year

def signed_date_from_title(title):
    """Only a full year-month-day explicitly next to an application-end label."""
    m=re.search(
        r"(?:접수\s*마감|신청\s*마감|모집\s*마감|마감일|접수기한)"
        r"\s*[:：]?\s*(20\d{2})[.\-/년 ]+\s*(\d{1,2})[.\-/월 ]+\s*(\d{1,2})",
        title,re.I,
    )
    if not m:
        return None
    try:
        return dt.date(int(m[1]),int(m[2]),int(m[3])).isoformat()
    except ValueError:
        return None

def validated_detail_target(url,source):
    base=source[1]
    kind=source[2]
    if kind in ("0001","0009"):
        p=urlsplit(url)
        q=parse_qs(p.query)
        mid="a10301000000" if kind=="0001" else "a10304000000"
        return (p.scheme=="https" and p.hostname=="www.khis.kr"
            and p.path=="/board.es" and q.get("act")==["view"]
            and q.get("bid")==[kind] and q.get("mid")==[mid]
            and len(q.get("list_no",[]))==1
            and bool(re.fullmatch(r"\d{1,8}",q["list_no"][0])))
    return valid_official_link(url,base,kind)==url

def examine(entry, source, now, fetch=get_soup):
    url=entry["url"]
    title=entry["title"]
    record={"id":hashlib.sha1(url.encode()).hexdigest()[:18],
            "title":title,"url":url,"source":source[0],
            "kimseFit":kimse_fit(title),
            "eligibility":"자격 확인 필요","eligibilityEvidence":"원문·첨부 근거 필요",
            "applicationDeadline":None,"status":"unknown_deadline",
            "evidence":entry.get("listingEvidence","previous_verified_snapshot"),
            "attachmentLinks":[],"checkedAt":now.isoformat(timespec="seconds")}
    if not validated_detail_target(url,source):
        record.update(status="invalid_official_link",detailError="Official article URL mismatch")
        return record
    # A verified dedicated application-period column may suffice, but not
    # a date that is merely the event, post, or overall project end.
    deadline=row_deadline(entry.get("context",""),source[2])
    if not deadline:
        deadline=signed_date_from_title(title)
    if not deadline:
        try:
            page=fetch(url)
            section=(page.select_one("article") or page.select_one(".board_view")
                     or page.select_one(".view") or page.select_one("main") or page)
            body=section.get_text("\n",strip=True)[:40000]
            deadline=explicit_deadline(body)
            if not deadline and source[2] in ("0001","0009"):
                deadline=application_deadline(title,body)
            eligibility,proof=eligibility_signal(body)
            record["eligibility"]=eligibility
            record["eligibilityEvidence"]=proof
            record["detailExcerpt"]=clean(body,450)
            attachments=[]
            for a in section.select("a[href]"):
                href=a.get("href","")
                link=urljoin(url,href)
                host=urlsplit(link).hostname
                if host in OFFICIAL_HOSTS and re.search(
                    r"\.(?:pdf|hwp|hwpx|docx?|zip|xlsx?)(?:[?#]|$)",link,re.I
                ):
                    attachments.append(link[:500])
            record["attachmentLinks"]=list(dict.fromkeys(attachments))[:12]
        except Exception as exc:
            record.update(status="access_failed",
                          detailError=type(exc).__name__+": "+clean(exc,180))
            return record
    if deadline:
        try:
            end=dt.datetime.fromisoformat(
                deadline if "T" in deadline else deadline+"T23:59:59+09:00")
        except ValueError:
            record["status"]="invalid_deadline"
            return record
        record["applicationDeadline"]=deadline
        record["status"]="expired_confirmed" if end<now else "deadline_verified_eligibility_pending"
        return record
    record["status"]="historical_unverified" if likely_historical(title,now) else "unknown_deadline"
    return record

def run(snapshot, now=None, crawl=crawl_source, examine_one=examine):
    now=now or utc_now()
    sources={spec[0]:spec for spec in ALL_SOURCES}
    evidence={}
    audits=[]
    with cf.ThreadPoolExecutor(max_workers=5) as listing_pool:
        listing_futures={listing_pool.submit(crawl,spec):spec for spec in ALL_SOURCES}
        for future in cf.as_completed(listing_futures):
            spec=listing_futures[future]
            try:
                item=future.result()
            except Exception as exc:
                item={"source":spec[0],"board":spec[1],"visited":0,
                      "observedPages":[],"pendingPages":[spec[1]],
                      "failedPages":[{"url":spec[1],
                       "error":type(exc).__name__+": "+clean(exc,160)}],
                      "candidates":[]}
            audits.append({key:value for key,value in item.items() if key!="candidates"})
            for row in item["candidates"]:
                evidence.setdefault(row["url"],row)
    # Existing verified official links are retained as previous-run evidence,
    # not misreported as new discoveries.
    for row in snapshot.get("opportunities",[]):
        spec=sources.get(row.get("source"))
        if spec and validated_detail_target(str(row.get("url","")),spec):
            evidence.setdefault(row["url"],{"url":row["url"],
                "title":row["title"],"context":row.get("description",""),
                "source":row["source"],"kind":spec[2],
                "listingEvidence":"previous_verified_snapshot"})
    backlog=sorted(evidence.values(),key=lambda x:(
        0 if kimse_fit(x["title"])=="높음" else 1,
        1 if likely_historical(x["title"],now) else 0,
        0 if x.get("listingEvidence")!="previous_verified_snapshot" else 1,
        x["title"]))
    # Keep direct KIMSE opportunities in every scan. Rotate lower-priority
    # notices so older candidates cannot remain permanently unexamined.
    direct=[x for x in backlog if kimse_fit(x["title"])=="높음"]
    remainder=[x for x in backlog if kimse_fit(x["title"])!="높음"]
    slots=max(0,MAX_DETAILS-len(direct))
    if remainder and slots:
        rotation=((now.date().toordinal()*2)+(now.hour>=12))*max(1,slots)
        offset=rotation%len(remainder)
        remainder=remainder[offset:]+remainder[:offset]
    targets=(direct+remainder)[:MAX_DETAILS]
    target_urls={x["url"] for x in targets}
    results=[]
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        future_map={pool.submit(examine_one,row,sources[row["source"]],now):
                     row for row in targets}
        for future in cf.as_completed(future_map):
            row=future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"title":row["title"],"url":row["url"],
                     "source":row["source"],"status":"audit_error",
                     "detailError":type(exc).__name__+": "+clean(exc,160)})
    unexamined=[{"title":x["title"],"url":x["url"],"source":x["source"]}
                for x in backlog if x["url"] not in target_urls]
    counts={}
    for record in results:
        counts[record["status"]]=counts.get(record["status"],0)+1
    return {"schemaVersion":1,"generatedAt":now.isoformat(timespec="seconds"),
            "sourceSnapshotAt":snapshot.get("generatedAt"),
            "sources":audits,"results":results,
            "unexamined":unexamined,
            "summary":{"sources":len(audits),
                "pagesActuallyRead":sum(s["visited"] for s in audits),
                "pageErrors":sum(len(s["failedPages"]) for s in audits),
                "pagesPending":sum(len(s["pendingPages"]) for s in audits),
                "uniqueOfficialCandidateUrls":len(backlog),
                "detailExamined":len(results),"detailUnexamined":len(unexamined),
                "outcomes":counts,
                "fullyVerified":False},
            "notice":"A deadline alone does not prove eligibility; attachment and application requirements remain unverified."}

def main():
    data=run(read_snapshot())
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    temp=OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(OUTPUT)
    print(json.dumps(data["summary"],ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
