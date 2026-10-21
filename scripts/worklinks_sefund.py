"""Read-only public notice collector for BAND Foundation (sefund.or.kr).

Discovery is from the official notice listing, not a keyword search index.
Only public article pages are fetched. Loan/member-finance notices and
non-application news are excluded; uncertain conditions remain uncertain.
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

NOTICE_URL = "https://sefund.or.kr/portal/news/notice"
ROOT = "https://sefund.or.kr"
ARTICLE_PATH = re.compile(r"^/portal/news/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.I)
USEFUL = re.compile(
    r"창업|스타트업|벤처기업|투자|IR\b|TIPS|피칭|데모데이|액셀러레이|"
    r"공모|지원사업|성장지원|멘토링|보육|입주|크라우드펀딩|매칭|"
    r"PoC|실증|교육|사업화|육성|협력기업|참여기업|회원기업", re.I)
EXCLUDE = re.compile(r"대출|소액금융|공제회원|채용|결산서류|기부금|연차보고|뉴스레터|선정\s*(결과|공고)", re.I)
DATE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*(?:[.일])?")
TIME = re.compile(r"^(?:\([^)]{1,8}\)\s*)?(\d{1,2})(?:\s*:\s*(\d{2})|\s*시(?:\s*(\d{1,2})\s*분)?)")


def notice_links(soup: BeautifulSoup):
    """Find notice cards by the website's public, semantic CSS selectors."""
    rows = []
    for card in soup.select("a.sf-post-card[href]"):
        u = urljoin(ROOT, card.get("href", ""))
        p = urlsplit(u)
        if p.scheme != "https" or p.netloc != "sefund.or.kr" or not ARTICLE_PATH.fullmatch(p.path):
            continue
        title_el = card.select_one(".sf-post-ctitle")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        badge = card.select_one(".sf-post-badge")
        kind = badge.get_text(" ", strip=True) if badge else ""
        if not title or not USEFUL.search(title) or EXCLUDE.search(title + " " + kind):
            continue
        posted_el = card.select_one(".sf-post-cmeta .portal-tabnum")
        posted = posted_el.get_text(" ", strip=True) if posted_el else ""
        state_el = card.select_one(".sf-dl")
        state_text = state_el.get_text(" ", strip=True) if state_el else ""
        closed = "is-closed" in (card.get("class") or []) or "closed" in (state_el.get("class") or [] if state_el else [])
        rows.append({"url": f"{p.scheme}://{p.netloc}{p.path}", "title": title,
                     "posted": posted, "kind": kind,
                     "closed": closed, "statusText": state_text})
    return rows


def deadline_from_header(soup: BeautifulSoup):
    """Use the explicit closing-date paragraph, never posting or event dates."""
    header = soup.select_one(".sf-post-detail article header")
    if not header:
        return None
    for line in header.select("p"):
        text = line.get_text(" ", strip=True)
        if not re.search(r"(?:접수|신청|모집)\s*마감", text):
            continue
        match = DATE.search(text)
        if not match:
            continue
        year, month, day = map(int, match.groups())
        try:
            date = dt.date(year, month, day)
        except ValueError:
            continue
        following = text[match.end():match.end() + 24].lstrip(" .·~")
        tm = TIME.match(following)
        if not tm:
            return date.isoformat()
        hour = int(tm.group(1))
        minute = int(tm.group(2) or tm.group(3) or 0)
        if hour > 23 or minute > 59:
            return date.isoformat()
        return f"{date.isoformat()}T{hour:02d}:{minute:02d}+09:00"
    return None


def category_for(title: str, body: str):
    both = title + " " + body[:1300]
    if re.search(r"TIPS|팁스", title, re.I):
        return "TIPS·연계"
    if re.search(r"IR\b|피칭|데모데이|투자\s*(?:상담|자|연계|설명)|엔젤|펀딩", title, re.I):
        return "IR·매칭"
    if re.search(r"PoC|실증|오픈이노베이션|사업협력", title, re.I):
        return "CVC·OI"
    if re.search(r"입주|센터|공간|멤버십", title, re.I):
        return "공간·입주"
    if re.search(r"교육|멘토링|컨설팅", title, re.I):
        return "교육·멘토링"
    if re.search(r"액셀러레이|육성|보육", title, re.I):
        return "AC·보육"
    if re.search(r"직접\s*투자|지분\s*투자|임팩트\s*펀드|투자\s*검토|투자연계", both, re.I):
        return "VC·투자"
    return "창업지원·공모"


def eligibility_for(body: str):
    # Mentioning preliminary founders alone is not proof of unconditional admission.
    if re.search(r"(?:예비창업자|예비창업팀).{0,35}(?:제외|신청\s*불가|지원\s*불가)", body):
        return "예비 제외"
    if re.search(r"(?:접수|신청|제출)\s*마감\s*전.{0,35}사업자등록(?:\s*\w{0,5})?\s*(?:완료|필수|제출)", body):
        return "사업자 필수"
    if re.search(r"사업자등록(?:증)?(?:을|이)?\s*.{0,35}(?:완료|필수|제출)\s*(?:하여야|해야|전까지)", body):
        return "사업자 필수"
    if re.search(r"(?:사업자등록증\s*필수|법인사업자\s*(?:전용|한정|만))", body):
        return "사업자 필수"
    if re.search(r"예비\s*창업자|예비\s*창업팀|사업자등록\s*전", body):
        return "예비 언급·조건 확인"
    return "자격 확인 필요"


def record(card: dict, soup: BeautifulSoup | None, now: dt.datetime):
    link = card["url"]
    title = card["title"]
    body_el = soup.select_one(".sf-post-detail .sf-post-body") if soup else None
    body = body_el.get_text(" ", strip=True) if body_el else ""
    detail = bool(soup and soup.select_one(".sf-post-detail article header"))
    header_el = soup.select_one(".sf-post-detail article header") if detail else None
    header_text = header_el.get_text(" ", strip=True) if header_el else ""
    end = deadline_from_header(soup) if detail else None
    description = re.sub(r"\s+", " ", body).strip()[:300] or title
    # URL-derived ID: title/date extensions must not duplicate a notice.
    uuid = link.rsplit("/", 1)[-1]
    return {"id": "sefund-" + uuid, "title": title, "url": link,
            "category": category_for(title, body), "eligibility": eligibility_for(body) if detail else "자격 확인 필요",
            "deadline": end, "description": description, "source": "재단법인 밴드 공식 공지사항",
            "sourceKind": "공식 원문·첨부 자격 재확인 필요" if detail else "공식 목록 확인·상세 원문 접근 실패",
            "lastSeenAt": now.isoformat(timespec="seconds"), "review": "신청 폼·첨부 자격·혜택 직접 확인 필요",
            "sourceStatus": "closed" if card["closed"] or (detail and bool(re.search(r"접수\s*마감된|모집\s*마감된", header_text))) else "unknown" if not card["statusText"] else "listed_open",
            "sourceStatusText": card["statusText"], "publishedDate": card["posted"],
            "attachmentReview": "첨부파일 내용까지 검증되지 않음"}


def scan_band(fetch_html, now: dt.datetime, pages: int = 2):
    """Return (opportunities, source_status). The caller supplies its HTTP fetcher."""
    found: dict[str, dict] = {}
    failed_pages = 0
    for page in range(1, pages + 1):
        url = NOTICE_URL if page == 1 else f"{NOTICE_URL}?page={page}"
        try:
            soup = fetch_html(url)
            cards = notice_links(soup)
            if not soup.select_one(".sf-post-grid"):
                raise ValueError("BAND notice card container missing")
            for item in cards:
                found[item["url"]] = item
        except Exception:
            failed_pages += 1
    if not found and failed_pages:
        raise RuntimeError(f"BAND notice listing unavailable ({failed_pages}/{pages} pages failed)")
    rows = []
    failed_details = 0
    for item in found.values():
        detail = None
        # Retain closed notices so they cannot be resurrected from old snapshots.
        if not item["closed"]:
            try:
                detail = fetch_html(item["url"])
                if not detail.select_one(".sf-post-detail article header"):
                    raise ValueError("BAND article detail not present")
            except Exception:
                failed_details += 1
                detail = None
        rows.append(record(item, detail, now))
    return rows, {"name": "재단법인 밴드 공식 공지", "url": NOTICE_URL,
                  "status": "partial" if failed_pages or failed_details else "ok",
                  "discovered": len(rows), "detailErrors": failed_pages + failed_details,
                  "pagesScanned": pages, "listPagesFailed": failed_pages,
                  "checkedAt": now.isoformat(timespec="seconds")}
