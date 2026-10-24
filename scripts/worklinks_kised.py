"""Official KIS ED (창업진흥원) public-list monitor for WorkLinks.

Read-only discovery on the institution site, not a search-engine result.
Business notices link to the official K-Startup detail; announcement and
tender boards are tracked separately. No source access, eligibility or
closing time is inferred from article age or an unrelated date.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

BUSINESS_URL = "https://www.kised.or.kr/misAnnouncement/index.es?mid=a10302000000"
NOTICE_URL = "https://www.kised.or.kr/board.es?bid=0004&mid=a10301000000"
TENDER_URL = "https://www.kised.or.kr/board.es?bid=0005&mid=a10303000000"
KST = dt.timezone(dt.timedelta(hours=9))
KSTARTUP_PATH = "/web/contents/bizpbanc-ongoing.do"
DATE = re.compile(r"(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})(?:일)?")
DEADLINE = re.compile(
    r"마감일자\s*[:：]?\s*(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})(?:일)?"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", re.I)
NOTICE_RELEVANT = re.compile(
    r"모집|공모|참가|지원사업|입주|창업교육|상담회|설명회|IR\b|TIPS|팁스|"
    r"데모데이|해외진출|투자|액셀러|스타트업|창업기업|정책\s*아이디어", re.I)
NOTICE_EXCLUDE = re.compile(
    r"채용|합격|청렴|개인정보\s*제공|운영계획|결과\s*(안내|발표|공개)|"
    r"선정\s*(결과|발표)|수상자\s*발표|모집\s*결과", re.I)
TENDER_SW = re.compile(
    r"소프트웨어|S/W|SW\s|AI\b|인공지능|정보화|정보시스템|"
    r"데이터|플랫폼|웹(?:사이트|서비스)?|홈페이지|모바일|앱\s|"
    r"API\b|개인정보\s*영향평가|보안\s*(?:점검|검증|컨설팅)|"
    r"전산|디지털\s*(?:전환|플랫폼)|시스템\s*(?:개발|구축|고도화)", re.I)


def compact(text, limit=400):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _record_id(prefix, key):
    return "kised-" + prefix + "-" + hashlib.sha1(str(key).encode()).hexdigest()[:16]


def _date(year, month, day, hour=None, minute=None):
    try:
        day_value = dt.date(int(year), int(month), int(day)).isoformat()
        if hour is None or minute is None:
            return day_value
        h, m = int(hour), int(minute)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return day_value + f"T{h:02d}:{m:02d}:00+09:00"
    except (ValueError, TypeError):
        return None
    return day_value


def business_link(anchor):
    """Use the exact public K-Startup announcement ID, not a home-page URL."""
    href = urljoin(BUSINESS_URL, anchor.get("href", ""))
    parts = urlsplit(href)
    if parts.scheme != "https" or parts.hostname not in ("www.k-startup.go.kr", "k-startup.go.kr"):
        return None
    if parts.path != KSTARTUP_PATH:
        return None
    qs = parse_qs(parts.query)
    ids = qs.get("pbancSn", [])
    if len(ids) != 1 or not re.fullmatch(r"\d{4,12}", ids[0]):
        return None
    return href, ids[0]


def board_link(anchor, bid):
    href = urljoin("https://www.kised.or.kr/", anchor.get("href", ""))
    parts = urlsplit(href)
    params = parse_qs(parts.query)
    if (parts.scheme != "https" or parts.hostname not in ("www.kised.or.kr", "kised.or.kr")
            or parts.path != "/board.es"
            or params.get("act") != ["view"] or params.get("bid") != [bid]
            or not re.fullmatch(r"\d+", (params.get("list_no") or [""])[0])):
        return None
    return href, params["list_no"][0]


def _isolated_card(anchor, match_link, max_chars=1200):
    """Never borrow a deadline from an adjacent article's card."""
    for ancestor in list(anchor.parents)[:8]:
        if not getattr(ancestor, "find_all", None) or ancestor.name in ("body", "html"):
            break
        text = compact(ancestor.get_text(" ", strip=True), max_chars + 1)
        if len(text) > max_chars:
            continue
        links = sum(1 for a in ancestor.find_all("a", href=True) if match_link(a))
        if links == 1:
            yield text


def business_category(title):
    if re.search(r"TIPS|팁스|프리.?팁스", title, re.I):
        return "TIPS·연계"
    if re.search(r"투자|IR\b|피칭|데모데이|벤처캐피탈", title, re.I):
        return "IR·매칭"
    if re.search(r"오픈이노베이션|민관협력|PoC|실증|대기업\s*협업", title, re.I):
        return "CVC·OI"
    if re.search(r"입주|창업보육|창업존|메이커", title, re.I):
        return "공간·입주"
    if re.search(r"법률|멘토링|상담|교육|아카데미", title, re.I):
        return "교육·멘토링"
    return "창업지원·공모"


def _base(title, url, ident, category, now, source, kind, description="", deadline=None):
    return {
        "id": ident,
        "title": compact(title, 180),
        "url": url,
        "category": category,
        "eligibility": "자격 확인 필요",
        "deadline": deadline,
        "description": compact(description, 330),
        "source": source,
        "sourceKind": kind,
        "lastSeenAt": now.isoformat(timespec="seconds"),
        "review": "창업진흥원 공개 목록에서 확인. 무사업자·연령·지역·업력·실적·신청폼·첨부 확인 필요. 지원금/투자 확정 아님.",
        "applicationStatus": "공식 목록 발견·실제 접수상태 및 자격 확인 필요",
    }


def business_rows(soup, now):
    rows = []
    missing = 0
    seen = set()
    for a in soup.select("a[href]"):
        ref = business_link(a)
        if not ref:
            continue
        url, code = ref
        title = compact(a.get_text(" ", strip=True), 180)
        if len(title) < 9 or code in seen:
            continue
        seen.add(code)
        card = next((s for s in _isolated_card(a, business_link, 1700) if "마감일자" in s), "")
        found = DEADLINE.search(card)
        closing = _date(*found.groups()[:5]) if found else None
        if not closing:
            missing += 1
        item = _base(title, url, "kised-biz-" + code, business_category(title), now,
                     "창업진흥원 공식 사업공고", "공식 기관 목록·K-Startup 원문 연결 / 첨부·혜택·자격 별도 검증",
                     "창업진흥원 사업공고 직접 확인. " +
                     ("공식 목록 마감 " + closing if closing else "마감일자 추출 실패 · 시간 미확인"),
                     closing)
        if not closing:
            item["review"] += " 목록 마감일 추출 실패로 기간 미확인."
        elif len(closing) == 10:
            item["review"] += " 마감시각 미확인."
        if "종료" in card and closing and dt.datetime.fromisoformat(
                closing + "T23:59:59+09:00" if len(closing) == 10 else closing) < now:
            item["sourceStatus"] = "closed"
        rows.append(item)
    return rows, len(seen), missing


def _board_cards(soup, bid):
    cards = {}
    for a in soup.select("a[href]"):
        ref = board_link(a, bid)
        if not ref:
            continue
        url, code = ref
        title = compact(a.get_text(" ", strip=True), 180)
        if len(title) < 8:
            continue
        # The closest table row contains the date range; fallback to a
        # uniquely isolated card for mobile layouts.
        tr = a.find_parent("tr")
        if tr and len(tr.find_all("a", href=True)) <= 3:
            snippet = compact(tr.get_text(" ", strip=True), 600)
        else:
            snippet = next(iter(_isolated_card(a, lambda x: board_link(x, bid), 750)), "")
        cards[code] = (url, title, snippet)
    return cards


def notice_rows(soup, now):
    cards = _board_cards(soup, "0004")
    rows = []
    for code, (url, title, snippet) in cards.items():
        if not NOTICE_RELEVANT.search(title) or NOTICE_EXCLUDE.search(title):
            continue
        item = _base(title, url, _record_id("notice", code),
                     business_category(title), now,
                     "창업진흥원 공식 공지사항",
                     "공식 기관 공지 · 모집 여부 및 실제 접수 링크 확인 필요",
                     "공지사항 발견. 모집/행사 공지와 결과·보도는 분리. 마감시각 미확인.")
        item["review"] += " 작성일자는 접수 마감일이 아니므로 마감일로 추정하지 않음."
        rows.append(item)
    return rows, len(cards), 0


def tender_rows(soup, now):
    cards = _board_cards(soup, "0005")
    rows = []
    missing = 0
    for code, (url, title, snippet) in cards.items():
        if not TENDER_SW.search(title):
            continue
        dates = list(DATE.finditer(snippet))
        # Tender list explicitly labels the range as 접수기간; date-only
        # entries stay date-only, never invent a 23:59 closing time.
        close = _date(*dates[-1].groups()) if len(dates) >= 2 else None
        if close is None:
            missing += 1
        item = _base(title, url, _record_id("tender", code),
                     "공개발주·원문검증", now,
                     "창업진흥원 공식 입찰공고",
                     "공공 입찰 후보 · RFP/가격/참가자격·개인 계약 가능 여부 미검증",
                     "소프트웨어·정보화 관련 공개 입찰 후보. 확정 개인 외주 아님. "
                     + ("목록 접수종료일 " + close + " (시각 미확인)" if close else "접수일자 확인 실패"), close)
        item["review"] += " 사업자등록·입찰참가자격·업종·실적·예산/가격·제안서/RFP 원문 확인 필수."
        if "종료" in snippet and close and close < now.date().isoformat():
            item["sourceStatus"] = "closed"
        rows.append(item)
    return rows, len(cards), missing


FEEDS = (
    ("창업진흥원 공식 사업공고", BUSINESS_URL, business_rows),
    ("창업진흥원 공식 공지사항", NOTICE_URL, notice_rows),
    ("창업진흥원 공식 입찰공고", TENDER_URL, tender_rows),
)


def scan_kised(fetch_html, now):
    """An unavailable board is ERROR, not zero opportunities.

    Existing collectors are isolated. No login/private content; only
    public GET requests via the caller's existing official HTML client.
    """
    all_rows, states = [], []
    for name, url, parse in FEEDS:
        try:
            soup = fetch_html(url)
            rows, listed, missing = parse(soup, now)
            if not listed:
                raise ValueError("공식 목록에서 상세 링크 추출 실패(접근 제한/DOM 변경 확인)")
            all_rows.extend(rows)
            states.append({
                "name": name, "url": url,
                "status": "partial" if missing else "ok",
                "discovered": len(rows),
                "listed": listed,
                "detailErrors": missing,
                "pagesScanned": 1,
                "checkedAt": now.isoformat(timespec="seconds"),
                "note": "공식 공개 목록 첫 페이지 직접 수집; 상세 첨부 및 사업자/예비창업자 자격은 별도 검증",
            })
        except Exception as exc:
            states.append({
                "name": name, "url": url, "status": "error", "discovered": 0,
                "detailErrors": 0, "pagesScanned": 0,
                "checkedAt": now.isoformat(timespec="seconds"),
                "error": compact(exc, 170),
            })
    return all_rows, states
