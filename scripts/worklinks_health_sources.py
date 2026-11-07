"""Read-only discovery of KIMSE-related official KHIS opportunities.

Only observed detail links from official public listing pages are followed.
A missing/ambiguous application deadline is never synthesized from event dates.
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
    ("한국보건의료정보원 공식 공지", "https://www.khis.kr/board.es?bid=0001&mid=a10301000000", "0001"),
    ("한국보건의료정보원 실증·사업 공고", "https://www.khis.kr/board.es?bid=0009&mid=a10304000000", "0009"),
)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WorkLinks/1.0 public-notice-monitor)",
           "Accept-Language": "ko-KR,ko;q=0.9"}
DOMAIN = re.compile(
    r"의료|보건|헬스|데이터|빅데이터|디지털|AI\b|인공지능|병원|실증|바이오|임상|인지|치매|돌봄|표준",
    re.I,
)
OFFER = re.compile(r"모집|지원|접수|신청|공모|경진|바우처|실증|교육|협력|매칭|설명회|입찰|참여", re.I)
EXCLUDE = re.compile(r"채용|선정\s*결과|우선협상대상자|낙찰|입찰가격|입찰\s*결과|용역\s*개찰", re.I)
DEADLINE_MARKER = re.compile(r"접수\s*(?:기한|기간|마감|일시)|신청\s*(?:기간|기한|마감)|모집\s*(?:기간|마감)|제출\s*기한", re.I)
FULL_DAY = re.compile(
    r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})\s*(?:일)?(?:\([월화수목금토일]\))?",
    re.I,
)
SHORT_DAY = re.compile(r"(?<!\d)(\d{1,2})[./월\s]+(\d{1,2})\s*(?:일)?(?!\d)")
HOUR = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")


def clean(value, limit=600):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def candidate_links(soup, base, board_id):
    """Return only observed KHIS article links with matching bid/list_no."""
    found = {}
    for anchor in soup.select("a[href]"):
        title = clean(anchor.get_text(" ", strip=True), 180)
        if len(title) < 8 or not DOMAIN.search(title) or not OFFER.search(title) or EXCLUDE.search(title):
            continue
        url = urljoin(base, anchor.get("href", ""))
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname not in ("khis.kr", "www.khis.kr") or p.path != "/board.es":
            continue
        q = parse_qs(p.query)
        if q.get("act") != ["view"] or q.get("bid") != [board_id]:
            continue
        number = q.get("list_no", [""])[0]
        if not re.fullmatch(r"\d{1,8}", number):
            continue
        # Canonicalize only values observed in source links; no guessed IDs.
        url = f"https://www.khis.kr/board.es?act=view&bid={board_id}&list_no={number}&mid=" + (
            "a10301000000" if board_id == "0001" else "a10304000000"
        )
        found[url] = title
    return found


def application_deadline(title, body, year_hint=None):
    """Require an actual application label; do not use project/event end date."""
    pieces = [clean(x, 450) for x in body.splitlines() if clean(x)]
    for i, part in enumerate(pieces):
        marker = DEADLINE_MARKER.search(part)
        if not marker:
            continue
        sample = part[marker.start():]
        if len(sample) < 65 and i + 1 < len(pieces):
            sample += " " + pieces[i + 1]
        dates = list(FULL_DAY.finditer(sample[:300]))
        if dates:
            end = dates[-1]
            try:
                day = dt.date(int(end[1]), int(end[2]), int(end[3]))
            except ValueError:
                continue
            clock = list(HOUR.finditer(sample[end.end():end.end()+50]))
            return day.isoformat() + (f"T{int(clock[-1][1]):02d}:{int(clock[-1][2]):02d}:00+09:00" if clock else "")
        # E.g. a title says "(~11/6 17:00)" but source has no full year.
        # We do not assume which year or which duration the range applies to.
    return None


def scan_source(spec, fetch, now):
    name, url, board_id = spec
    checked = now.isoformat(timespec="seconds")
    state = {"name": name, "url": url, "status": "error", "discovered": 0,
             "checkedAt": checked, "detailErrors": 0}
    try:
        soup = fetch(url)
    except (requests.RequestException, ValueError, AttributeError) as exc:
        state["error"] = clean(str(exc), 180)
        return [], state
    found = candidate_links(soup, url, board_id)
    results = []
    failures = 0
    unknown_deadline = 0
    for detail_url, title in list(found.items())[:25]:
        try:
            article = fetch(detail_url)
            content = article.select_one("article") or article.select_one(".board_view") or article.select_one("main") or article
            body = content.get_text("\n", strip=True)
            # Ignore nav-only pages and unrelated redirected content.
            if clean(title, 35).replace(" ", "")[:12] not in clean(body, 30000).replace(" ", ""):
                failures += 1
                continue
            deadline = application_deadline(title, body, now.year)
            if not deadline:
                unknown_deadline += 1
            elif deadline[:10] < now.date().isoformat():
                continue
            identity = hashlib.sha1((detail_url + "|" + title).encode()).hexdigest()[:17]
            results.append({
                "id": "khis-" + identity, "title": title, "url": detail_url,
                "category": "창업지원·공모", "eligibility": "자격 확인 필요",
                "deadline": deadline, "description": clean(body, 300),
                "source": name, "sourceKind": "공식 게시판 원문 · 신청자격 별도 검증 필요",
                "lastSeenAt": checked, "sourceStatus": "unknown",
                "review": "예비창업자 자격·지원규모·실제 신청 가능 여부는 원문 및 첨부 확인 필요",
            })
        except (requests.RequestException, ValueError, AttributeError) as exc:
            failures += 1
    state.update({
        "status": "partial" if failures or not found or len(found) > 25 else "ok",
        "discovered": len(results), "candidateLinks": len(found),
        "detailErrors": failures, "unknownDeadline": unknown_deadline,
        "candidateLimitReached": len(found) > 25,
    })
    if not found:
        state["note"] = "공식 목록 접근은 성공했으나 상세 링크 0건 · CSS/페이지 형식 확인 필요"
    return results, state


def scan_health_sources(fetch=None, now=None):
    now = now or dt.datetime.now(KST)
    if fetch is None:
        def fetch(url):
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError("HTML body too large")
            return BeautifulSoup(response.text, "html.parser")
    all_rows, states = [], []
    for spec in SOURCES:
        rows, status = scan_source(spec, fetch, now)
        all_rows.extend(rows)
        states.append(status)
    return all_rows, states
