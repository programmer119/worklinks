#!/usr/bin/env python3
"""WorkLinks investment-opportunity discovery. No changes to bid processing."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import requests
import sys
from bs4 import BeautifulSoup
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path: sys.path.insert(0, str(SCRIPT_DIR))
from worklinks_sefund import scan_band
from worklinks_global_accelerators import scan_global
from worklinks_kised import scan_kised
from worklinks_dynamic_sources import scan_browser_sources

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "startup-support/investment-opportunities.json"
KST = dt.timezone(dt.timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0 WorkLinks/1.0 public-listing-monitor", "Accept-Language": "ko-KR,ko;q=0.9"}
KEY = re.compile(r"엔젤투자|액셀러레이|엑셀러레이|투자유치|투자상담|투자교류|투자매칭|벤처투자|투자설명|투자자\s*매칭|오픈이노베이션|투자\s*피칭|IR\s*(?:경진|데모|피칭|상담|캠프)|데모데이|TIPS|LIPS|프라이머|블루포인트|스파크랩|퓨처플레이|배치\s*\d|batch|office\s*hour|d\.day|invest|사업협력.*매칭|CVC|VC\b",re.I)
DATE = re.compile(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})\s*(?:일)?(?:\([월화수목금토일]\))?\s*(?:(\d{1,2}):(\d{2}))?",re.I)
WATCH = [
 {"name":"창업진흥원 공식 사업공고","type":"창업지원·공모","url":"https://www.kised.or.kr/misAnnouncement/index.es?mid=a10302000000"},
 {"name":"한국엔젤투자협회","type":"엔젤","url":"https://www.kban.or.kr/"},
 {"name":"벤처투자종합포털","type":"VC","url":"https://www.vcs.go.kr/"},
 {"name":"TIPS 공식","type":"TIPS","url":"https://www.jointips.or.kr/"},
 {"name":"프라이머","type":"AC","url":"https://www.primer.kr/"},
 {"name":"블루포인트파트너스","type":"AC","url":"https://bluepoint.ac/"},
 {"name":"스파크랩","type":"AC","url":"https://www.sparklabs.co.kr/"},
 {"name":"COMEUP","type":"IR·매칭","url":"https://www.comeup.org/"},
 {"name":"OI마켓","type":"CVC·OI","url":"https://oimarket.kr/program"},
 {"name":"서울 스타트업플러스","type":"공공지원·OI·투자","url":"https://startup-plus.kr/project"},
 {"name":"도전의 IR 운영사별 접수","type":"TIPS·IR","url":"https://irchallenge.jointips.or.kr/apply"}
]

def now(): return dt.datetime.now(KST)
def tidy(s,n=350): return re.sub(r"\s+"," ",str(s or "")).strip()[:n]
def token(url, title=""): return hashlib.sha256((url.split("?")[0].rstrip("/") + "|" + title).encode()).hexdigest()[:20]
def html(url):
    r=requests.get(url,headers=HEADERS,timeout=17)
    r.raise_for_status()
    if len(r.content)>4500000: raise ValueError("HTML size limit")
    return BeautifulSoup(r.text,"html.parser")
def category(title):
    if re.search("엔젤|angel",title,re.I): return "엔젤"
    if re.search("TIPS|LIPS|팁스|립스",title,re.I):return "TIPS·연계"
    if re.search("CVC|오픈이노베이션",title,re.I): return "CVC·OI"
    if re.search("액셀러레이|엑셀러레이|batch|배치|accelerat",title,re.I):return "AC·보육"
    if re.search(r"VC\b|벤처투자|직접투자|invest",title,re.I):return "VC·투자"
    return "IR·매칭"
def section(body,start,stop,n=700):
    m=re.search(start,body)
    if not m:return ""
    raw=body[m.end():m.end()+n];e=re.search(stop,raw)
    return raw[:e.start()] if e else raw
def eligibility(body):
    target=section(body,"신청대상|모집대상|지원대상","제외대상|제출서류|선정절차|지원내용|신청방법|문의처")
    excluded=section(body,"제외대상|신청 제외","제출서류|선정절차|지원내용|신청방법|문의처",450)
    if re.search(r"예비\s*창업자\s*(?:신청\s*불가|지원\s*불가|제외|불가)",excluded+(" "+target if "제외" in target else "")):return "예비 제외"
    if re.search(r"(?:법인기업|법인사업자)\s*(?:만|한정|대상)|법인등기\s*필수|사업자등록증\s*필수",target):return "사업자 필수"
    if re.search(r"예비\s*창업자|예비\s*창업팀|사업자등록\s*전",target):return "예비 언급·조건 확인"
    return "자격 확인 필요"
def deadline(body):
    compact=tidy(body,13000);m=re.search("신청기간|접수기간|모집기간",compact)
    if not m:return None
    snip=compact[m.end():m.end()+180]
    dates=[]
    for x in DATE.finditer(snip):
        y,mo,d,h,minute=x.groups()
        try:dates.append((dt.datetime(int(y),int(mo),int(d),int(h or 23),int(minute or 59),tzinfo=KST),bool(h)))
        except ValueError:pass
    if not dates or (len(dates)==1 and not re.search("마감|종료|~|～|까지",snip)):return None
    day,explicit=dates[1] if len(dates)>1 else dates[0]
    if day.year<2024 or day.year>2035:return None
    return day.isoformat(timespec="minutes") if explicit else day.date().isoformat()
def make(url,title,body,source,kind):
    return {"id":token(url,title),"title":tidy(title,180),"url":url,"category":category(title),
       "eligibility":eligibility(body),"deadline":deadline(body),"description":tidy(body,300),
       "source":source,"sourceKind":kind,"lastSeenAt":now().isoformat(timespec="seconds"),
       "review":"모집 원문·거주지·법인 요건 확인 필요"}
def venture_links(soup):
    out={}
    for a in soup.select("a[href]"):
        href=urljoin("https://www.venturesquare.net",a.get("href",""))
        if not re.fullmatch(r"https?://(?:www\.)?venturesquare\.net/announcement/\d+/?(?:\?.*)?",href):continue
        title=tidy(a.get_text(" ",strip=True),180)
        if len(title)>=8 and KEY.search(title):out[href.split("?")[0]] = title
    return out
def venture():
    found={}
    for n in range(1,5):
        page="https://www.venturesquare.net/announcement/" if n==1 else "https://www.venturesquare.net/announcement/page/%d/"%n
        found.update(venture_links(html(page)))
    rows=[];failed=0
    for url,title in list(found.items())[:65]:
        try:
            soup=html(url);main=soup.select_one("article") or soup.select_one("main") or soup
            rows.append(make(url,title,main.get_text(" ",strip=True),"벤처스퀘어 모집공고","재게시·공식 원문 확인 필요"))
        except (requests.RequestException, ValueError):
            failed+=1;rows.append(make(url,title,"","벤처스퀘어 모집공고","목록만 확인"))
    return rows,{"name":"벤처스퀘어 모집공고","url":"https://www.venturesquare.net/announcement/","status":"partial" if failed else "ok","discovered":len(rows),"detailErrors":failed,"checkedAt":now().isoformat(timespec="seconds")}
def dcamp():
    soup=html("https://dcamp.kr/");links={}
    for a in soup.select("a[href]"):
        href=urljoin("https://dcamp.kr/",a.get("href",""))
        p=urlsplit(href)
        if p.netloc not in ("dcamp.kr","www.dcamp.kr") or not re.match(r"^/program/(?:\d+|batch(?:_\d+)?|officehour.*|d-day.*)",p.path):continue
        title=tidy(a.get_text(" ",strip=True),170)
        if len(title)>=5:links[href.split("?")[0]]=title
    rows=[];failed=0
    for url,title in list(links.items())[:25]:
        try:
            soup=html(url);main=soup.select_one("main") or soup
            body=main.get_text(" ",strip=True)
            if KEY.search(title+" "+body[:450]):rows.append(make(url,title,body,"디캠프 공식 프로그램","공식 모집페이지·접수 확인 필요"))
        except (requests.RequestException,ValueError):
            failed+=1;rows.append(make(url,title,"","디캠프 공식 프로그램","목록만 확인"))
    return rows,{"name":"디캠프 공식 프로그램","url":"https://dcamp.kr/","status":"partial" if failed else "ok","discovered":len(rows),"detailErrors":failed,"checkedAt":now().isoformat(timespec="seconds")}
def band():
    return scan_band(html, now())



# Additive official-source discovery. Each source is isolated so failures never stop
# the original VentureSquare/dcamp/Band/global collectors.
OFFICIAL_FEEDS = (
 ("벤처투자종합포털 벤처투자마트", "https://www.vcs.go.kr/web/portal/bbs/martnotice/list",
  "vcs.go.kr", r"^/web/portal/bbs/martnotice/[0-9]+$"),
 ("TIPS 공식 행사", "https://jointips.or.kr/",
  "jointips.or.kr", r"^/contents/events/detail$"),
)
OFFICIAL_RELEVANCE = re.compile(
 r"투자|엔젤|매칭|IR|TIPS|팁스|데모데이|보육|액셀러|오픈이노베이션|실증|PoC|협업|공동개발|창업|사업화|해외진출", re.I)

def official_source(spec):
    name, listing_url, host, detail_path = spec
    checked=now().isoformat(timespec="seconds")
    soup=html(listing_url)
    candidates={}
    for a in soup.select("a[href]"):
        title=tidy(a.get_text(" ",strip=True),180)
        href=urljoin(listing_url,a.get("href",""))
        parts=urlsplit(href)
        host_name=parts.hostname or ""
        if parts.scheme!="https" or not (host_name==host or host_name.endswith("."+host)):
            continue
        # A detail URL is mandatory: exclude listing/navigation/pagination and
        # fabricated JS template URLs such as /project/{{projectCode}}.
        if not re.fullmatch(detail_path,parts.path):
            continue
        if not OFFICIAL_RELEVANCE.search(title) or not 9<=len(title)<=160:
            continue
        if host=="jointips.or.kr" and not re.search(r"(?:^|[?&])eventId=[A-Za-z0-9]+",parts.query):
            continue
        candidates[href]=title
    rows=[];errors=0
    for url,title in list(candidates.items())[:35]:
        try:
            detail=html(url)
            body=tidy((detail.select_one("main") or detail).get_text(" ",strip=True),12000)
            if not OFFICIAL_RELEVANCE.search(title+" "+body[:500]):continue
            # Many TIPS event details are JS-only. A HTTP 200 with only menu
            # text is NOT a verified application page.
            if normalize_title(title) not in normalize_title(body):
                errors+=1
                rows.append(make(url,title,"",name,"목록에서만 발견 · 동적 상세 확인 실패"))
                continue
            item=make(url,title,body,name,"공식 공개 상세·신청자격 확인 필요")
            if host=="vcs.go.kr":
                # Month-only date ranges must not inherit a made-up 23:59 time.
                ym=re.search(r"(20\d\d)년\s*(\d{1,2})월",title)
                dr=re.search(r"모집기간\s*[:：]?\s*(?:20\d\d년\s*)?(\d{1,2})월\s*(\d{1,2})일.*?[~～]\s*(\d{1,2})월\s*(\d{1,2})일",body)
                if ym and dr and int(ym.group(2))==int(dr.group(3)):
                    item["deadline"]=f"{ym.group(1)}-{int(dr.group(3)):02d}-{int(dr.group(4)):02d}"
                if re.search(r"예비창업자.{0,45}(?:개인|신청\s*가능)",body):
                    item["eligibility"]="예비창업자 가능·회원가입 및 세부조건 확인"
                item["review"]="VC 1:1 상담 모집. 본문 접수일 확인, 선정·상담 및 투자 보장 없음."
            rows.append(item)
        except (requests.RequestException,ValueError,AttributeError):
            errors+=1
            rows.append(make(url,title,"",name,"목록만 확인 · 상세 접근 실패"))
    # A responsive page is not necessarily a working feed. Angular/JS-only
    # screens are PARTIAL, never a successfully empty monitor.
    state="partial" if errors or not rows else "ok"
    note=("공개 상세 링크 "+str(len(candidates))+"개 발견. "
          +("목록 로딩은 되었지만 상세 추출 0건; JS·로그인·API 접근 제한 확인 필요."
            if not rows else "접수·자격은 반드시 공식 상세 확인."))
    return rows,{"name":name,"url":listing_url,"status":state,
      "discovered":len(rows),"detailErrors":errors,"checkedAt":checked,
      "note":note}
def scan_official():
    found=[];states=[]
    for spec in OFFICIAL_FEEDS:
        try:
            entries,info=official_source(spec);found.extend(entries);states.append(info)
        except (requests.RequestException,ValueError,AttributeError,RuntimeError) as exc:
            states.append({"name":spec[0],"url":spec[1],"status":"error",
              "discovered":0,"detailErrors":0,"checkedAt":now().isoformat(timespec="seconds"),
              "error":tidy(exc,170)})
    return found,states

def normalize_title(title):
    text = re.sub(r"\([^)]*\)", "", str(title or ""))
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", text).casefold()


def registered_titles():
    doc = (ROOT / "startup-support/index.html").read_text(encoding="utf-8")
    found = {}
    for prefix in ("var items=", "var pendingSupportCandidates="):
        m = re.search(re.escape(prefix) + r"(\[.*?\]);", doc, re.S)
        if not m:
            continue
        try:
            entries = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for entry in entries:
            key = normalize_title(entry.get("title", ""))
            if key:
                found[key] = entry.get("id", "")
    return found


def historic():
    doc=(ROOT/"startup-support/index.html").read_text(encoding="utf-8")
    out=[]
    for prefix in ("var items=","var pendingSupportCandidates="):
        m=re.search(re.escape(prefix)+r"(\[.*?\]);",doc,re.S)
        if not m:continue
        try:records=json.loads(m.group(1))
        except json.JSONDecodeError:continue
        for x in records:
            title=str(x.get("title",""));url=str(x.get("url",""))
            if not KEY.search(title) or not url.startswith("https://"):continue
            d=x.get("deadline");iso=re.match(r"^20\d\d-\d\d-\d\d(?:T\d\d:\d\d(?::\d\d)?(?:\+09:00)?)?",d or "") if isinstance(d,str) else None
            out.append({"id":token(url,title),"title":title,"url":url,"category":category(title),"eligibility":"기존 판정·재확인 필요",
            "deadline":iso.group(0) if iso else None,"description":tidy(x.get("support",""),300),"source":"기존 WorkLinks 등록",
            "sourceKind":"과거 수동 등록·현재 재검증 아님","lastSeenAt":None,"review":"현재 모집 원문 확인 필요"})
    return out
def deadline_dt(raw):
    if not raw:return None
    try:
        v=dt.datetime.fromisoformat(raw+"T23:59:59+09:00" if len(raw)==10 else raw)
        return v if v.tzinfo else v.replace(tzinfo=KST)
    except (ValueError,TypeError):return None
def main():
    old={}
    if OUT.exists():
        try:old=json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):pass
    rows=[];sources=[]
    for name,fetch in (("벤처스퀘어 모집공고",venture),("디캠프 공식 프로그램",dcamp),("재단법인 밴드 공식 공지",band)):
        try:
            items,status=fetch();rows+=items;sources.append(status)
        except (requests.RequestException,ValueError,AttributeError,RuntimeError) as ex:
            sources.append({"name":name,"status":"error","discovered":0,"detailErrors":0,"error":tidy(ex,170),"checkedAt":now().isoformat(timespec="seconds")})
    official_rows, official_sources = scan_official()
    rows += official_rows
    sources += official_sources
    browser_rows, browser_sources = scan_browser_sources()
    rows += browser_rows
    sources += browser_sources
    global_rows, global_sources = scan_global()
    rows += global_rows
    sources += global_sources
    kised_rows, kised_sources = scan_kised(html, now())
    rows += kised_rows
    sources += kised_sources
    registered = registered_titles()
    for item in rows:
        if item.get("source") == "재단법인 밴드 공식 공지사항":
            matched = registered.get(normalize_title(item.get("title", "")))
            if matched:
                item["worklinksRecordId"] = matched
    checked={x["id"] for x in rows}
    known_titles={normalize_title(x.get("title","")) for x in rows}
    rows += [x for x in historic() if normalize_title(x.get("title","")) not in known_titles]
    merged={x["id"]:x for x in rows}
    for p in old.get("opportunities",[]):
        if not isinstance(p,dict) or p.get("id") in merged or p.get("source")=="기존 WorkLinks 등록":continue
        try:age=(now()-dt.datetime.fromisoformat(p.get("lastSeenAt",""))).days
        except (ValueError,TypeError):continue
        if age<=7:
            p["sourceKind"]="과거 수집·이번 실행에서 미확인";merged[p["id"]]=p
    listing=[]
    for p in merged.values():
        end=deadline_dt(p.get("deadline"))
        if end and end<now()-dt.timedelta(days=40):continue
        p["deadlineState"]="closed" if p.get("sourceStatus")=="closed" or (end and end<now()) else "open_by_date" if end else "unknown"
        p["freshness"]="checked" if p["id"] in checked else "historical" if p["source"]=="기존 WorkLinks 등록" else "stale"
        listing.append(p)
    listing.sort(key=lambda x:(x["freshness"]!="checked",x["deadlineState"]=="closed",x["deadlineState"]=="unknown",x.get("deadline") or "9999",x["title"]))
    data={"schemaVersion":1,"generatedAt":now().isoformat(timespec="seconds"),"sources":sources,
    "watchTargets":[dict(x,mode=("공식 공개 목록 수집 시도·JS/인증 제한 별도 표시" if x["url"].startswith(("https://www.vcs.go.kr","https://www.jointips.or.kr","https://startup-plus.kr","https://irchallenge.jointips.or.kr")) else "참고 링크·자동수집 아님")) for x in WATCH],"opportunities":listing,
    "stats":{"total":len(listing),"liveDiscovered":sum(x["freshness"]=="checked" for x in listing),
             "historical":sum(x["freshness"]=="historical" for x in listing)}}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"sources":sources,"stats":data["stats"]},ensure_ascii=False))
    return 0 if any(s["status"] in ("ok","partial") for s in sources) else 1
if __name__=="__main__":raise SystemExit(main())
