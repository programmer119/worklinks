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

from worklinks_priority_health import SOURCES, KST, HEADERS, observed_links, coverage_summary, verified_public_get

def probe(source):
    name, url, kind=source
    result={"name":name,"url":url,"status":"error","articleLinks":0,"relevantLinks":0,"discovered":0,"undatedCandidates":0,"detailErrors":0}
    try:
        resp=verified_public_get(url,timeout=9,headers=HEADERS)
        resp.raise_for_status()
        if len(resp.content)>3_000_000:
            raise ValueError("oversized listing")
        soup=BeautifulSoup(resp.text,"html.parser")
        links,count=observed_links(soup,url,kind)
        result.update(articleLinks=count,relevantLinks=len(links),
                      status="ok" if count>0 else "partial",
                      sampleTitles=[x["title"] for x in links[:4]])
        if count==0:
            examples=[]
            for anchor in soup.select("a")[:350]:
                title=" ".join(anchor.stripped_strings)[:95]
                if len(title)<8 or not any(token in title for token in ("AI","의료","데이터","공고","지원","공지","사업")):
                    continue
                examples.append({
                    "title":title,
                    "href":str(anchor.get("href",""))[:150],
                    "onclick":str(anchor.get("onclick",""))[:150]
                })
                if len(examples)>=10:break
            result["pageTitle"]=(soup.title.get_text(" ",strip=True) if soup.title else "")[:100]
            result["pageBytes"]=len(resp.content)
            result["suspectedArticleAnchors"]=examples
            target_phrases=["공공데이터 활용기업","2026년도 클라우드","방송영상 AI","AI 허브 민간기업"]
            snippets=[]
            for text_node in soup.find_all(string=True):
                value=str(text_node).strip()
                if not any(term in value for term in target_phrases):continue
                parent=text_node.parent
                for _ in range(2):
                    if parent and parent.parent:parent=parent.parent
                snippets.append(str(parent)[:1150] if parent else value[:200])
                if len(snippets)>=5:break
            result["noticeHtmlSnippets"]=snippets
            if kind=="nia":
                result["viewLinks"]=[
                    {"title":" ".join(a.stripped_strings)[:120],
                     "href":str(a.get("href",""))[:210],
                     "onclick":str(a.get("onclick",""))[:210]}
                    for a in soup.select('a[href*="View.do"],a[href*="view"],a[onclick]')[:38]
                ]
                result["noticeRows"]=[
                    str(tr)[:950]
                    for tr in soup.select('tr') if ("2026" in tr.get_text(" ",strip=True)
                                                or "데이터" in tr.get_text(" ",strip=True))
                ][:5]



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
    if summary["listingDegraded"]:
        print("::error title=Critical KIMSE official listing gaps::"+", ".join(summary["listingDegraded"]))
        return 1
    if summary["degraded"]:
        print("::warning title=Unverified KIMSE application details::"+", ".join(summary["degraded"]))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
