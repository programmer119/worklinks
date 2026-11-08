"""Read-only discovery of KIMSE-related official KHIS opportunities.

Only observed detail links from official public listing pages are followed.
A missing/ambiguous application deadline is never synthesized from event dates.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import xml.etree.ElementTree as ET
from html import escape as html_escape
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
    r"의료|보건|헬스|데이터|빅데이터|디지털|AI|인공지능|병원|실증|바이오|임상|인지|치매|돌봄|표준|진료정보|건강정보",
    re.I,
)
OFFER = re.compile(r"모집|지원|접수|신청|공모|경진|바우처|실증|교육|협력|매칭|설명회|입찰|참여", re.I)
EXCLUDE = re.compile(r"채용|모집\s*결과|선정\s*결과|모집\s*발표|우선협상대상자|낙찰|입찰가격|입찰\s*결과|용역\s*개찰", re.I)
DEADLINE_MARKER = re.compile(r"접수\s*(?:기한|기간|마감|일시)|신청\s*(?:기간|기한|마감)|모집\s*(?:기간|마감)|공모\s*(?:기간|마감)|제출\s*기한", re.I)
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
        row=anchor.find_parent("tr")
        published=None
        if row:
            observed=re.search(r"(20\d{2})[./\-](\d{1,2})[./\-](\d{1,2})",row.get_text(" ",strip=True))
            if observed:
                try:
                    published=dt.date(int(observed[1]),int(observed[2]),int(observed[3]))
                except ValueError:
                    pass
        found[url]=(title,published)
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
            year, month, day_number = int(end[1]), int(end[2]), int(end[3])
            date_end = end.end()
            # Common official format: "2026년 5월 27일 ~ 6월 16일 17:00".
            # The second date is the deadline, not the first date in the range.
            tail = sample[date_end:date_end+95]
            after = SHORT_DAY.search(tail)
            if after and re.search(r"[~～\-–]", tail[:after.start()+1]):
                month, day_number = int(after[1]), int(after[2])
                date_end += after.end()
                if month < int(end[2]):  # crossing December into January
                    year += 1
            elif len(dates) == 1 and not re.search(r"까지|마감|기한|~|～|–|\-", sample[date_end:date_end+35]):
                # A lone start date in an "application period" is not an end.
                continue
            try:
                day = dt.date(year, month, day_number)
            except ValueError:
                continue
            clock = list(HOUR.finditer(sample[date_end:date_end+45]))
            return day.isoformat() + (f"T{int(clock[-1][1]):02d}:{int(clock[-1][2]):02d}:00+09:00" if clock else "")
        # Abbreviated dates get their year only from the observed KHIS posting.
        if isinstance(year_hint,int):
            short=SHORT_DAY.search(sample[:150])
            if short and re.search(r"까지|마감|기한|~|～|–",sample[:150]):
                try:
                    day=dt.date(year_hint,int(short[1]),int(short[2]))
                except ValueError:
                    continue
                clock=list(HOUR.finditer(sample[short.end():short.end()+45]))
                return day.isoformat()+(f"T{int(clock[-1][1]):02d}:{int(clock[-1][2]):02d}:00+09:00" if clock else "")
    return None


def scan_source(spec, fetch, now):
    name, url, board_id = spec
    checked = now.isoformat(timespec="seconds")
    state = {"name": name, "url": url, "status": "error", "discovered": 0,
             "checkedAt": checked, "detailErrors": 0, "articleLinks": 0,
             "relevantLinks": 0, "candidateLinks": 0}
    try:
        soup = fetch(url)
    except (requests.RequestException, ValueError, AttributeError) as exc:
        state["error"] = clean(str(exc), 180)
        return [], state
    found = candidate_links(soup, url, board_id)
    # These are actual observed and validated official article URLs. Expose
    # the same coverage keys as every other KIMSE official source collector.
    state.update(articleLinks=len(found), relevantLinks=len(found),
                 candidateLinks=len(found))
    results = []
    failures = 0
    unknown_deadline = 0
    for detail_url, (title, published) in list(found.items())[:25]:
        try:
            article = fetch(detail_url)
            content = article.select_one("article") or article.select_one(".board_view") or article.select_one("main") or article
            body = content.get_text("\n", strip=True)
            # Ignore nav-only pages and unrelated redirected content.
            # The listing can prepend [안내] / 새글; the article often drops it.
            # Compare normalized substantive title rather than its UI prefix.
            headline=re.sub(r"^(?:새글\s*|\[[^\]]{1,14}\]\s*)+", "", title)
            headline=re.sub(r"[^0-9a-zA-Z가-힣]", "", headline)[:14]
            page_text=re.sub(r"[^0-9a-zA-Z가-힣]", "", clean(body,30000))
            if len(page_text)<20 or (headline and headline not in page_text):
                failures += 1
                continue
            deadline = application_deadline(title, body, published.year if published else None)
            if not deadline:
                unknown_deadline += 1
                continue  # Never publish a possibly finished training/event as open.
            if deadline[:10] < now.date().isoformat():
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
        "status": "partial" if failures or unknown_deadline or not found or len(found) > 25 else "ok",
        "discovered": len(results), "candidateLinks": len(found),
        "detailErrors": failures, "unknownDeadline": unknown_deadline,
        "candidateLimitReached": len(found) > 25,
    })
    if not found:
        state["note"] = "공식 목록 접근은 성공했으나 상세 링크 0건 · CSS/페이지 형식 확인 필요"
    return results, state


KHIS_TENDER_RSS = "https://www.khis.kr/rss/board.es?bid=0009&mid=a10304000000"


def official_rss_listing(content, board_id="0009"):
    """Convert observed KHIS official RSS entry links to an HTML listing.
    A feed that cannot be validated stays an error, never an empty result.
    """
    root = ET.fromstring(content)
    items = root.findall(".//item")
    if not items:
        raise ValueError("KHIS official RSS contains no items")
    rows = []
    # Keep the two newest public listing pages. Older items remain historical,
    # while deep fetches of old tenders can exhaust the live monitor time budget.
    for item in items[:20]:
        title = clean(item.findtext("title"), 240)
        link = str(item.findtext("link") or "").strip()
        parts = urlsplit(link)
        q = parse_qs(parts.query)
        if (parts.scheme != "https" or
                parts.hostname not in ("www.khis.kr","khis.kr") or
                parts.path != "/board.es" or
                q.get("act") != ["view"] or
                q.get("bid") != [board_id] or
                q.get("mid") != ["a10304000000"]):
            continue
        ids = q.get("list_no", [])
        if len(ids) != 1 or not re.fullmatch(r"\d{1,8}", ids[0]):
            continue
        published = clean(item.findtext("pubDate"), 80)
        rows.append("<tr><td><a href=\"" + html_escape(link, quote=True) +
                    "\">" + html_escape(title) + "</a></td><td>" +
                    html_escape(published) + "</td></tr>")
    if not rows:
        raise ValueError("KHIS official RSS lacks verified notice article URLs")
    return BeautifulSoup("<table>" + "".join(rows) + "</table>", "html.parser")


def scan_health_sources(fetch=None, now=None):
    now = now or dt.datetime.now(KST)
    if fetch is None:
        def fetch(url):
            try:
                response = requests.get(url, headers=HEADERS, timeout=(6, 12))
            except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout):
                # Use the explicitly linked, officially published RSS endpoint
                # if the KHIS tender board HTML is slow or unresponsive.
                if url == SOURCES[1][1]:
                    try:
                        feed = requests.get(KHIS_TENDER_RSS, headers=HEADERS,
                                            timeout=(6, 14))
                        feed.raise_for_status()
                        if len(feed.content) > 3_000_000:
                            raise ValueError("KHIS RSS response too large")
                        return official_rss_listing(feed.content, "0009")
                    except (requests.RequestException, ValueError, ET.ParseError):
                        pass
                # Bounded final attempt: a second failure is retained as an
                # error rather than a false no-opportunity result.
                response = requests.get(url, headers=HEADERS, timeout=(6, 16))
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
