"""Independent high-priority KIMSE official-notice collector.

Covers real public source LISTS, not guessed notice IDs or UI search keywords.
Only items with verified future *application* deadlines become actionable rows.
Other relevant notices remain counted for missed-opportunity auditing.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re
import xml.etree.ElementTree as ET
from html import escape as html_escape
from urllib.parse import parse_qs, urljoin, urlsplit
import requests
import certifi
import ssl
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
from urllib.parse import urlsplit as _urlsplit
from bs4 import BeautifulSoup

KST = dt.timezone(dt.timedelta(hours=9))
MAX_DETAIL_PER_SOURCE = 24
MAX_LIST_PAGES = 4
REQUEST_TIMEOUT_SECONDS = 7
_KHIDI_LIMIT=threading.Semaphore(2)
SOURCES = (
    ("KHIDI 보건산업 사업공고", "https://www.khidi.or.kr/board?menuId=MENU01108", "khidi"),
    ("KHIDI 의료기기 지원사업", "https://www.khidi.or.kr/mdtis/bizPbanc/bizPbancList?menuId=MENU03471", "device"),
    ("KHIDI 기관별 의료·연구지원 사업", "https://www.khidi.or.kr/board?menuId=MENU01484", "khidi_external"),
    ("KHIDI 의료기기 상담·교육", "https://www.khidi.or.kr/board?menuId=MENU01491", "khidi_events"),
    ("NIA AI·데이터 공지", "https://www.nia.or.kr/site/nia_kor/ex/bbs/List.do?cbIdx=99835", "nia"),
    ("K-DATA 데이터·안심구역 공지", "https://www.kdata.or.kr/kr/board/notice_01/boardList.do", "kdata"),
    ("심평원 창업·의료데이터 소식", "https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020002000100", "hira"),
    ("AI-Hub 의료·안심존 데이터 공지", "https://www.aihub.or.kr/aihubnews/notice/list.do?currMenu=132&topMenu=103", "aihub"),
)
HEADERS = {"User-Agent":"Mozilla/5.0 (compatible; WorkLinks/1.0 public-research-monitor)",
           "Accept-Language":"ko-KR,ko;q=0.9"}
THEME = re.compile(r"치매|인지(?:저하|장애|건강)|보건|중개연구|용역연구개발|연구개발|연구과제|규제과학|IRB|DRB|연구윤리|연구비|안심구역|안심존|건강|고령|실버|에이지|바이오|헬스|의료|병원|임상|임상시험|데이터|빅데이터|음성|AI|인공지능|실증|사용적합성",re.I)
OFFER = re.compile(r"지원|모집|공모|경진|챌린지|인큐베이팅|창업|바우처|안심구역|안심존|실증|검증|활용|교육|연구|평가|멘토|컨설팅|시험|인증|사업화|장려|서비스|프로그램|신청|상담|상시접수",re.I)
IGNORE = re.compile(r"채용|합격자|선정\s*결과|제안서\s*평가\s*결과|입찰공고|낙찰|수의계약|용역\s*발주|운영\s*용역|대행\s*용역|부처\s*업무보고|보도자료\s*발표|공개검증\s*대상",re.I)
PATIENT = re.compile(r"당번\s*약국|문여는\s*약국|의료비\s*지원\s*대상|치매\s*치료\s*관리비",re.I)
APPLICATION = re.compile(r"(?:접수|신청|모집|응모|제출|공모|공고)\s*(?:기간|기한|마감|일정|일시)\s*[:：]?\s*",re.I)
DAY = re.compile(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})(?:일)?")
TIME = re.compile(r"(?<!\d)([012]?\d):([0-5]\d)(?!\d)")
DATE_IN_ROW = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
KDATA_DETAIL = re.compile(r"^/kr/board/notice_01/boardView\.do$",re.I)
SOURCE_IDS = {name for name,_,_ in SOURCES}

def clean(v,limit=300):
    return re.sub(r"\s+"," ",str(v or "")).strip()[:limit]

def match_notice(title):
    title=clean(title,220)
    return len(title)>=9 and bool(THEME.search(title)) and bool(OFFER.search(title)) and not IGNORE.search(title) and not PATIENT.search(title)

def valid_official_link(href,base,kind):
    """Use only links actually observed in source HTML, never guess IDs."""
    if not href or href.lower().startswith(("javascript:","#","mailto:")):
        return None
    url=urljoin(base,href)
    p=urlsplit(url)
    if p.scheme!="https":return None
    q=parse_qs(p.query)
    host=p.hostname
    if kind=="khidi" and host in ("khidi.or.kr","www.khidi.or.kr") and p.path=="/board/view":
        ids=q.get("linkId",[])
        if q.get("menuId")!=["MENU01108"] or len(ids)!=1 or not re.fullmatch(r"\d{6,12}",ids[0]):
            return None
        return f"https://www.khidi.or.kr/board/view?menuId=MENU01108&linkId={ids[0]}"
    if kind in ("khidi_external","khidi_events") and host in ("khidi.or.kr","www.khidi.or.kr") and p.path=="/board/view":
        expected="MENU01484" if kind=="khidi_external" else "MENU01491"
        ids=q.get("linkId",[])
        if q.get("menuId")!=[expected] or len(ids)!=1 or not re.fullmatch(r"\d{6,12}",ids[0]):
            return None
        return f"https://www.khidi.or.kr/board/view?menuId={expected}&linkId={ids[0]}"
    if kind=="device" and host in ("khidi.or.kr","www.khidi.or.kr") and p.path=="/mdtis/bizPbanc/bizPbancView":
        a=q.get("biz_pbanc_id",[]);b=q.get("biz_pbanc_no",[])
        if len(a)!=1 or len(b)!=1 or not re.fullmatch(r"[A-Za-z0-9_-]{3,40}",a[0]) or not re.fullmatch(r"\d{1,8}",b[0]):
            return None
        return f"https://www.khidi.or.kr/mdtis/bizPbanc/bizPbancView?menuId=MENU03471&biz_pbanc_id={a[0]}&biz_pbanc_no={b[0]}"
    if kind=="nia" and host in ("www.nia.or.kr","nia.or.kr") and p.path.endswith("/ex/bbs/View.do"):
        ids=q.get("bcIdx",[])
        if q.get("cbIdx")!=["99835"] or len(ids)!=1 or not re.fullmatch(r"\d{4,10}",ids[0]):
            return None
        return f"https://www.nia.or.kr/site/nia_kor/ex/bbs/View.do?cbIdx=99835&bcIdx={ids[0]}"
    if kind=="kdata" and host in ("www.kdata.or.kr","kdata.or.kr") and KDATA_DETAIL.match(p.path):
        ids=q.get("bbsIdx",[])
        if len(ids)!=1 or not re.fullmatch(r"\d{2,12}",ids[0]):
            return None
        return f"https://www.kdata.or.kr/kr/board/notice_01/boardView.do?bbsIdx={ids[0]}"
    if kind=="aihub" and host in ("aihub.or.kr","www.aihub.or.kr") and p.path=="/aihubnews/notice/view.do":
        sn=q.get("nttSn",[])
        if len(sn)!=1 or not re.fullmatch(r"\d{2,8}",sn[0]):
            return None
        return f"https://www.aihub.or.kr/aihubnews/notice/view.do?nttSn={sn[0]}&currMenu=132&topMenu=103"
    if kind=="hira" and host in ("www.hira.or.kr","hira.or.kr") and p.path=="/bbsDummy.do":
        b=q.get("brdBltNo",[])
        if len(b)!=1 or not re.fullmatch(r"\d{4,8}",b[0]):
            return None
        if q.get("brdScnBltNo")!=["4"] or q.get("pgmid")!=["HIRAA020002000100"]:return None
        return f"https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020002000100&brdScnBltNo=4&brdBltNo={b[0]}"
    return None

def observed_links(soup,base,kind):
    discovered={}
    all_valid=0
    if kind=="kdata":
        # The official K-DATA notice list uses <li onclick="fnLinkView('39049');">
        # rather than hyperlinks. IDs must be observed on actual notice rows.
        for li in soup.select("ul.bbs_list > li[onclick]"):
            script=str(li.get("onclick","")).strip()
            m=re.fullmatch(r"""fnLinkView\(['"](\d{2,12})['"]\)\s*;?""",script)
            if not m:continue
            anchor=li.select_one("p.tit a")
            if anchor is None:continue
            title=clean(anchor.get_text(" ",strip=True),200)
            title=re.sub(r"^제목\s*","",title)
            if len(title)<9:continue
            all_valid+=1
            if not match_notice(title):continue
            article=f"https://www.kdata.or.kr/kr/board/notice_01/boardView.do?bbsIdx={m[1]}"
            context=clean(li.get_text(" ",strip=True),340)
            discovered[article]={"title":title,"url":article,"context":context}
        return list(discovered.values()),all_valid
    if kind=="nia":
        # Official NIA list links use an observed onclick call rather than href:
        # doBbsFView('99835','30134','16010100','30134')
        for a in soup.select('a[onclick*="doBbsFView"]'):
            title=clean(a.get_text(" ",strip=True),200)
            script=str(a.get("onclick",""))
            m=re.search(r"""doBbsFView\(['"]99835['"]\s*,\s*['"](\d{4,10})['"]\s*,\s*['"]\d+['"]\s*,\s*['"](\d{4,10})['"]\)""",script)
            if not m or m[1]!=m[2]:continue
            all_valid+=1
            if not match_notice(title):continue
            url=f"https://www.nia.or.kr/site/nia_kor/ex/bbs/View.do?cbIdx=99835&bcIdx={m[1]}"
            tr=a.find_parent("tr")
            context=clean(tr.get_text(" ",strip=True),340) if tr else ""
            discovered[url]={"title":title,"url":url,"context":context}
        return list(discovered.values()),all_valid
    if kind=="aihub":
        # AI-Hub publishes observed article IDs in data-key, not in href.
        # Use only IDs present on official notice-row anchor elements.
        for a in soup.select("td.subject a.btnView[data-key]"):
            title=clean(a.get_text(" ",strip=True),200)
            key=str(a.get("data-key",""))
            if not re.fullmatch(r"\d{2,8}",key):
                continue
            all_valid+=1
            if not match_notice(title):continue
            url=f"https://www.aihub.or.kr/aihubnews/notice/view.do?nttSn={key}&currMenu=132&topMenu=103"
            tr=a.find_parent("tr")
            context=clean(tr.get_text(" ",strip=True),340) if tr else ""
            discovered[url]={"title":title,"url":url,"context":context}
        return list(discovered.values()),all_valid
    for a in soup.select("a[href]"):
        url=valid_official_link(a.get("href"),base,kind)
        if not url:continue
        title=clean(a.get_text(" ",strip=True),200)
        if len(title)<9:continue
        all_valid+=1
        if match_notice(title):
            tr=a.find_parent("tr")
            context=clean(tr.get_text(" ",strip=True),340) if tr else ""
            discovered[url]={"title":title,"url":url,"context":context}
    return list(discovered.values()),all_valid

SHORT_DAY = re.compile(r"(?<!\d)(\d{1,2})[./월\s]+(\d{1,2})(?:일)?(?!\d)")

def explicit_deadline(text):
    """Never turn a registration starting date or event date into an end date."""
    lines=str(text or "").splitlines()
    for i,line in enumerate(lines):
        line=clean(line,550)
        m=APPLICATION.search(line)
        if not m:continue
        tail=line[m.end():]
        # A marked application-period label on its own line may be followed
        # by the application dates on the immediately next line.
        if not DAY.search(tail) and i+1<len(lines) and not tail.strip(" :："):
            nxt=clean(lines[i+1],320)
            if re.match(r"^(?:20\d{2})[.\-/년\s]",nxt):
                tail=nxt
        dates=list(DAY.finditer(tail[:230]))
        if not dates:continue
        last=dates[-1];year,month,day=int(last[1]),int(last[2]),int(last[3])
        after=tail[last.end():last.end()+100]
        short=SHORT_DAY.search(after)
        final_offset=last.end()
        if short and re.search(r"[~～\-–]|부터",after[:short.start()+1]):
            sm,sd=int(short[1]),int(short[2])
            if sm<month:year+=1
            month,day=sm,sd
            final_offset+=short.end()
        elif len(dates)==1:
            # A lone full date is usable only if it itself is a deadline,
            # not the beginning of a partially specified application range.
            if re.search(r"[~～]|부터",after[:60]):continue
            if not re.search(r"마감|까지|기한|종료",m.group(0)+tail[:240]):continue
        try:
            date=dt.date(year,month,day)
        except ValueError:continue
        times=list(TIME.finditer(tail[final_offset:final_offset+42]))
        if times:
            t=times[-1]
            if int(t[1])>23:continue
            return date.isoformat()+f"T{int(t[1]):02d}:{int(t[2]):02d}:00+09:00"
        return date.isoformat()
    return None

def row_deadline(row,kind):
    """KHIDI medical device listing alone has a dedicated application-period column."""
    if kind!="device" or not row:return None
    tr=clean(row,500)
    dates=list(DATE_IN_ROW.finditer(tr))
    if len(dates)<2:return None
    d=dates[-1]
    try:return dt.date(int(d[1]),int(d[2]),int(d[3])).isoformat()
    except ValueError:return None

PAGE_KEYS = ("pageIndex", "pageNum", "pageNo", "page", "currentPage")


def observed_listing_pages(soup, list_url):
    """Follow only official pagination URLs actually found on the listing.
    Do not synthesize a guessed offset, page index or article ID.
    """
    root=urlsplit(list_url)
    found={}
    for link in soup.select("a[href]"):
        href=str(link.get("href",""))
        if href.lower().startswith(("javascript:","mailto:","#")):
            continue
        url=urljoin(list_url,href)
        part=urlsplit(url)
        if part.scheme!="https" or part.hostname!=root.hostname or part.path!=root.path:
            continue
        query=parse_qs(part.query)
        valid_pages=[int(v) for k in PAGE_KEYS for v in query.get(k,[])
                     if re.fullmatch(r"\d{1,3}",v) and 2<=int(v)<=100]
        if len(valid_pages)!=1:
            continue
        # Ignore unrelated categories or board IDs.
        baseline=parse_qs(root.query)
        if any(key in query and query[key]!=value for key,value in baseline.items()
               if key not in PAGE_KEYS and key not in ("maxIndex","minIndex")):
            continue
        found.setdefault(valid_pages[0],url)
    return [found[k] for k in sorted(found)]


def kimse_fit(title, detail=""):
    """Triage priority, not a claim of application eligibility."""
    value=clean(title,220)+" "+clean(detail,900)
    if re.search(r"치매|경도.?인지|인지.?저하|인지.?기능|고령|노인|돌봄|실버|에이지|기억|의료데이터|보건의료데이터|의료 AI|의료.?인공지능|병원.?실증|안심구역|안심존|임상|IRB|DRB",value,re.I):
        return "높음"
    if re.search(r"의료|보건|헬스|바이오|데이터|AI|인공지능|연구|실증|창업",value,re.I):
        return "검토"
    return "기타"


def eligibility_signal(detail):
    """Return only explicit requirements mentioned in visible source text."""
    value=clean(detail,4000)
    if re.search(r"예비창업자\s*(?:및|또는|포함|지원\s*가능|신청\s*가능|참여\s*가능)",value):
        return "예비 언급·조건 확인","예비창업자 포함 문구 확인, 나머지 조건은 별도 검증"
    if re.search(r"(?:신청|지원|참여)\s*(?:자격|대상).{0,100}(?:법인사업자|개인사업자|사업자등록증\s*필수)",value):
        return "사업자 필수","신청대상에 사업자 요건 명시; 상세 예외 확인 필요"
    return "자격 확인 필요","사업자·업력·IRB·지역 및 협력기관 조건 검증 필요"


def review_record(entry, name, stamp, reason, detail="", deadline=None):
    value=entry["title"]
    uid=hashlib.sha1(entry["url"].encode()).hexdigest()[:18]
    eligibility, proof=eligibility_signal(detail)
    return {"id":"priority-health-"+uid,"title":value,"url":entry["url"],
            "category":"창업지원·공모","source":name,"deadline":deadline,
            "description":clean(detail,400) or clean(entry.get("context"),340) or
                          "공식 목록에서 확인, 상세 공고 재검증 필요",
            "eligibility":eligibility,"eligibilityEvidence":proof,
            "kimseFit":kimse_fit(value,detail),
            "reviewStatus":reason,"review":"재검증 필요: "+reason+" · "+proof,
            "sourceKind":"공식 게시글 후보·신청 가능 여부 미확인",
            "sourceStatus":"unknown","lastSeenAt":stamp}


def scan_one(source,fetch,now):
    name,url,kind=source
    stamp=now.isoformat(timespec="seconds")
    state={"name":name,"url":url,"status":"error","discovered":0,"checkedAt":stamp,
           "articleLinks":0,"relevantLinks":0,"undatedCandidates":0,
           "detailErrors":0,"expiredCandidates":0,
           "candidateLimit":MAX_DETAIL_PER_SOURCE,"pagesScanned":0,
           "pagesPending":0,"uninspectedCandidates":0}
    try:
        soup=fetch(url)
    except Exception as exc:
        state["error"]=clean(type(exc).__name__+": "+str(exc),200)
        return [],state
    pages=[(url,soup)]
    seen_pages={url}
    queue=observed_listing_pages(soup,url)
    if len(queue)>MAX_LIST_PAGES-1:
        # Scan page 2 every time; rotate the other *observed* page links
        # across runs so pages 5-10 are not permanently starved.
        first,rest=queue[0],queue[1:]
        rotation=(now.date().toordinal()*2+(now.hour>=12))%len(rest)
        queue=[first]+rest[rotation:]+rest[:rotation]
    while queue and len(pages)<MAX_LIST_PAGES:
        page_url=queue.pop(0)
        if page_url in seen_pages:
            continue
        seen_pages.add(page_url)
        try:
            page=fetch(page_url)
        except Exception:
            state["detailErrors"]+=1
            continue
        pages.append((page_url,page))
        for following in observed_listing_pages(page,page_url):
            if following not in seen_pages and following not in queue:
                queue.append(following)
    state["pagesScanned"]=len(pages)
    state["pagesPending"]=len(queue)
    all_entries={}
    total_links=0
    for page_url,page in pages:
        links,count=observed_links(page,page_url,kind)
        total_links+=count
        for entry in links:
            all_entries.setdefault(entry["url"],entry)
    links=list(all_entries.values())
    state["articleLinks"]=total_links
    state["relevantLinks"]=len(links)
    if kind=="kdata" and total_links<5:
        state["lowLinkCoverage"]=True
    if not total_links:
        state.update(status="partial",note="목록 접근 성공했으나 실제 게시글 링크 0건. 목록 구조·파서 재검증 필요")
        return [],state
    state["uninspectedCandidates"]=max(0,len(links)-MAX_DETAIL_PER_SOURCE)
    results=[]
    for index,entry in enumerate(links):
        if index>=MAX_DETAIL_PER_SOURCE:
            results.append(review_record(entry,name,stamp,"상세검사 대기·검사 상한 도달"))
            continue
        title=entry["title"]
        deadline=row_deadline(entry["context"],kind)
        detail=""
        error=False
        if not deadline:
            try:
                article=fetch(entry["url"])
                container=article.select_one("article") or article.select_one("main") or article
                detail=container.get_text("\n",strip=True)
                deadline=explicit_deadline(detail)
            except Exception:
                error=True
                state["detailErrors"]+=1
        if not deadline:
            state["undatedCandidates"]+=1
            reason="상세 접근 실패" if error else (
                "상시접수·마감일 별도 확인" if re.search(r"상시.?접수|상시.?모집",title+" "+detail) else
                "신청 마감일 불명")
            results.append(review_record(entry,name,stamp,reason,detail))
            continue
        boundary=dt.datetime.fromisoformat(
            deadline if "T" in deadline else deadline+"T23:59:59+09:00")
        if boundary<now:
            state["expiredCandidates"]+=1
            continue
        eligibility,proof=eligibility_signal(detail)
        result=review_record(entry,name,stamp,"자격 확인 필요",detail,deadline)
        result.update(sourceKind="공식 모집공고·원문 확인",
                      eligibility=eligibility,eligibilityEvidence=proof,
                      reviewStatus="자격 확인 필요",
                      review="모집마감 확인·최종 신청자격 및 첨부 검증 필요")
        results.append(result)
    state["discovered"]=sum(bool(r.get("deadline")) for r in results)
    state["pendingReview"]=sum(not r.get("deadline") for r in results)
    state["status"]="partial" if (state["pagesPending"] or state["uninspectedCandidates"] or
       state.get("lowLinkCoverage") or state["detailErrors"] or
       state["undatedCandidates"]) else "ok"
    if not state["discovered"]:
        state["note"]="현재 신청 가능 공고 미확정. 공식 목록 접근 성공만으로 0건 확정하지 않음"
    return results,state

def coverage_summary(states, required_names):
    """Fail-visible source health. A successful HTTP response is NOT enough."""
    by_name={s.get("name"):s for s in states if isinstance(s,dict)}
    required=list(required_names)
    outcomes=[]
    for name in required:
        row=by_name.get(name)
        state=row.get("status","error") if row else "missing"
        outcomes.append({
            "name":name,"status":state,
            "verifiedArticleLinks":int((row or {}).get("articleLinks",0)),
            "relevantLinks":int((row or {}).get("relevantLinks",0)),
            "currentQualified":int((row or {}).get("discovered",0)),
            "undated":int((row or {}).get("undatedCandidates",(row or {}).get("unknownDeadline",0))),
            "pendingReview":int((row or {}).get("pendingReview",0)),
            "uninspectedCandidates":int((row or {}).get("uninspectedCandidates",0)),
            "pagesScanned":int((row or {}).get("pagesScanned",1)),
            "pagesPending":int((row or {}).get("pagesPending",0)),
            "detailErrors":int((row or {}).get("detailErrors",0)),
            "error":str((row or {}).get("error",""))[:160],
        })
    degraded=[x["name"] for x in outcomes if x["status"]!="ok"]
    listing_degraded=[
        x["name"] for x in outcomes
        if x["status"] in ("error","missing") or
           (x["verifiedArticleLinks"]==0 and x["currentQualified"]==0) or
           bool((by_name.get(x["name"]) or {}).get("lowLinkCoverage"))
    ]
    return {
       "expected":len(required),
       "listingHealthy":len(required)-len(listing_degraded),
       "listingDegraded":listing_degraded,
       "applicationDatesUnverified":sum(x["undated"] for x in outcomes),
       "pendingReview":sum(x["pendingReview"] for x in outcomes),
       "uninspectedCandidates":sum(x["uninspectedCandidates"] for x in outcomes),
       "detailFailures":sum(x["detailErrors"] for x in outcomes),
       "pagesScanned":sum(x["pagesScanned"] for x in outcomes),
       "pagesPending":sum(x["pagesPending"] for x in outcomes),
       "healthy":len(required)-len(degraded),
       "degraded":degraded,
       "status":"healthy" if not degraded else "degraded",
       "sources":outcomes,
       "note":"공식 출처 0건과 접속 실패를 구분하며, 응모자격·자료이용권 자동 확인을 의미하지 않음",
    }

KDATA_CA_ISSUER = "http://public.wisekey.com/crt/tsrsasecureca2.cer"


def verified_public_get(url, *, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS):
    """Fetch with TLS verification. Repair K-DATA's incomplete server chain
    by supplying the certificate issuer intermediate (never a replacement root).
    OpenSSL must still verify the full chain and the exact requested hostname.
    """
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout:
        # Both KHIDI boards and the HIRA notice page intermittently time out.
        # Retry a bounded second request; a second failure stays visible.
        if urlsplit(url).hostname not in (
            "www.hira.or.kr","hira.or.kr",
            "www.khidi.or.kr","khidi.or.kr"):
            raise
        return requests.get(url, headers=headers, timeout=(6,14))
    except requests.exceptions.SSLError:
        if urlsplit(url).hostname != "www.kdata.or.kr":
            raise
        # The URL is the explicit CA-Issuers AIA of K-DATA's live certificate.
        # An untrusted HTTP intermediate cannot authenticate the site: the
        # subsequent HTTPS request is validated against certifi trust roots.
        issuer = requests.get(KDATA_CA_ISSUER, timeout=7)
        issuer.raise_for_status()
        if not 300 <= len(issuer.content) <= 100000:
            raise ValueError("K-DATA issuer certificate has invalid length")
        if issuer.content.lstrip().startswith(b"-----BEGIN CERTIFICATE-----"):
            pem = issuer.content.decode("ascii")
        else:
            pem = ssl.DER_cert_to_PEM_cert(issuer.content)
        with tempfile.TemporaryDirectory(prefix="worklinks-ca-") as directory:
            ca_file = Path(directory) / "verified-ca-chain.pem"
            ca_file.write_bytes(
                Path(certifi.where()).read_bytes() + b"\n" +
                pem.encode("ascii") + b"\n"
            )
            return requests.get(url, headers=headers, timeout=timeout,
                                verify=str(ca_file))


HIRA_NOTICE_RSS = "https://www.hira.or.kr/cms/inform/01/notice.xml"


def verified_hira_rss(content):
    """Parse only HIRA's published official notice RSS; reject alien links."""
    if len(content)>3_000_000:
        raise ValueError("HIRA RSS too large")
    root=ET.fromstring(content)
    items=root.findall(".//item")
    if not items:
        raise ValueError("HIRA RSS contains no notice items")
    rows=[]
    base=next(url for _,url,kind in SOURCES if kind=="hira")
    for item in items[:50]:
        title=clean(item.findtext("title"),200)
        link=clean(item.findtext("link"),500)
        official=valid_official_link(link,base,"hira")
        if not official or not title:
            continue
        rows.append('<tr><td><a href="'+html_escape(official,quote=True)+'">'+
                    html_escape(title)+'</a></td></tr>')
    if not rows:
        raise ValueError("HIRA RSS has no verified official notice links")
    return BeautifulSoup("<table>"+"".join(rows)+"</table>","html.parser")


def scan_priority_sources(fetch=None,now=None):
    now=now or dt.datetime.now(KST)
    if fetch is None:
        def fetch(url):
            def request_one():
                try:
                    r=verified_public_get(url,headers=HEADERS,timeout=REQUEST_TIMEOUT_SECONDS)
                    r.raise_for_status()
                except requests.exceptions.RequestException:
                    if url != next(x[1] for x in SOURCES if x[2]=="hira"):
                        raise
                    # An independent, officially published feed; only links
                    # validated against the HIRA notice board are accepted.
                    feed=requests.get(HIRA_NOTICE_RSS,headers=HEADERS,timeout=(6,14))
                    feed.raise_for_status()
                    return verified_hira_rss(feed.content)
                if len(r.content)>3_000_000:raise ValueError("HTML exceeds safe size")
                return BeautifulSoup(r.text,"html.parser")
            # Four public KHIDI boards share one host. Avoid self-inflicted
            # rate limits while probing different official institutions.
            if _urlsplit(url).hostname in ("www.khidi.or.kr","khidi.or.kr"):
                with _KHIDI_LIMIT:
                    return request_one()
            return request_one()
    rows,states=[],[]
    # Concurrent independent source checks are bounded so one slow institution
    # cannot consume the entire 18-minute WorkLinks refresh time budget.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rr,st in pool.map(lambda source:scan_one(source,fetch,now), SOURCES):
            rows.extend(rr);states.append(st)
    return rows,states
