"""Independent high-priority KIMSE official-notice collector.

Covers real public source LISTS, not guessed notice IDs or UI search keywords.
Only items with verified future *application* deadlines become actionable rows.
Other relevant notices remain counted for missed-opportunity auditing.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re
from urllib.parse import parse_qs, urljoin, urlsplit
import requests
from bs4 import BeautifulSoup

KST = dt.timezone(dt.timedelta(hours=9))
SOURCES = (
    ("KHIDI 보건산업 사업공고", "https://www.khidi.or.kr/board?menuId=MENU01108", "khidi"),
    ("KHIDI 의료기기 지원사업", "https://www.khidi.or.kr/mdtis/bizPbanc/bizPbancList?menuId=MENU03471", "device"),
    ("KHIDI 기관별 의료·연구지원 사업", "https://www.khidi.or.kr/board?menuId=MENU01484", "khidi_external"),
    ("KHIDI 의료기기 상담·교육", "https://www.khidi.or.kr/board?menuId=MENU01491", "khidi_events"),
    ("NIA AI·데이터 공지", "https://www.nia.or.kr/site/nia_kor/ex/bbs/List.do?cbIdx=99835", "nia"),
    ("K-DATA 데이터·안심구역 공지", "https://www.kdata.or.kr/kr/board/notice_01/boardList.do", "kdata"),
    ("심평원 창업·의료데이터 소식", "https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020041000100", "hira"),
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
        if not any(re.fullmatch(r"\d{1,12}",v) for values in q.values() for v in values):
            return None
        return url
    if kind=="hira" and host in ("www.hira.or.kr","hira.or.kr") and p.path=="/bbsDummy.do":
        b=q.get("brdBltNo",[])
        if len(b)!=1 or not re.fullmatch(r"\d{4,8}",b[0]):
            return None
        if q.get("brdScnBltNo")!=["4"]:return None
        return f"https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020041000100&brdScnBltNo=4&brdBltNo={b[0]}"
    return None

def observed_links(soup,base,kind):
    discovered={}
    all_valid=0
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
    for line in str(text or "").splitlines():
        line=clean(line,550)
        m=APPLICATION.search(line)
        if not m:continue
        tail=line[m.end():]
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

def scan_one(source,fetch,now):
    name,url,kind=source
    stamp=now.isoformat(timespec="seconds")
    state={"name":name,"url":url,"status":"error","discovered":0,"checkedAt":stamp,"articleLinks":0,"relevantLinks":0,
           "undatedCandidates":0,"detailErrors":0,"expiredCandidates":0,"candidateLimit":24}
    try:soup=fetch(url)
    except Exception as e:
        state["error"]=clean(type(e).__name__+": "+str(e),200)
        return [],state
    links,count=observed_links(soup,url,kind)
    state["articleLinks"]=count;state["relevantLinks"]=len(links)
    if not count:
        state.update(status="partial",note="공식 페이지 접근은 성공했으나 실제 상세링크를 0건 식별. 목록 구조 검증 필요")
        return [],state
    results=[]
    for entry in links[:24]:
        title=entry["title"]
        deadline=row_deadline(entry["context"],kind)
        detail=""
        if not deadline:
            try:
                article=fetch(entry["url"])
                container=article.select_one("article") or article.select_one("main") or article
                detail=container.get_text("\n",strip=True)
                deadline=explicit_deadline(detail)
            except Exception:
                state["detailErrors"]+=1
        if not deadline:
            state["undatedCandidates"]+=1
            continue
        boundary=dt.datetime.fromisoformat(deadline if "T" in deadline else deadline+"T23:59:59+09:00")
        if boundary < now:
            state["expiredCandidates"]+=1
            continue
        uid=hashlib.sha1(entry["url"].encode()).hexdigest()[:18]
        results.append({"id":"priority-health-"+uid,"title":title,"url":entry["url"],"category":"창업지원·공모",
          "eligibility":"자격 확인 필요","deadline":deadline,
          "description":clean(detail,400) or "공식 공개목록 확인. 개별 지원요건과 비용은 원문 및 첨부 확인 필요",
          "source":name,"sourceKind":"공식기관 직접 검색·신청자격 원문 검증 필요",
          "sourceStatus":"unknown","lastSeenAt":stamp,"review":"사업자등록·IRB·지역제한·실제 지원혜택은 공식 첨부 확인 필요"})
    state["discovered"]=len(results)
    state["status"]="partial" if len(links)>24 or state["detailErrors"] or state["undatedCandidates"] else "ok"
    if not results:
        state["note"]="지원 가능 공고 미확정. 공식목록 접근 성공만으로 0건 확정하지 않음"
    return results,state

def scan_priority_sources(fetch=None,now=None):
    now=now or dt.datetime.now(KST)
    if fetch is None:
        session=requests.Session()
        def fetch(url):
            r=session.get(url,headers=HEADERS,timeout=12)
            r.raise_for_status()
            if len(r.content)>3_000_000:raise ValueError("HTML exceeds safe size")
            return BeautifulSoup(r.text,"html.parser")
    rows,states=[],[]
    for source in SOURCES:
        rr,st=scan_one(source,fetch,now)
        rows.extend(rr);states.append(st)
    return rows,states
