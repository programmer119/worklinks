"""Fast live audit of essential KIMSE institution listings without browser automation.

A status=ok means a real list of official detail URLs was extracted.
Statuses degraded/missing are never reported as no available notices.
"""
from __future__ import annotations
import json
import os
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from pathlib import Path
from bs4 import BeautifulSoup
import requests

from worklinks_priority_health import SOURCES, KST, HEADERS, observed_links, coverage_summary

def probe(source):
    name, url, kind=source
    result={"name":name,"url":url,"status":"error","articleLinks":0,"relevantLinks":0,"discovered":0,"undatedCandidates":0,"detailErrors":0}
    try:
        resp=requests.get(url,timeout=9,headers=HEADERS)
        resp.raise_for_status()
        if len(resp.content)>3_000_000:
            raise ValueError("oversized listing")
        soup=BeautifulSoup(resp.text,"html.parser")
        links,count=observed_links(soup,url,kind)
        result.update(articleLinks=count,relevantLinks=len(links),
                      status="ok" if count>0 else "partial",
                      sampleTitles=[x["title"] for x in links[:4]])
        if count==0:result["note"]="official list accessible but notice links not extracted"
    except Exception as ex:
        result["error"]=str(ex)[:220]
    return result

def main():
    with ThreadPoolExecutor(max_workers=8) as pool:
        states=list(pool.map(probe,SOURCES))
    summary=coverage_summary(states,[source[0] for source in SOURCES])
    print(json.dumps({"generatedAt":dt.datetime.now(KST).isoformat(timespec="seconds"),
                      "coverage":summary,"results":states},ensure_ascii=False,indent=2))
    path=os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a",encoding="utf-8") as f:
            f.write("### Critical KIMSE source — live listing audit\\n\\n")
            f.write("| Source | Status | Article links | Relevant links |\\n|---|---|---:|---:|\\n")
            for item in states:
                f.write(f"| {item['name']} | {item['status']} | {item['articleLinks']} | {item['relevantLinks']} |\\n")
            f.write(f"\\nWarnings: {len(summary['degraded'])} / {len(SOURCES)}. 0 captured links is NOT 0 opportunities.\\n")
    if summary["healthy"]==0:
        print("::error title=Critical source listings inaccessible::All sources degraded, manual recovery required")
        return 1
    if summary["degraded"]:
        print("::warning title=Critical source listing gaps::"+", ".join(summary["degraded"]))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
