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
    ("청양군 공지·지원", "https://www.cheongyang.go.kr/kor.do", "청양군", "local"),
    ("봉화군 고시공고", "https://www.bonghwa.go.kr/portal/saeol/gosi/list.do?mid=0201030000&seCode=01", "봉화군", "local"),
    ("무주군 소식", "https://www.muju.go.kr/index.9is", "무주군", "local"),
    ("의령군 새소식", "https://www.uiryeong.go.kr/", "의령군", "local"),
    ("단양군 소식", "https://www.danyang.go.kr/dy21/", "단양군", "local"),
    ("기업마당 지역공고", "https://www.bizinfo.go.kr/", "전국 지역공고", "national"),
)
# Later add boards with verified detail selectors. 읍면동 notices are accepted
# when linked by an indexed official municipality page, but there is no
# claim of exhaustive 읍면동 coverage.
POSITIVE = re.compile(r"공모전|아이디어\s*공모|경진대회|시상|상금|포상금|활동비|사업화\s*지원|실증\s*지원|실증비|지원사업|수혜기업\s*모집|재공고|추가\s*모집|긴급\s*모집|바우처|제안\s*공모", re.I)
NEGATIVE = re.compile(r"채용|인사발령|개별공시지가|분묘|폐기물|행정예고|공고\s*취소|합격자|선정\s*결과|입법예고|경매|자격증\s*시험|의견\s*수렴", re.I)
PAYOUT = re.compile(r"상금|포상금|시상금|활동비|사례비|원고료|실증비|사업화\s*지원금|지원금|바우처|상금\s*총액", re.I)
EQUITY_ONLY = re.compile(r"투자\s*(?:유치|상담|검토|심사)|IR\b|멘토링|네트워킹|무료\s*교육|투자자\s*매칭", re.I)
REGION_LIMIT = re.compile(r"(?:관내|해당\s*지역|군내|도내|시내|거주자|주민등록|사업장\s*소재|본점\s*소재|전입|사업자\s*등록|지역에\s*주소)", re.I)
OPEN_TO_ALL = re.compile(r"(?:전\s*국민|누구나|지역\s*제한\s*없음|거주지\s*무관)", re.I)
FAST = re.compile(r"재공고|추가\s*모집|긴급\s*모집|수시\s*모집|연장\s*공고|선착순|예산\s*소진", re.I)
ONLINE = re.compile(r"온라인\s*접수|이메일\s*접수|전자우편|구글\s*폼|네이버\s*폼", re.I)
IN_PERSON = re.compile(r"방문\s*접수|현장\s*접수|직접\s*방문|방문\s*제출", re.I)
CLOSE = re.compile(r"(?:접수\s*(?:마감|종료)|신청\s*(?:마감|기한)|모집\s*(?:마감|종료)|접수\s*기간|신청\s*기간)[^\n\r]{0,95}?(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})(?:일)?", re.I)
DATE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
DETAIL = re.compile(r"(?:view|detail|selectBbsNtt|bbs|article|board|saeol|notice|gosi|pblanc|ntt|idx|sn|seq|no=)", re.I)

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
    if EQUITY_ONLY.search(title) and not direct:
        return None
    region = bool(REGION_LIMIT.search(body))
    everyone = bool(OPEN_TO_ALL.search(body))
    deadline = deadline_from(detail)
    if deadline and deadline < now.date().isoformat():
        return None
    online = bool(ONLINE.search(body))
    in_person = bool(IN_PERSON.search(body))
    fast = bool(FAST.search(title + " " + body))
    score = (4 if direct else 0) + (2 if everyone and not region else 0) + (2 if fast else 0) + (1 if online and not in_person else 0)
    # Rank is a clue, never a probability of winning or an assumed grant.
    grade = "상금형 우선검토" if direct and everyone and not region else "조건부 검토" if direct else "현금 근거 미확인"
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
        "lastSeenAt": now.isoformat(timespec="seconds"), "applied": False,
    }

def fetch_soup(session, url):
    response = session.get(url, timeout=16, headers=HEADERS, allow_redirects=True)
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("too_large")
    return BeautifulSoup(response.text, "html.parser")

def scan_source(spec, session, now):
    name, source_url, municipality, kind = spec
    state = {"name": name, "url": source_url, "status": "error", "discovered": 0, "checkedAt": now.isoformat(timespec="seconds"), "level": "기초지자체 원문" if kind == "local" else "공식 통합 포털"}
    try:
        soup = fetch_soup(session, source_url)
        host = urlsplit(source_url).hostname or ""
        candidates = {}
        for anchor in soup.select("a[href]"):
            title = clean(anchor.get_text(" ", strip=True), 190)
            if len(title) < 9 or not POSITIVE.search(title) or NEGATIVE.search(title):
                continue
            url = urljoin(source_url, anchor.get("href", ""))
            u = urlsplit(url)
            if u.scheme != "https" or not u.hostname or (u.hostname != host and not u.hostname.endswith("." + host)):
                continue
            # Never treat a bare home/list/navigation link as a detail notice.
            if not DETAIL.search(u.path + "?" + u.query) or normalized_url(url) == normalized_url(source_url):
                continue
            candidates[normalized_url(url)] = (url, title)
        rows = []
        errors = 0
        for url, title in list(candidates.values())[:35]:
            try:
                doc = fetch_soup(session, url)
                area = doc.select_one("article") or doc.select_one("main") or doc.select_one("#contents") or doc
                body = area.get_text(" ", strip=True)
                # The notice title must actually occur in the detail document.
                first = re.sub(r"\s+", "", title)[:14]
                if first and first not in re.sub(r"\s+", "", body):
                    errors += 1
                    continue
                row = assess(title, body, municipality, url, now)
                if row:
                    row["sourceKind"] = "지자체 공식 게시판 직접 확인" if kind == "local" else "기업마당 공식 재게시 · 원 발행기관 확인 필요"
                    rows.append(row)
            except (requests.RequestException, ValueError, AttributeError):
                errors += 1
        state.update({"status": "partial" if errors or not candidates else "ok", "discovered": len(rows), "candidateLinks": len(candidates), "detailErrors": errors})
        if not candidates:
            state["status"] = "partial"
            state["note"] = "목록 정상 응답이나 상세공고 링크 0건: 게시판 형식/접근 차단 검토 필요"
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
                      "cashEvidence": sum(r["benefitType"] != "금전 혜택 미확인" for r in values)},
            "coverageNote": "일부 기초지자체 시범 직접수집 및 기업마당 공고. 전국 226개 시군구 또는 전체 읍면동 전수수집은 아님."}

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
