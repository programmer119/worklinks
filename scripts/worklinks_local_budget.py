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
POSITIVE = re.compile(r"공모전|아이디어\s*공모|경진대회|시상|상금|포상금|활동비|사업화\s*지원|실증\s*지원|실증비|지원사업|수혜기업\s*모집|재공고|추가\s*모집|긴급\s*모집|바우처|제안\s*공모|창업\s*지원|참여기업\s*모집|헬스케어|치매|고령친화|의료\s*AI", re.I)
NEGATIVE = re.compile(r"채용|인사발령|개별공시지가|분묘|폐기물|행정예고|공고\s*취소|합격자|선정\s*결과|입법예고|경매|자격증\s*시험|의견\s*수렴", re.I)
PAYOUT = re.compile(r"상금|포상금|시상금|활동비|사례비|원고료|실증비|사업화\s*지원금|지원금|바우처|상금\s*총액", re.I)
EQUITY_ONLY = re.compile(r"투자\s*(?:유치|상담|검토|심사)|IR\b|멘토링|네트워킹|무료\s*교육|투자자\s*매칭", re.I)
REGION_LIMIT = re.compile(r"(?:관내|해당\s*지역|군내|도내|시내|거주자|주민등록|사업장\s*소재|본점\s*소재|전입|지역에\s*주소|지역\s*(?:기업|소재|거주))", re.I)
OPEN_TO_ALL = re.compile(r"(?:전\s*국민|누구나|지역\s*제한\s*없음|거주지\s*무관)", re.I)
FAST = re.compile(r"재공고|추가\s*모집|긴급\s*모집|수시\s*모집|연장\s*공고|선착순|예산\s*소진", re.I)
ONLINE = re.compile(r"온라인\s*접수|이메일\s*접수|전자우편|구글\s*폼|네이버\s*폼", re.I)
IN_PERSON = re.compile(r"방문\s*접수|현장\s*접수|직접\s*방문|방문\s*제출", re.I)
CLOSE = re.compile(r"(?:접수\s*(?:마감|종료)|신청\s*(?:마감|기한)|모집\s*(?:마감|종료)|접수\s*기간|신청\s*기간)[^\n\r]{0,95}?(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})(?:일)?", re.I)
DATE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
DETAIL = re.compile(r"(?:view|detail|selectBbsNtt|bbs|article|board|saeol|notice|gosi|pblanc|ntt|idx|sn|seq|no=|mode=V|action=view)", re.I)
KIMSE = re.compile(r"치매|인지\s*(?:저하|장애)|고령\s*친화|에이지\s*테크|에이지테크|헬스케어|디지털\s*헬스|의료\s*AI|음성\s*바이오마커|돌봄|시니어", re.I)
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
    if PAYOUT.search(text):
        # Avoid inventing an award to a single winner from a total prize pool.
        m = re.search(r"(?:(?:총\s*)?상금|시상금|포상금|활동비|실증비|사업화\s*지원금|지원금)[^\n]{0,46}?(\d[\d,]*(?:\.\d+)?\s*(?:억원|천만원|백만원|만원|천원|원))", text, re.I)
        return ("상금·포상·활동비" if re.search(r"상금|포상금|시상금|활동비|사례비|원고료", text) else "사업비·바우처"), (clean(m.group(0), 90) if m else "금액·개별 지급조건 원문 확인")
    return "금전 혜택 미확인", "지급액·수익 여부 원문 확인"

def deadline_from(body):
    # Never mistake the publication date or the START of a range for its end.
    dates = []
    date = r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})(?:일)?"
    ranged = re.compile(r"(?:접수|신청|모집)\s*(?:기간|일정)[^0-9]{0,32}" + date +
                        r"\s*(?:~|∼|～|부터|\-|–|—)\s*" + date)
    explicit = re.compile(r"(?:접수|신청|모집)?\s*(?:마감일|마감|종료일|신청기한)[^0-9]{0,20}" + date)
    for pattern, offset in ((ranged, 4), (explicit, 1)):
        for m in pattern.finditer(body):
            values = m.groups()[offset-1:offset+2]
            try:
                dates.append(dt.date(*(int(x) for x in values)))
            except ValueError:
                pass
    return max(dates).isoformat() if dates else None

def assess(title, detail, municipality, url, now):
    if len(title) < 9 or not POSITIVE.search(title) or NEGATIVE.search(title):
        return None
    body = clean(detail, 10000)
    if not body or not POSITIVE.search(title + " " + body[:2000]):
        return None
    # Promotional and press-releases with no concrete application are not
    # published as actionable notices.
    if not re.search(r"공고|모집|공모|접수|신청|시상", title + " " + body[:1200]):
        return None
    benefit, money = amount_info(title, body)
    direct = bool(PAYOUT.search(title + " " + body[:3500]))
    kimse = bool(KIMSE.search(title + " " + body[:3500]))
    commercialization = bool(re.search(r"사업화|시제품|기술\s*실증|검증\s*지원|바우처|지원금|상금|활동비", title, re.I))
    # Re-announcements with no financial or product value are noise.
    if EQUITY_ONLY.search(title) and not direct and not kimse:
        return None
    if not direct and not commercialization and not kimse:
        return None
    region = bool(REGION_LIMIT.search(body))
    everyone = bool(OPEN_TO_ALL.search(body))
    deadline = deadline_from(detail)
    if deadline and deadline < now.date().isoformat():
        return None
    online = bool(ONLINE.search(body))
    in_person = bool(IN_PERSON.search(body))
    fast = bool(FAST.search(title + " " + body))
    applicant = bool(APPLICANT.search(body))
    business_only = bool(BUSINESS_ONLY.search(body))
    score = (5 if direct else 0) + (4 if kimse else 0) + (2 if applicant and not region and not business_only else 0) + (2 if fast else 0) + (1 if online and not in_person else 0) - (4 if region else 0)
    # Signals for manual review, NEVER an assertion of eligibility.
    grade = "현금성·자격 검토" if direct and applicant and not region and not business_only else "낌새 관련 검토" if kimse else "지역·사업자 조건부 검토" if direct else "지원내용 확인 필요"
    condition = ("지역 자격 제한 가능 · 원문 확인" if region else "지역 제한 발견 안 됨 · 공고 원문 확인")
    condition += " · 온라인 제출 표시" if online and not in_person else " · 접수방식 확인 필요"
    return {
        "id": notice_id(normalized_url(url)), "title": clean(title, 180), "url": url,
        "monitorTrack": "yearEndLocalBudget", "category": "general",
        "source": municipality, "sourceKind": "지자체 직접 원문 또는 공식 기관 재게시",
        "deadline": deadline or "", "period": ("공식 게시 · 마감 " + deadline if deadline else "접수 마감일 미확인"),
        "support": benefit + " · " + grade + (" · 추가/긴급/재모집 단서" if fast else ""),
        "money": money, "condition": condition + " · 신청자격 및 개인 수령액 검토 필요",
        "eligibility": "uncertain", "reviewGrade": grade, "reviewScore": score,
        "benefitType": benefit, "regionRestrictionHint": region, "applicationOnlineHint": online,
        "preStartupHint": applicant, "businessRequiredHint": business_only,
        "kimseRelevantHint": kimse,
        "quickWinTier": "cash_candidate" if direct and applicant and not region and not business_only else "kimse_candidate" if kimse else "regional_or_unverified",
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
