"""Direct official-page monitoring for international founder accelerators.

Never infer eligibility or a live application window from the existence of an
"Apply" link. A failed source must remain visible in the snapshot.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

KST = dt.timezone(dt.timedelta(hours=9))
PACIFIC = ZoneInfo("America/Los_Angeles")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WorkLinks/1.0; public opportunity monitor)",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
MONTHS = (
    "January February March April May June July August September October "
    "November December"
).split()


def current_time():
    return dt.datetime.now(KST)


def fetch_page(url):
    response = requests.get(url, headers=HEADERS, timeout=16)
    response.raise_for_status()
    if len(response.content) > 4_500_000:
        raise ValueError("official HTML exceeds size limit")
    return BeautifulSoup(response.text, "html.parser")


def plain(soup):
    for node in soup.select("script,style,nav,footer"):
        node.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def record(source, title, url, description, deadline=None, status="unknown", note=""):
    stamp = current_time().isoformat(timespec="seconds")
    return {
        "id": hashlib.sha256((url.split("?")[0].rstrip("/") + "|" + title).encode()).hexdigest()[:20],
        "title": title[:180],
        "url": url,
        "category": "AC·보육",
        "eligibility": "자격 확인 필요",
        "deadline": deadline,
        "description": description[:300],
        "source": source,
        "sourceKind": "공식 모집페이지 자동 확인",
        "sourceStatus": status,
        "lastSeenAt": stamp,
        "review": note or "지원 가능 국적·체류·현지 참여·투자 지분 조건은 공식 원문에서 확인",
    }


def report(name, url, rows, errors=0, scanned=0, message=""):
    return {
        "name": name,
        "url": url,
        "status": "error" if (errors and not rows) or not scanned else "partial" if errors else "ok",
        "discovered": len(rows),
        "detailErrors": errors,
        "pagesScanned": scanned,
        "error": message[:170],
        "checkedAt": current_time().isoformat(timespec="seconds"),
    }


def antler():
    name = "Antler Korea 공식 레지던시"
    url = "https://www.antler.co/location/korea"
    soup = fetch_page(url)
    text = plain(soup)
    if len(text) < 300 or not re.search(r"Antler|앤틀러", text, re.I):
        raise ValueError("Antler Korea official content not found")
    rolling = bool(re.search(r"applications.{0,60}accepted year.round|연중.{0,20}(접수|신청)", text, re.I))
    title = "Antler Korea 창업자 레지던시 (상시 신청)" if rolling else "Antler Korea 창업자 레지던시 (접수상태 확인)"
    rows = [record(name, title, url, text[:300], status="listed_open" if rolling else "unknown",
                   note="개인·팀 유형별 신청 필요. 평일 전일제 참여와 투자·지분 조건을 확인")]
    return rows, report(name, url, rows, scanned=1)


def parse_yc(text):
    batch = re.search(r"\b(Winter|Spring|Summer|Fall)\s+(20\d{2})\s+Batch\b", text, re.I)
    if not batch:
        return None
    season, batch_year = batch.group(1).title(), int(batch.group(2))
    m = re.search(
        r"deadline to apply on.time is\s+([A-Za-z]+)\s+(\d{1,2})\s+at\s+(\d{1,2})\s*(am|pm)\s*PT",
        text, re.I,
    )
    deadline = None
    if m and m.group(1).title() in MONTHS:
        month = MONTHS.index(m.group(1).title()) + 1
        h = int(m.group(3)) % 12 + (12 if m.group(4).lower() == "pm" else 0)
        # YC's Winter batch starts in the following calendar year.
        year = batch_year - 1 if season == "Winter" else batch_year
        day = dt.datetime(year, month, int(m.group(2)), h, tzinfo=PACIFIC)
        deadline = day.astimezone(KST).isoformat(timespec="minutes")
    accepting = bool(re.search(r"accepting applications for the\s+" + re.escape(season)
                                + r"\s+" + str(batch_year) + r"\s+Batch", text, re.I))
    return season, batch_year, deadline, accepting


def yc():
    name, url = "Y Combinator 공식 모집", "https://www.ycombinator.com/apply"
    text = plain(fetch_page(url))
    parsed = parse_yc(text)
    if not parsed:
        raise ValueError("YC batch or official application evidence not found")
    season, year, deadline, accepting = parsed
    label = "Y Combinator " + season + " " + str(year)
    rows = [record(name, label + " 공식 배치 지원", url, text[:300], deadline,
                   "listed_open" if accepting else "unknown",
                   "정규 마감 이후 접수 가능 여부와 미국 프로그램 참여·SAFE 투자 조건 확인")]
    return rows, report(name, url, rows, scanned=1)


def parse_techstars_deadline(text):
    for pattern in (
        r"\b([A-Za-z]{3,9})\s+(\d{1,2})\s+(20\d{2})\s+Final Deadline\b",
        r"\bFinal Deadline\s+([A-Za-z]{3,9})\s+(\d{1,2})\s+(20\d{2})\b",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            for fmt in ("%b %d %Y", "%B %d %Y"):
                try:
                    end = dt.datetime.strptime(" ".join(match.groups()), fmt)
                    return end.replace(hour=23, minute=59, tzinfo=PACIFIC).astimezone(KST).isoformat(timespec="minutes")
                except ValueError:
                    continue
    return None


def techstars():
    name, url = "Techstars 공식 액셀러레이터", "https://www.techstars.com/accelerators"
    soup = fetch_page(url)
    text = plain(BeautifulSoup(str(soup), "html.parser"))
    if "Techstars" not in text:
        raise ValueError("Techstars official accelerator listing not found")
    links = {}
    for a in soup.select("a[href]"):
        target = urljoin(url, a.get("href", "")).split("#")[0].split("?")[0].rstrip("/")
        parts = urlsplit(target)
        if parts.netloc not in ("techstars.com", "www.techstars.com"):
            continue
        if not re.fullmatch(r"/accelerators/[a-z0-9-]+", parts.path):
            continue
        links[target] = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
    if not links:
        raise ValueError("Techstars program links not exposed in listing")
    rows, errors = [], 0
    scanned = 1
    for target, fallback_title in list(links.items())[:40]:
        try:
            body = plain(fetch_page(target))
            scanned += 1
            if "Techstars" not in body or len(body) < 200:
                raise ValueError("missing official program page")
            end = parse_techstars_deadline(body)
            if not end and not re.search(r"Applications Open|Final Deadline", body, re.I):
                # Preserve a reviewable lead rather than mislabelling this as open.
                state = "unknown"
            else:
                state = "unknown" if not end else "listed_open"
            title = fallback_title.strip() or target.rsplit("/", 1)[-1].replace("-", " ").title()
            if not re.search("Techstars", title, re.I):
                title = "Techstars " + title
            rows.append(record(name, title, target, body[:300], end, state,
                               "지원 가능 국적·프로그램 도시·산업 제한·현지 체류·투자 조건 확인"))
        except (requests.RequestException, ValueError):
            errors += 1
    return rows, report(name, url, rows, errors=errors, scanned=scanned,
                        message="일부 세부 프로그램 페이지 접근 실패" if errors else "")


def parse_ef_deadline(text):
    m = re.search(r"\bApply by\s*:?\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if not m:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            d = dt.datetime.strptime(" ".join(m.groups()), fmt)
            return d.date().isoformat()
        except ValueError:
            pass
    return None


def entrepreneur_first():
    name, url = "Entrepreneurs First 공식 지원", "https://apply.joinef.com/"
    soup = fetch_page(url)
    text = plain(BeautifulSoup(str(soup), "html.parser"))
    if "Entrepreneurs First" not in text and "Apply to Entrepreneurs First" not in text:
        raise ValueError("EF official application listing not found")
    links = {}
    for a in soup.select("a[href]"):
        target = urljoin(url, a.get("href", "")).split("#")[0].split("?")[0].rstrip("/")
        parts = urlsplit(target)
        if parts.netloc == "apply.joinef.com" and re.fullmatch(r"/app/[a-z0-9-]+", parts.path):
            links[target + "/"] = True
    # Direct official entry points cover dynamically rendered program lists too.
    for seed in ("https://apply.joinef.com/app/bangalore-winter/",
                 "https://apply.joinef.com/app/san-francisco-thebridge-winter/"):
        links.setdefault(seed, True)
    rows, errors, scanned = [], 0, 1
    for target in list(links)[:25]:
        try:
            detail = plain(fetch_page(target))
            scanned += 1
            if len(detail) < 100 or not re.search(r"Apply|Residency|Program", detail, re.I):
                raise ValueError("EF application detail missing")
            title_match = re.search(r"Apply to (?:the )?(.{4,90}?)\s*(?:Program|\.|More Information)", detail, re.I)
            title = "Entrepreneurs First " + (title_match.group(1).strip() if title_match else
                     target.split("/app/")[-1].strip("/").replace("-", " ").title()) + " 지원"
            end = parse_ef_deadline(detail)
            rows.append(record(name, title, target, detail[:300], end,
                               "unknown" if not end else "listed_open",
                               "지역별 자격·비자·전일제 참여 제한과 마감 회차 확인"))
        except (requests.RequestException, ValueError):
            errors += 1
    if not rows:
        # A live application landing page is still important to surface,
        # but its availability does NOT prove any particular cohort is open.
        rows = [record(name, "Entrepreneurs First 지원 프로그램 확인", url, text[:300],
                       status="unknown", note="개별 모집의 접수·지역·비자 요건 직접 확인")]
    return rows, report(name, url, rows, errors, scanned,
                        "세부 프로그램 페이지 일부 접근 실패" if errors else "")


OFFICIAL_COLLECTORS = (
    ("Antler Korea 공식 레지던시", antler),
    ("Y Combinator 공식 모집", yc),
    ("Techstars 공식 액셀러레이터", techstars),
    ("Entrepreneurs First 공식 지원", entrepreneur_first),
)


def scan_global():
    rows, states = [], []
    for name, function in OFFICIAL_COLLECTORS:
        try:
            entries, state = function()
            rows.extend(entries)
            states.append(state)
        except (requests.RequestException, ValueError, AttributeError) as exc:
            states.append(report(name, {
                "Antler Korea 공식 레지던시": "https://www.antler.co/location/korea",
                "Y Combinator 공식 모집": "https://www.ycombinator.com/apply",
                "Techstars 공식 액셀러레이터": "https://www.techstars.com/accelerators",
                "Entrepreneurs First 공식 지원": "https://apply.joinef.com/",
            }[name], [], errors=1, scanned=0, message=str(exc)))
    return rows, states
