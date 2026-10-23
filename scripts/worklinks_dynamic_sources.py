"""Isolated browser-based discovery for public, JavaScript-driven startup/IR listings.

No authentication, application submission, private API access, or modification of
external services. Source failures are reported as partial/error, never as zero
available opportunities. The legacy collectors run independently.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

KST = dt.timezone(dt.timedelta(hours=9))
PROJECT_URL = "https://www.startup-plus.kr/project"
IR_URL = "https://irchallenge.jointips.or.kr/apply"
RELEVANT = re.compile(r"투자|엔젤|IR|TIPS|팁스|창업|매칭|오픈이노베이션|PoC|실증|협업|멘토|교육|입주|보육|해외", re.I)
ID_RE = re.compile(r"^PRJ[0-9]{5,9}$", re.I)
MONTH_DATE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
DAY_DATE = re.compile(r"(\d{1,2})월\s*(\d{1,2})일")
DATE_KEYS = ("applyDeadline", "applicationEndDate", "applyEndDate", "receiptEndDate", "recruitEndDate",
             "applicationEndAt", "applyEndAt", "endDate", "endDt", "closeDate", "deadline",
             "endDtm", "rcptEndDt")
PROJECT_IDS = ("projectCode", "projectCd", "prjCode", "prjCd", "project_id", "projectId")
PROJECT_TITLES = ("projectName", "projectNm", "projectTitle", "projectSubject",
                  "businessName", "businessNm", "title", "subject")
OPERATOR_NAMES = ("operatorName", "operatorNm", "companyName", "companyNm",
                  "investorName", "investorNm", "orgName", "organizationName")
IR_DATES = ("meetDate", "irDate", "irDay", "eventDate", "scheduleDate", "meetingDate",
            "programDate", "irStartDate", "irStartAt", "startDate")
PROGRAM_IDS = ("slotId", "irProgramId", "programId", "scheduleId", "irId", "sessionId")

def clean(value, n=220):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:n]

def first(obj, keys):
    for name in keys:
        val = obj.get(name)
        if val is not None and not isinstance(val, (dict, list)) and clean(val):
            return clean(val)
    return ""

def date_value(value):
    """Only output a time when the original source explicitly provides one."""
    if value is None:
        return None
    raw = str(value).strip()
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    m = MONTH_DATE.search(raw)
    if not m:
        return None
    result = f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    tm = re.search(r"(?:T|\s)(\d{2}):(\d{2})", raw[m.end():m.end()+12])
    return result + f"T{tm[1]}:{tm[2]}:00+09:00" if tm else result

def objects(data, depth=0):
    if depth > 9:
        return
    if isinstance(data, dict):
        yield data
        for value in data.values():
            if isinstance(value, (dict, list)):
                yield from objects(value, depth+1)
    elif isinstance(data, list):
        for obj in data[:1500]:
            yield from objects(obj, depth+1)

def record_id(prefix, *parts):
    return prefix + "-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]

def project_record(obj):
    code = first(obj, PROJECT_IDS)
    title = first(obj, PROJECT_TITLES)
    if not ID_RE.fullmatch(code) or len(title) < 7 or title == code:
        return None
    deadline = date_value(first(obj, DATE_KEYS))
    desc = first(obj, ("supportContents", "supportContent", "projectDescription",
                       "content", "description", "summary"))
    org = first(obj, ("organizationName", "organizationNm", "orgName", "centerName"))
    return {
        "id": record_id("startup-plus", code), "title": title,
        "url": PROJECT_URL + "/" + code,
        "category": "IR·매칭" if re.search(r"투자|IR|피칭|매칭|오픈이노베이션",title,re.I) else "창업지원·공모",
        "eligibility": "자격 확인 필요",
        "deadline": deadline, "description": clean((org+" · "+desc).strip(" ·"), 300),
        "source": "서울 스타트업플러스 지원사업",
        "sourceKind": "공식 공개목록·개별 공고원문 자격 검증 필요",
        "review": "사업자등록·연령·소재지·실제 신청폼 확인 필요",
        "lastSeenAt":dt.datetime.now(KST).isoformat(timespec="seconds"),
    }

def ir_record(obj):
    operator = first(obj, OPERATOR_NAMES)
    date = date_value(first(obj, IR_DATES))
    program = first(obj, PROGRAM_IDS)
    # A session needs a specific operator AND date. Never promote a generic
    # operator profile, investor ad, or dashboard statistics into an IR round.
    if len(operator) < 2 or not date:
        return None
    name = first(obj, ("eventName", "programName", "programTitle", "irTitle", "title"))
    if name and not (RELEVANT.search(name) or "IR" in name.upper()):
        name = ""
    limit = first(obj, ("capacity", "recruitCount", "maxApplicantCount", "applyLimit"))
    remaining = first(obj, ("remaining", "remainingCount", "remainCount", "availableCount"))
    closing = date_value(first(obj, DATE_KEYS))
    if not closing:
        closing = None  # Seven-days-before is a rule, not a verified clock time.
    status = first(obj, ("applicationStatus", "applyStatus", "roundStatus", "status", "recruitStatus"))
    session_key = program or (operator+"|"+date+"|"+name)
    limit_value = obj.get("operatorApplyLimit")
    submitted_value = obj.get("appliedCount")
    remaining_applications = None
    if isinstance(limit_value,int) and isinstance(submitted_value,int):
        remaining_applications = max(0,limit_value-submitted_value)
    is_closed = (obj.get("meetingClosed") is True or
                 status.upper() in ("CLOSED","END","ENDED") or
                 remaining_applications == 0)
    if closing:
        try:
            if dt.date.fromisoformat(closing[:10]) < dt.datetime.now(KST).date():
                is_closed = True
        except ValueError:
            pass
    eligibility = "예비 언급·조건 확인"
    max_years = obj.get("bizYears")
    industries = []
    for key in ("industry12Tags", "industryStdTags"):
        val = obj.get(key)
        if isinstance(val,str):
            try: val=json.loads(val)
            except (ValueError,TypeError): val=[]
        if isinstance(val,list):
            industries += [clean(x.get("nm"),40) for x in val if isinstance(x,dict) and x.get("nm")]
    tags = "·".join(dict.fromkeys(industries))[:120]
    description = (date+" IR · "+clean(obj.get("regionText"),45)+
         (f" · 업력기준 {max_years}년" if isinstance(max_years,int) else "")+
         (f" · 투자분야 {tags}" if tags else "")+
         (f" · 운영사 접수 {submitted_value}/{limit_value}" if remaining_applications is not None else "")+
         (f" · IR 미팅 가능 {obj.get('capacity')}개사" if isinstance(obj.get("capacity"),int) else "")+
         (" · 마감/접수종료" if is_closed else " · 신청상태 별도 확인"))
    return {
        "id": record_id("ir-slot", session_key),
        "title": operator+" — "+(name or "도전의 IR")+" ("+date[:10]+")",
        "url": IR_URL, "category": "TIPS·연계",
        "eligibility": eligibility,
        "deadline": closing,
        "description": clean(description,450),
        "source":"도전의 IR 운영사별 프로그램",
        "sourceKind":"정부·TIPS 운영사 투자상담/IR 신청·투자/TIPS 선정 보장 없음",
        "review":"운영사별 접수자격·IR 자료·최대 2회 투자제안·조기마감 확인. 마감시각 미확인.",
        "operator":operator, "irDate":date, "programId":program or None,
        "applicationStatus":"마감" if is_closed else "접수중(공개정보)",
        "sourceStatus":"closed" if is_closed else "unknown",
        "lastSeenAt":dt.datetime.now(KST).isoformat(timespec="seconds"),
    }

def _schema_keys(value, depth=0):
    """Describe nested public JSON structure without retaining any raw values."""
    if depth >= 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k)[:60]:_schema_keys(v,depth+1) for k,v in list(value.items())[:18]}
    if isinstance(value, list):
        return {"count":len(value),"item":_schema_keys(value[0],depth+1) if value else None}
    return type(value).__name__

def _collect_json(page, seen, debug):
    def handle(resp):
        try:
            if resp.request.resource_type not in ("xhr", "fetch"):
                return
            url = urlsplit(resp.url)
            if url.scheme != "https" or not (url.hostname or "").endswith((
                "startup-plus.kr", "jointips.or.kr")):
                return
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return
            data = resp.json()
            scrubbed_path = urlunsplit(("", "", url.path, "", ""))
            # Avoid recording tokens, cookie headers or query parameters.
            paging=((data.get("data") or {}).get("pagination") or {}) if isinstance(data,dict) else {}
            debug.append({"path": scrubbed_path[:170], "status": resp.status,
                          "keys": list(data)[:12] if isinstance(data, dict) else ["array"],
                          "bytes": len(resp.body()), "shape": _schema_keys(data),
                          "method":resp.request.method, "requestUrl":resp.url,
                          "requestBody":resp.request.post_data,
                          "totalElements":paging.get("totalElements"),
                          "totalPages":paging.get("totalPages")})
            for ob in objects(data):
                for parser in (project_record, ir_record):
                    row = parser(ob)
                    if row:
                        seen[row["id"]] = row
        except Exception:
            return
    page.on("response", handle)

def _increment_page(data, number):
    """Set public-list paging argument without dropping other search filters."""
    if not isinstance(data,dict):
        return False
    changed=False
    for key,val in data.items():
        if isinstance(val,dict):
            changed = _increment_page(val,number) or changed
        elif key.casefold() in ("page","currentpage","pagenumber","pageno","pagenum","pageindex") and (
                isinstance(val,int) or str(val).isdigit()):
            original=int(val)
            data[key]=(number-1 if original==0 else number)
            changed=True
    return changed

def _public_api_pages(page,records,debug):
    """Replay only the site's own unauthenticated list request with next-page args."""
    import copy
    requests_seen=[x for x in debug if x.get("path")=="/api/project/list"
                   and x.get("status")==200]
    if not requests_seen:
        return 0, None
    base=requests_seen[0]
    total=base.get("totalElements")
    max_pages=min(70,max(1,int(base.get("totalPages") or 1)))
    request_url=base.get("requestUrl","")
    if not urlsplit(request_url).path.endswith("/api/project/list"):
        return 0,total
    method=base.get("method","GET").upper()
    raw=base.get("requestBody") or ""
    parsed=None
    is_json=False
    if raw:
        try:
            parsed=json.loads(raw)
            is_json=isinstance(parsed,dict)
        except (ValueError,TypeError):
            parsed=dict(parse_qsl(raw,keep_blank_values=True))
    scanned=0
    for number in range(2,max_pages+1):
        if total is not None and len(records)>=int(total):
            break
        try:
            if method=="POST":
                payload=copy.deepcopy(parsed) if isinstance(parsed,dict) else {}
                if not _increment_page(payload,number):
                    payload["page"]=number
                if is_json:
                    reply=page.request.post(request_url,data=payload,timeout=17000)
                else:
                    reply=page.request.post(request_url,form=payload,timeout=17000)
            else:
                parts=urlsplit(request_url)
                params=dict(parse_qsl(parts.query,keep_blank_values=True))
                if not _increment_page(params,number):
                    params["page"]=number
                next_url=parts._replace(query=urlencode(params)).geturl()
                reply=page.request.get(next_url,timeout=17000)
            if not reply.ok:
                break
            value=reply.json()
            if not isinstance(value,dict) or not isinstance(value.get("data"),dict):
                break
            data=value["data"]
            rows=data.get("contents")
            if not isinstance(rows,list) or not rows:
                break
            before=len(records)
            for obj in objects(rows):
                row=project_record(obj)
                if row:records[row["id"]]=row
            scanned+=1
            if len(records)==before:
                break
            if data.get("pagination",{}).get("last") is True:
                break
        except Exception:
            break
    return scanned,total

def _rendered_project_links(page, seen):
    hrefs = page.locator("a[href*='/project/PRJ']").evaluate_all(
        "(els) => els.map(x=>({href:x.href,title:(x.innerText||x.textContent||'').trim()}))")
    for link in hrefs[:300]:
        match = re.search(r"/project/(PRJ\d{5,9})(?:\b|/|\?)", link["href"], re.I)
        title = clean(link.get("title"), 180)
        if match and len(title) > 6:
            obj = {"projectCode":match.group(1), "projectName":title}
            row = project_record(obj)
            if row:
                seen.setdefault(row["id"], row)

def _dom_ir_records(page, seen):
    """Fallback for visible per-day operator labels when a public API schema changes."""
    text = page.locator("body").inner_text(timeout=9000)
    year_match = re.search(r"(20\d\d)년\s*(\d{1,2})월", text)
    year = int(year_match[1]) if year_match else dt.datetime.now(KST).year
    headers = list(DAY_DATE.finditer(text))
    today = dt.datetime.now(KST).date()
    added = 0
    for i, header in enumerate(headers[:65]):
        mo, day = int(header[1]), int(header[2])
        try:
            date = dt.date(year, mo, day)
        except ValueError:
            continue
        if date < today or date > today + dt.timedelta(days=110):
            continue
        end = headers[i+1].start() if i+1 < len(headers) else min(len(text),header.end()+4200)
        segment = text[header.end():end]
        if len(segment) > 6500 or not re.search(r"운영사|접수중|접수마감",segment):
            continue
        candidates = re.findall(
            r"(?:^|\n|[•·])\s*([가-힣A-Za-z0-9&().\- ]{2,48}?)\s+(접수중|신청가능|접수마감|마감)\b",
            segment, re.M)
        if not candidates:
            # Some calendar cells concatenate labels without newlines.
            candidates = re.findall(
                r"[•·]\s*([가-힣A-Za-z0-9&().\- ]{2,48}?)\s*(접수중|접수마감)",
                segment)
        for j,(operator,status) in enumerate(candidates[:40]):
            operator = clean(operator,48)
            if not operator or re.search(r"전체선택|투자분야|IR 회차",operator):
                continue
            program = "visible-%s-%s-%s" % (date.isoformat(),i,j)
            row = ir_record({"operatorName":operator,"irDate":date.isoformat(),
                             "programId":program,"applicationStatus":status})
            if row and row["id"] not in seen:
                row["sourceKind"]="공식 공개 달력 표기·상세 자격 및 잔여정원 확인 필요"
                seen[row["id"]]=row
                added+=1
    return added

def scan_ir_public_api():
    """Retrieve actual official operator slots, not one generic IR program."""
    import requests
    name="도전의 IR 운영사별 프로그램"
    rounds_url="https://irchallenge.jointips.or.kr/api/cms/public/challenge-ir/rounds"
    slots_url="https://irchallenge.jointips.or.kr/api/cms/public/challenge-ir/slots"
    state={"name":name,"url":IR_URL,"status":"error","discovered":0}
    try:
        session=requests.Session()
        session.headers.update({"User-Agent":"Mozilla/5.0 WorkLinks/1.0 public-ir-discovery",
                                "Accept":"application/json"})
        r=session.get(rounds_url,timeout=18);r.raise_for_status()
        body=r.json()
        if body.get("code")!=200 or not isinstance(body.get("data"),list):
            raise ValueError("IR rounds schema changed")
        today=dt.datetime.now(KST).date()
        rounds=[x for x in body["data"] if x.get("status")=="OPEN"
                and (date_value(x.get("applyTo")) or "0000")>=today.isoformat()]
        results={}; inspected=0
        for current in rounds[:4]:
            r=session.get(slots_url,params={"roundId":current["id"]},timeout=20)
            r.raise_for_status()
            payload=r.json()
            if payload.get("code")!=200 or not isinstance(payload.get("data"),list):
                raise ValueError("IR slots schema changed")
            inspected+=len(payload["data"])
            for slot in payload["data"]:
                if not isinstance(slot,dict):continue
                item=ir_record(slot)
                if item:
                    results[item["id"]]=item
        state.update({"status":"ok" if results else "partial",
                      "discovered":len(results),"slotsInspected":inspected,
                      "roundsInspected":len(rounds),
                      "uniqueOperators":len({x["operator"] for x in results.values()}),
                      "note":"운영사별 고유 slotId·IR일·공식 신청마감일·접수상한 확인. 공개 API 접근."})
        return list(results.values()),state
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        state["error"]=clean(exc,160)
        return [],state

def scan_browser_sources():
    """Independent startup-plus browser scan plus direct official IR API scan."""
    ir_rows,ir_state=scan_ir_public_api()
    all_rows,states=list(ir_rows),[ir_state]
    name,url="서울 스타트업플러스 지원사업",PROJECT_URL
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        states.append({"name":name,"url":url,"status":"error","discovered":0,
                       "error":"Playwright dependency missing"})
        return all_rows,states
    try:
        with sync_playwright() as tool:
            browser=tool.chromium.launch(headless=True,args=["--no-sandbox"])
            try:
                records,debug={},[]
                page=browser.new_page(locale="ko-KR",timezone_id="Asia/Seoul")
                _collect_json(page,records,debug)
                page.goto(url,wait_until="domcontentloaded",timeout=24000)
                page.wait_for_timeout(4200)
                for _ in range(4):
                    page.evaluate("window.scrollTo(0,document.body.scrollHeight)")
                    page.wait_for_timeout(650)
                _rendered_project_links(page,records)
                api_pages,expected_total=_public_api_pages(page,records,debug)
                pages_scanned=1+api_pages
                consecutive_empty=0
                # Site-URL pagination fallback if public list API did not advance.
                for page_number in range(2,13) if api_pages==0 else ():
                    if consecutive_empty>=2 or len(records)>=140:
                        break
                    before=len(records)
                    try:
                        page.goto(url+"?page="+str(page_number),
                                  wait_until="domcontentloaded",timeout=17000)
                        page.wait_for_timeout(1350)
                        _rendered_project_links(page,records)
                        pages_scanned+=1
                    except Exception:
                        break
                    if len(records)==before:
                        consecutive_empty+=1
                    else:
                        consecutive_empty=0
                page.close()
                rows=list(records.values())
                all_rows.extend(rows)
                states.append({"name":name,"url":url,
                   "status":"ok" if rows and (expected_total is None or len(rows)>=int(expected_total)) else "partial",
                   "discovered":len(rows),"availableInSource":expected_total,
                   "apiResponses":len(debug), "pagesScanned":pages_scanned,
                   "apiPaths":list(dict.fromkeys(x["path"] for x in debug))[:10],
                   "note":"공개 공고별 PRJ ID 확인" if rows else "공개 API 개별공고 미추출"})
            finally:
                browser.close()
    except Exception as exc:
        states.append({"name":name,"url":url,"status":"error",
                       "discovered":0,"error":clean(exc,160)})
    return all_rows,states
