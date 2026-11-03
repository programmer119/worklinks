#!/usr/bin/env python3
"""Official small-municipality opportunity monitor; independently fail-closed.

Discover notices on official public boards and official Bizinfo cross-posts.
Unknown application eligibility, amounts and deadlines remain UNKNOWN.
A local government site failing never counts as a successful empty scan.
No applicant state is changed, and no unofficial money/competition claim is inferred.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "startup-support/year-end-local-budget.json"
KST = dt.timezone(dt.timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WorkLinksLocalBudget/1.0; official public pages)", "Accept-Language": "ko-KR,ko;q=0.9"}
# Real government sites, not a list of search-engine queries. Each URL is a
# monitored source, not a claim that all its posts are currently recoverable.
SOURCES = (
    ("옥천군 공지", "https://www.oc.go.kr/www/selectBbsNttList.do?bbsNo=36&key=232", "옥천군", "local"),
    ("옥천군 고시공고", "https://www.oc.go.kr/www/selectBbsNttList.do?bbsNo=40&key=236", "옥천군", "local"),
    ("청양군 군정소식", "https://www.cheongyang.go.kr/kor.do", "청양군", "local"),
    ("봉화군 고시공고", "https://www.bonghwa.go.kr/portal/saeol/gosi/list.do?mid=0201030000&seCode=01", "봉화군", "local"),
    ("무주군 소식", "https://www.muju.go.kr/index.9is", "무주군", "local"),
    ("의령군 고시공고", "https://www.uiryeong.go.kr/index.do", "의령군", "local"),
    ("단양군 타기관 고시공고", "https://www.danyang.go.kr/dy21/980", "단양군", "local"),
    ("영동군 고시공고", "https://www.yd21.go.kr/kr/html/sub02/020103.html?mode=L", "영동군", "local"),
    ("전국 테크노파크 사업공고 통합", "https://www.technopark.or.kr/www/linkBoard/list.do?mid=1012&type=P", "전국 19개 테크노파크", "tp_hub"),
    ("광주테크노파크 사업공고", "https://gjtp.or.kr/home/business.cs", "광주테크노파크", "agency"),
    ("포항테크노파크", "https://ptp.or.kr/", "포항테크노파크", "agency"),
    ("충남테크노파크", "https://www.ctp.or.kr/", "충남테크노파크", "agency"),
    ("경기테크노파크", "https://www.gtp.or.kr/", "경기테크노파크", "agency"),
    ("부산테크노파크", "https://www.btp.or.kr/kor/Main.do", "부산테크노파크", "agency"),
    ("국민생각함 공모·설문", "https://www.epeople.go.kr/idea/acrc/ideajoin.npaid", "국민권익위원회", "participation"),
    ("국민생각함 사천시", "https://www.epeople.go.kr/idea/4000/ideajoin.npaid?pageIndex=1", "사천시", "participation"),
    ("국민생각함 기상청", "https://www.epeople.go.kr/idea/kma/ideajoin.npaid", "기상청", "participation"),
    ("국민생각함 제주교육청", "https://www.epeople.go.kr/idea/jjethink/ideajoin.npaid?pageIndex=1", "제주교육청", "participation"),
    ("대전시소 시민제안", "https://www.daejeon.go.kr/seesaw/djaskList.do", "대전광역시", "participation"),
    ("기업마당 지역공고", "https://www.bizinfo.go.kr/", "전국 지역공고", "national"),
)
# Only the official TP domains shown in the TP association directory are
# permitted as cross-host detail targets. This is not exhaustive coverage.
TRUSTED_TP_DOMAINS = frozenset((
    "seoultp.or.kr", "btp.or.kr", "dgtp.or.kr", "itp.or.kr",
    "gjtp.or.kr", "djtp.or.kr", "utp.or.kr", "sjtp.or.kr",
    "gtp.or.kr", "gwtp.or.kr", "cbtp.or.kr", "ctp.or.kr",
    "jbtp.or.kr", "jntp.or.kr", "gbtp.or.kr", "gntp.or.kr",
    "jejutp.or.kr", "gdtp.or.kr", "ptp.or.kr",
))
# Later add boards with verified detail selectors. 읍면동 notices are accepted
# when linked by an indexed official municipality page, but there is no
# claim of exhaustive 읍면동 coverage.
# Broad discovery vocabulary: titles are leads, never proof of an award.
# Both 10,000-won user participation rewards and expensive in-kind services matter.
POSITIVE = re.compile(r"공모|아이디어|제안|경진|시상|상금|포상|활동비|사업화|실증|지원사업|수혜기업|재공고|추가\s*모집|긴급|바우처|고령친화|헬스케어|치매|의료\s*AI|설문|만족도|조사\s*(?:참여|이벤트)|경품|상품권|기프티콘|답례품|참여수당|사례비|참여보상|수수료\s*감면|무료\s*(?:지원|이용|분석)|안심존|안심구역|분석환경|API|GPU|데이터\s*(?:지원|이용)|특허|출원|IP\s*디딤돌|크레딧|시험분석|검증\s*지원", re.I)
NEGATIVE = re.compile(r"채용|인사발령|개별공시지가|분묘|폐기물|행정예고|공고\s*취소|합격자|선정\s*결과|심사\s*결과|입법예고|경매|자격증\s*시험|낙찰\s*결과", re.I)
PAYOUT = re.compile(r"상금|포상금|시상금|활동비|사례비|원고료|실증비|사업화\s*지원금|지원금|바우처|상품권|기프티콘|경품|답례품|참여수당|쿠폰|크레딧|수수료\s*면제|비용\s*감면|분석비\s*지원", re.I)
CASH = re.compile(r"상금|포상금|시상금|활동비|사례비|원고료|실증비|사업화\s*지원금|현금|지원금|참여수당", re.I)
GIFT = re.compile(r"상품권|기프티콘|경품|답례품|쿠폰|모바일\s*교환권|기프트콘", re.I)
COST_SAVING = re.compile(r"바우처|크레딧|수수료\s*(?:면제|감면)|비용\s*(?:감면|지원)|무료\s*(?:분석|이용|제공|시험)|특허\s*출원\s*지원|권리화\s*지원|안심존|안심구역|데이터\s*(?:이용|분석)\s*지원|GPU\s*지원|API\s*(?:이용권|크레딧)", re.I)
EQUITY_ONLY = re.compile(r"투자\s*(?:유치|상담|검토|심사)|IR\b|멘토링|네트워킹|무료\s*교육|투자자\s*매칭", re.I)
REGION_LIMIT = re.compile(r"(?:관내|해당\s*지역|군내|도내|시내|거주자|주민등록|사업장\s*소재|본점\s*소재|전입|지역에\s*주소|지역\s*(?:기업|소재|거주))", re.I)
OPEN_TO_ALL = re.compile(r"(?:전\s*국민|누구나|지역\s*제한\s*없음|거주지\s*무관|국민\s*누구나)", re.I)
FAST = re.compile(r"재공고|추가\s*모집|긴급\s*모집|수시\s*모집|연장\s*공고|선착순|예산\s*소진|잔여\s*(?:예산|물량|건수)|재접수|추가\s*접수|재개|미달|재선정", re.I)
COMPETITION_EVIDENCE = re.compile(r"접수\s*(?:미달|부족)|모집\s*(?:미달|인원\s*미달)|신청자\s*미달|잔여\s*(?:인원|선정\s*인원)|유찰|지원자\s*부족", re.I)
ONLINE = re.compile(r"온라인\s*접수|이메일\s*접수|전자우편|구글\s*폼|네이버\s*폼|온라인\s*(?:응모|참여)|설문\s*바로가기", re.I)
IN_PERSON = re.compile(r"방문\s*접수|현장\s*접수|직접\s*방문|방문\s*제출", re.I)
CLOSE = re.compile(r"(?:접수\s*(?:마감|종료)|신청\s*(?:마감|기한)|모집\s*(?:마감|종료)|접수\s*기간|신청\s*기간)[^\n\r]{0,95}?(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})(?:일)?", re.I)
DATE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
DETAIL = re.compile(r"(?:view|detail|selectBbsNtt|bbs|article|board|saeol|notice|gosi|pblanc|ntt|idx|sn|seq|no=|mode=V|action=view)", re.I)
KIMSE = re.compile(r"치매|인지\s*(?:저하|장애)|고령\s*친화|에이지\s*테크|에이지테크|헬스케어|디지털\s*헬스|의료\s*AI|음성\s*바이오마커|돌봄|시니어", re.I)
HEALTH_PATIENT_ONLY = re.compile(r"치료\s*(?:관리비|지원비)|의료급여|환자\s*(?:본인부담|치료비)|장기요양급여|의료비\s*지원\s*기준", re.I)
SUSPENDED = re.compile(r"접수\s*(?:일시\s*)?(?:중지|중단|마감)|지원\s*종료|모집\s*(?:일시\s*)?중단|신규\s*접수\s*불가", re.I)
REOPEN = re.compile(r"재개|재접수|추가\s*접수|잔여\s*(?:건수|물량|예산)|재모집", re.I)
BUSINESS_ONLY = re.compile(r"(?:사업자등록증\s*필수|법인\s*사업자\s*한정|기\s*창업\s*기업|창업\s*[137]년\s*이내)", re.I)
APPLICANT = re.compile(r"(?:예비\s*창업자|창업\s*예정자|사업자\s*등록\s*전|전\s*국민|누구나\s*참여|개인\s*참가)", re.I)

def clean(value, limit=600):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]

def normalized_url(url):
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc.lower(), u.path, u.query, ""))

def notice_id(url):
    return "localbudget-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]

def amount_info(title, body):
    text = title + " " + body[:6500]
    if not PAYOUT.search(text) and not COST_SAVING.search(text):
        return "금전 혜택 미확인", "지급액·수익 여부 원문 확인"
    kind = ("상금·활동비·현금" if CASH.search(text)
            else "상품권·참여보상" if GIFT.search(text)
            else "실비절감·서비스")
    m = re.search(r"(?:상금|포상금|시상금|활동비|실증비|지원금|상품권|쿠폰|크레딧|지원액|수수료)[^\n]{0,55}?(\d[\d,]*(?:\.\d+)?\s*(?:억원|천만원|백만원|만원|천원|원))", text, re.I)
    return kind, clean(m.group(0), 100) if m else "지급액·개별 수령조건 원문 확인"

def deadline_from(body):
    # A standalone publication date is not an application deadline.
    # Support visible title ranges and common YYYY.MM.DD date windows.
    date = r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})(?:일)?"
    ranged = re.compile(r"(?:접수|신청|모집|응모|설문|조사|공모)\s*(?:기간|일정)[^0-9]{0,32}" + date +
                        r"\s*(?:~|∼|～|부터|\-|–|—)\s*" + date, re.I)
    explicit = re.compile(r"(?:접수|신청|모집|응모)?\s*(?:마감일|마감|종료일|신청기한)[^0-9]{0,20}" + date, re.I)
    dates = []
    for pattern, offset in ((ranged, 4), (explicit, 1)):
        for match in pattern.finditer(body):
            values = match.groups()[offset-1:offset+2]
            try:
                dates.append(dt.date(*(int(x) for x in values)))
            except ValueError:
                pass
    if not dates:
        # Only an unambiguous title/status range, not unrelated dates in prose.
        title = body.split("\n", 1)[0][:260]
        match = re.search(date + r"\s*(?:~|∼|～|부터|\-|–|—)\s*" + date, title)
        if match:
            try:
                dates.append(dt.date(*(int(x) for x in match.groups()[3:6])))
            except ValueError:
                pass
    return max(dates).isoformat() if dates else None

def assess(title, detail, municipality, url, now):
    if len(title) < 6 or not POSITIVE.search(title) or NEGATIVE.search(title):
        return None
    body = clean(detail, 10000)
    if not body:
        return None
    joined = title + " " + body[:3500]
    if HEALTH_PATIENT_ONLY.search(title) and not re.search(r"창업|기업|지원사업", title):
        return None
    # A public offer must have a concrete mechanism; a mere policy notice,
    # a success story or an investment-only talk is not an opportunity.
    if not re.search(r"공고|모집|공모|접수|신청|응모|참여|설문|혜택|제공|이벤트|안내", joined[:1800]):
        return None
    benefit, money = amount_info(title, body)
    direct = bool(CASH.search(joined))
    gift = bool(GIFT.search(joined))
    saving = bool(COST_SAVING.search(joined))
    kimse = bool(KIMSE.search(title + " " + body[:1800]))
    # Genuine free technical resources remain candidates even with no
    # numerical amount or a cash keyword.
    if not (direct or gift or saving or kimse):
        return None
    if EQUITY_ONLY.search(title) and not (direct or gift or saving or kimse):
        return None
    deadline = deadline_from(title + "\n" + detail)
    if deadline and deadline < now.date().isoformat():
        return None
    region = bool(REGION_LIMIT.search(body))
    everyone = bool(OPEN_TO_ALL.search(body))
    applicant = bool(APPLICANT.search(body) or everyone)
    business_only = bool(BUSINESS_ONLY.search(body))
    online = bool(ONLINE.search(body))
    in_person = bool(IN_PERSON.search(body))
    fast = bool(FAST.search(title + " " + body[:3500]))
    low_competition = bool(COMPETITION_EVIDENCE.search(title + " " + body[:3500]))
    suspended = bool(SUSPENDED.search(body[:3500]) or re.search(r"^\[(?:마감|접수중지)\]", title))
    # An explicit reopened status overrides an old suspended banner only if
    # posted as an active notice. Otherwise keep it on a waiting list.
    reopened = bool(re.search(r"접수\s*재개\s*(?:안내|공지)|추가\s*접수\s*시작", title))
    if reopened:
        suspended = False
    score = ((8 if low_competition else 0) + (6 if direct and not gift else 0) +
             (5 if saving else 0) + (3 if gift else 0) + (4 if kimse else 0) +
             (3 if applicant and not region and not business_only else 0) +
             (2 if fast else 0) + (1 if online and not in_person else 0) -
             (5 if region else 0) - (3 if business_only else 0) -
             (6 if suspended else 0))
    tier = ("waiting_reopen" if suspended and (fast or saving)
            else "cash_candidate" if (direct or gift) and applicant and not region and not business_only
            else "cost_saving_candidate" if saving and not region and not business_only
            else "kimse_candidate" if kimse
            else "regional_or_unverified")
    grade = ("재개 대기·접수 중지" if suspended else
             "현금·상품권 자격 확인" if tier == "cash_candidate" else
             "실비절감 자격 확인" if tier == "cost_saving_candidate" else
             "낌새 실증·의료 검토" if tier == "kimse_candidate" else "자격·혜택 확인 필요")
    condition = ("지역 자격 제한 단서 · 원문 확인" if region else "지역 제한 발견 안 됨 · 원문 확인")
    condition += " · 예비창업자 표시" if applicant else " · 개인/예비창업 자격 미확인"
    if business_only:
        condition += " · 사업자 조건 의심"
    if suspended:
        condition += " · 현재 접수 중지 단서"
    if online and not in_person:
        condition += " · 온라인 제출 단서"
    return {
        "id": notice_id(normalized_url(url)), "title": clean(title, 180), "url": url,
        "monitorTrack": "yearEndLocalBudget", "category": "general",
        "source": municipality, "sourceKind": "공식 기관 원문 확인",
        "deadline": deadline or "", "period": "공식 마감 " + deadline if deadline else "정확한 접수마감 미확인",
        "support": benefit + " · " + grade + (" · 추가/긴급/재개 단서" if fast else ""),
        "money": money, "condition": condition + " · 개별 지급액과 신청자격 확인 필요",
        "eligibility": "uncertain", "reviewGrade": grade, "reviewScore": score,
        "benefitType": benefit, "regionRestrictionHint": region, "applicationOnlineHint": online,
        "preStartupHint": applicant, "businessRequiredHint": business_only,
        "kimseRelevantHint": kimse, "quickWinTier": tier,
        "competitionEvidence": "공식 원문에 미달/잔여인원 단서" if low_competition else "확인 불가",
        "competitionLevel": "unknown", "suspendedHint": suspended,
        "lastSeenAt": now.isoformat(timespec="seconds"), "applied": False,
    }

def fetch_soup(session, url):
    response = session.get(url, timeout=16, headers=HEADERS, allow_redirects=True)
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("too_large")
    return BeautifulSoup(response.text, "html.parser")

def base_host(host):
    return (host or "").lower().removeprefix("www.")

def trusted_notice_url(raw, source_url, kind):
    if not raw:
        return None
    url = urljoin(source_url, raw)
    u = urlsplit(url)
    source = urlsplit(source_url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        return None
    candidate = base_host(u.hostname)
    current = base_host(source.hostname)
    if candidate != current and not (kind == "tp_hub" and candidate in TRUSTED_TP_DOMAINS):
        return None
    if normalized_url(url) == normalized_url(source_url):
        return None
    if not DETAIL.search(u.path + "?" + u.query):
        # The TP hub is an official index of direct links to TP sites.
        if kind != "tp_hub" or candidate == current or u.path in ("", "/"):
            return None
    return url

def extract_notice_candidates(soup, source_url, kind):
    candidates, unresolved = {}, 0
    for anchor in soup.select("a"):
        title = clean(anchor.get_text(" ", strip=True) or anchor.get("title", ""), 190)
        if len(title) < 9 or not POSITIVE.search(title) or NEGATIVE.search(title):
            continue
        raw = anchor.get("data-href") or anchor.get("data-url") or anchor.get("href", "")
        if not raw or raw.lower().startswith(("javascript:", "#")):
            # Recover only literal URLs from supported JS navigation.
            onclick = anchor.get("onclick", "")
            m = re.search(r"""(?:location\.href\s*=|location\.(?:assign|replace)\()\s*['"]([^'"]+)['"]""", onclick)
            raw = m.group(1) if m else ""
        url = trusted_notice_url(raw, source_url, kind)
        if not url:
            unresolved += 1
            continue
        candidates[normalized_url(url)] = (url, title)
    return candidates, unresolved

def scan_source(spec, session, now):
    name, source_url, municipality, kind = spec
    level = "전국 TP 공식 연결목록" if kind == "tp_hub" else "지역 산하기관 공식" if kind == "agency" else "공식 통합 포털" if kind == "national" else "기초지자체 원문"
    state = {"name": name, "url": source_url, "status": "error", "discovered": 0, "checkedAt": now.isoformat(timespec="seconds"), "level": level}
    try:
        soup = fetch_soup(session, source_url)
        candidates, unresolved = extract_notice_candidates(soup, source_url, kind)
        rows, errors = [], 0
        for url, title in list(candidates.values())[:35]:
            try:
                doc = fetch_soup(session, url)
                area = doc.select_one("article") or doc.select_one("main") or doc.select_one("#contents") or doc
                body = area.get_text(" ", strip=True)
                first = re.sub(r"\s+", "", title)[:14]
                if first and first not in re.sub(r"\s+", "", body):
                    errors += 1
                    continue
                row = assess(title, body, municipality, url, now)
                if row:
                    row["sourceKind"] = (
                        "전국 TP 공식 연결목록 · 지역 TP 원문 확인" if kind == "tp_hub"
                        else "지역 산하기관 공식 사업공고" if kind == "agency"
                        else "지자체 공식 게시판 직접 확인" if kind == "local"
                        else "기업마당 공식 재게시 · 원 발행기관 확인 필요")
                    rows.append(row)
            except (requests.RequestException, ValueError, AttributeError):
                errors += 1
        state.update({"status": "partial" if errors or unresolved or not candidates else "ok",
                      "discovered": len(rows), "candidateLinks": len(candidates),
                      "detailErrors": errors, "unresolvedLinks": unresolved})
        if not candidates:
            state["note"] = "상세 공고 추출 0건 · 공식 게시판 형식 확인 필요"
        return rows, state
    except (requests.RequestException, ValueError, AttributeError) as exc:
        state["error"] = clean(str(exc), 180)
        return [], state

def collect(now=None, session=None):
    now = now or dt.datetime.now(KST)
    session = session or requests.Session()
    records, statuses = {}, []
    for spec in SOURCES:
        rows, state = scan_source(spec, session, now)
        statuses.append(state)
        for row in rows:
            if row["id"] not in records:
                records[row["id"]] = row
    values = sorted(records.values(), key=lambda x: (-x["reviewScore"], x["deadline"] or "9999-12-31", x["id"]))
    return {"schemaVersion": 1, "generatedAt": now.isoformat(timespec="seconds"),
            "sources": statuses, "opportunities": values,
            "stats": {"sources": len(statuses), "successfulSources": sum(s["status"] == "ok" for s in statuses),
                      "partialSources": sum(s["status"] == "partial" for s in statuses),
                      "failedSources": sum(s["status"] == "error" for s in statuses),
                      "opportunities": len(values),
                      "unresolvedLinks": sum(s.get("unresolvedLinks", 0) for s in statuses),
                      "cashEvidence": sum(r["benefitType"] != "금전 혜택 미확인" for r in values),
                      "quickWinCandidates": sum(r.get("quickWinTier") == "cash_candidate" for r in values),
                      "kimseCandidates": sum(r.get("kimseRelevantHint") for r in values)},
            "coverageNote": "기초지자체·TP 공식 사업공고·기업마당의 비전수 수집. TP 통합목록은 19개 TP의 일부 재게시이며 전체 시군구·산하기관 전수감시가 아님."}

def main():
    data = collect()
    print(json.dumps(data["stats"], ensure_ascii=False))
    # Do not overwrite a previously populated snapshot if every source fails.
    if not any(s["status"] in ("ok", "partial") for s in data["sources"]):
        print("All local sources failed; preserve last published dataset", file=sys.stderr)
        return 1
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
