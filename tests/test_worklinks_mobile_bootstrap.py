#!/usr/bin/env python3
"""Regression: the support homepage must not start the G2B crawler UI,
and mobile Jobs loads saved public tenders in bounded, user-expandable pages.
Run after playwright/chromium installation.
"""
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
calls = []
external_calls = []
errors = []


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def record(index):
    return {
        "kind": "servc",
        "bidNo": "R26BK%08d" % (17000000 + index),
        "order": "000",
        "title": "AI 시스템 구축 및 소프트웨어 개발 QA %03d" % index,
        "org": "QA 테스트 기관",
        "posted": "2026-10-17",
        "closes": "2026-12-30 17:00",
        "budget": "10000000",
        "url": "https://www.g2b.go.kr/",
    }


def api_route(route):
    url = urlparse(route.request.url)
    path = url.path
    if any(path.endswith("/"+operation) for operation in (
        "company", "eligibility", "bid-evidence", "direct-production",
        "contract-capability", "awards", "contract-evidence", "contract-notice")):
        external_calls.append(path)
    if path.endswith("/worklinks-auth-config"):
        payload = {"ok": True, "enabled": False}
    elif path.endswith("/saved"):
        args = parse_qs(url.query)
        offset = int(args.get("offset", ["0"])[0])
        limit = int(args.get("limit", ["500"])[0])
        calls.append((offset, limit))
        payload = {
            "ok": True, "totalCount": 480, "eligibilityLinked": 0,
            "items": [record(i) for i in range(offset, min(offset + limit, 480))]
        }
    elif path.endswith("/status"):
        payload = {"ok": True, "configured": True}
    elif path.endswith("/crawl-status"):
        payload = {"ok": True, "installed": True, "state": "completed",
                   "storedTotal": 480, "candidateTotal": 480}
    elif path.endswith("/award-cache"):
        payload = {"ok": True, "installed": False, "records": [], "totalCount": 0}
    elif path.endswith("/company"):
        payload = {"ok": True, "found": False}
    elif path.endswith("/contract-capability"):
        payload = {"ok": True, "authorized": False}
    elif path.endswith("/eligibility"):
        payload = {"ok": True, "complete": False, "requirements": []}
    elif path.endswith("/bid-evidence"):
        payload = {"ok": True, "complete": False, "region": {},
                   "attachments": {}, "noticeDocuments": {}}
    else:
        payload = {"ok": True, "totalCount": 0, "items": []}
    route.fulfill(status=200, content_type="application/json",
                  body=json.dumps(payload))


def main():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/startup-support/" % server.server_port
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, **(
                {"executable_path":os.environ["WORKLINKS_CHROMIUM_PATH"]}
                if os.environ.get("WORKLINKS_CHROMIUM_PATH") else {}))
            page = browser.new_page(
                viewport={"width": 390, "height": 844},
                device_scale_factor=1, is_mobile=True, has_touch=True,
            )
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.route("**/api/g2b/**", api_route)
            page.goto(base, wait_until="domcontentloaded", timeout=30000)
            page.locator("#supportView.on").wait_for(timeout=15000)
            page.wait_for_function(
                "() => document.querySelector('#tb')?.children.length > 0",
                timeout=15000
            )
            page.wait_for_timeout(500)
            assert not calls, "Startup homepage eagerly requested G2B: %s" % calls
            assert page.evaluate("!jobsBootstrapStarted"), "Jobs booted on support page"
            assert page.locator("#pageRefreshButton").count() == 1
            assert "화면 로드" in page.locator("#pageLoadStamp").text_content()
            # The deployment stamp tracks the current revision; it must not be
            # pinned to a previous release and fail after a valid update.
            revision = page.evaluate("WORKLINKS_PAGE_REVISION")
            assert isinstance(revision, str) and revision.startswith("20") and len(revision) >= 12
            assert page.locator("#pageLoadStamp").text_content().endswith(" · v" + revision)

            # Ordinary browser reload must create a fresh document and return
            # to the top rather than silently restoring the previous scroll.
            original_origin = page.evaluate("performance.timeOrigin")
            page.evaluate("window.scrollTo(0, 1100)")
            page.wait_for_timeout(200)
            assert page.evaluate("window.scrollY") > 300, "Page was not scrollable"
            page.reload(wait_until="load", timeout=30000)
            page.wait_for_timeout(350)
            assert page.evaluate("performance.timeOrigin") > original_origin
            assert page.evaluate("performance.getEntriesByType('navigation')[0].type") == "reload"
            assert page.evaluate("history.scrollRestoration") == "manual"
            assert page.evaluate("window.scrollY") <= 2, "Normal reload retained scroll"
            assert "화면 로드" in page.locator("#pageLoadStamp").text_content()
            assert not calls, "Reload eagerly fetched G2B while on support view"

            # The visible refresh control must navigate to a unique URL and
            # also return to the top without modifying hidden/applied records.
            page.evaluate("window.scrollTo(0, 900)")
            page.wait_for_timeout(160)
            assert page.evaluate("window.scrollY") > 300
            origin_before_button = page.evaluate("performance.timeOrigin")
            with page.expect_navigation(wait_until="load"):
                page.evaluate("document.querySelector('#pageRefreshButton').click()")
            page.wait_for_timeout(350)
            assert "_refresh=" in page.url
            assert page.evaluate("performance.timeOrigin") > origin_before_button
            assert page.evaluate("history.scrollRestoration") == "manual"
            assert page.evaluate("window.scrollY") <= 2, "In-page refresh retained scroll"
            assert not calls, "Refresh control eagerly fetched G2B on support"

            page.locator(".workspace-tab[data-view='jobs']").click()
            page.locator("#jobsView.on").wait_for(timeout=15000)
            page.wait_for_function(
                "() => g2bServerAvailable && g2bLoadedOffset === 160",
                timeout=20000
            )
            assert calls == [(0, 160)], "Mobile first page must be bounded: %s" % calls
            assert not external_calls, "Jobs refresh queried upstream-dependent endpoints: %s" % external_calls
            # API state is updated before its debounced DOM paint. Wait for
            # the actual visible control, not just the background fetch flag.
            page.wait_for_function(
                "() => !jobRenderDirty && !!document.querySelector('#partnerSummary')?.textContent?.includes('현재 로드')",
                timeout=20000
            )
            page.locator("#g2bMore").wait_for(state="visible", timeout=15000)
            assert page.evaluate("g2bSavedTotal") == 480
            assert "현재 로드" in page.locator("#partnerSummary").text_content()
            # Partner bid screening is private by default. For the rest of
            # this browser-only regression, simulate a verified membership
            # event; never relax the production authentication guard.
            assert page.locator("#jobDecisionSummary").is_hidden()
            assert not page.evaluate("worklinksPartnerAccess()")
            page.evaluate("""() => {
                window.worklinksMemberAuthenticated=true;
                document.documentElement.dataset.worklinksPartnerAccess='granted';
                window.dispatchEvent(new Event('worklinks:partner-access'));
            }""")
            page.wait_for_function(
                "() => worklinksPartnerAccess() && document.querySelector('#jobDecisionSummary')?.textContent?.includes('적격 후보')",
                timeout=15000
            )
            assert page.evaluate("jobRenderLimit") == 24
            assert page.locator("#jobCards .job-mini").count() <= 24

            # Real-browser regression: bid amounts share the same relative
            # vertical baseline regardless of a one-line vs wrapped title.
            amount_positions = page.evaluate("""() => {
                const cards = [...document.querySelectorAll('#jobCards .job-mini')].slice(0,2);
                if (cards.length !== 2) return null;
                const titles = cards.map(c=>c.querySelector('.job-card-title'));
                const original = titles.map(t=>t.textContent);
                titles[0].textContent = '계룡시 유지관리';
                titles[1].textContent = '수원시 상수도사업소 홈페이지 및 요금관리시스템 통합유지관리';
                const rows = cards.map(c => {
                    const title = c.querySelector('.job-card-title');
                    const amount = c.querySelector('.job-headline-side .job-amount');
                    if (!amount) return null;
                    return {
                        amountY: amount.getBoundingClientRect().top - c.getBoundingClientRect().top,
                        titleHeight: title.getBoundingClientRect().height,
                        inSide: !!amount.closest('.job-headline-side')
                    };
                });
                titles.forEach((t,i)=>t.textContent=original[i]);
                return rows;
            }""")
            assert amount_positions and all(v and v["inSide"] for v in amount_positions), amount_positions
            assert abs(amount_positions[0]["amountY"] - amount_positions[1]["amountY"]) <= 1, amount_positions
            assert amount_positions[1]["titleHeight"] > amount_positions[0]["titleHeight"], amount_positions

            # Source-checked bids must be rendered in the SAME standard cards,
            # never a second, overfull verification-only card grid.
            page.wait_for_function(
                "() => !!changcomActionableData && Array.isArray(changcomActionableData.bids) && !jobRenderDirty",
                timeout=20000
            )
            census = page.evaluate("""() => ({
                indexed:changcomActionableData.counts.indexedSWTotal,
                aligned:changcomActionableEntries('aligned').length,
                review:changcomActionableEntries('review').length,
                mismatch:changcomActionableEntries('mismatch').length,
                unknown:changcomActionableEntries('unknown').length,
                all:changcomActionableEntries('all').length,
                verified:changcomActionableEntries('verified').length,
                activeMode:changcomActionableMode,
                parallelPanel:!!document.querySelector('#changcomActionableList'),
                firstIds:[...document.querySelectorAll('#jobCards .job-mini')].slice(0,4)
                    .map(e=>e.dataset.jobCard),
                noisyCards:[...document.querySelectorAll('#jobCards .job-mini')]
                    .filter(e=>/유리도 평가 제외|경쟁자료 미확인|경쟁자료 부족|창컴 3단계/.test(e.innerText)).length,
                firstPassCards:document.querySelectorAll('#jobCards .job-basic-signal').length,
                firstPassTags:[...document.querySelectorAll('#jobCards .job-basic-signal')]
                    .map(e=>e.textContent.trim()),
                firstPassCounts:{
                    checked:Number(document.querySelector('[data-verdict-count="adv-3"]')?.textContent||0),
                    aligned:Number(document.querySelector('[data-verdict-count="adv-2"]')?.textContent||0)
                }
            })""")
            assert census["indexed"] > 100, census
            assert census["aligned"] > 0 and census["all"] >= census["aligned"], census
            assert census["all"] == census["aligned"] + census["review"] + census["unknown"] + census["mismatch"], census
            assert not census["parallelPanel"], census
            # Snapshot evidence can legitimately have zero documented prechecks.
            # Never manufacture a positive qualification count merely to satisfy QA.
            assert census["verified"] >= 0, census
            assert census["noisyCards"] == 0, census
            assert census["firstPassCards"] >= 2, census
            assert census["firstPassCounts"]["checked"] >= 0, census
            assert census["firstPassCounts"]["aligned"] > 0, census
            if census["verified"] >= 2:
                assert census["firstPassTags"][:2] == ["기초요건 대조", "기초요건 대조"], census
            else:
                assert all(tag == "등록업종 일치" for tag in census["firstPassTags"][:2]), census
            assert "등록업종 일치" in census["firstPassTags"], census
            checked_ids = page.evaluate("""() =>
                changcomActionableEntries('verified').map(x=>String(x.bidNo)+':'+String(x.order||'000').padStart(3,'0'))
            """)
            displayed_ids = page.evaluate("""() =>
                [...document.querySelectorAll('#jobCards .job-mini')].slice(0,2)
                  .map(e=>e.dataset.jobCard)
            """)
            assert all(any(bid.split(':')[0] in got for got in displayed_ids) for bid in checked_ids[:2]), (checked_ids, displayed_ids)
            print("WORKLINKS_UNIFIED_SHORTLIST_MOBILE_QA=PASS",
                  json.dumps(census,ensure_ascii=False))

            # Verify a REAL pointer click can reach each control on mobile.
            # A static scrollIntoView can leave the button under preceding
            # filters after asynchronous layout shifts. Never force clicks.
            def click_verified(selector):
                page.wait_for_function("""selector => {
                    const target=document.querySelector(selector);
                    if(!target)return false;
                    const r=target.getBoundingClientRect();
                    const desired=window.scrollY+r.top-window.innerHeight*0.64;
                    window.scrollTo({top:Math.max(0,desired),behavior:'instant'});
                    const b=target.getBoundingClientRect();
                    const x=b.left+b.width/2,y=b.top+b.height/2;
                    if(x<0||x>=innerWidth||y<0||y>=innerHeight)return false;
                    const hit=document.elementFromPoint(x,y);
                    return hit===target||target.contains(hit);
                }""", arg=selector, timeout=12000)
                # Playwright Locator.click() may perform a SECOND implicit
                # scroll after this hit-test, moving the button under a nearby
                # filter/progress block. Use an actual mouse pointer event at
                # the already verified visible coordinates instead.
                point=page.evaluate("""selector => {
                    const target=document.querySelector(selector);
                    if(!target)return null;
                    const b=target.getBoundingClientRect();
                    const x=b.left+b.width/2,y=b.top+b.height/2;
                    const hit=document.elementFromPoint(x,y);
                    return hit===target||target.contains(hit)?{x,y}:null;
                }""",selector)
                assert point is not None, "mobile action obstructed: "+selector
                page.mouse.click(point["x"],point["y"])
            assert calls == [(0,160)], ("prechecked card grid must not trigger extra G2B requests", calls)
            assert not external_calls, ("first paint must use stored evidence only", external_calls)

            # Important card text must never be ellipsized, even for unusually
            # long Korean notice names and verification text. Tiny history
            # indicators are in a separate wrap-safe row below the heading.
            card_readability = page.evaluate("""() => {
                const card=document.querySelector('#jobCards .job-mini');
                if(!card)return {error:'no displayed job'};
                const heading=card.querySelector('h3'),button=heading.querySelector('.job-card-title');
                const original=button.textContent;
                button.textContent='2027년 나라장터 공공기관 AI 데이터 관리시스템 구축 및 클라우드 정보보안 전환 운영 유지관리와 개발 용역 사업 세부 참여 조건 확인 및 과업지시서 전수검토';
                const style=getComputedStyle(button),headline=getComputedStyle(heading);
                const title={clamp:style.webkitLineClamp,display:style.display,
                    visible:button.getBoundingClientRect().height>2*parseFloat(style.lineHeight),
                    overflow:button.scrollHeight>button.clientHeight+2,
                    wrapperClipped:heading.scrollHeight>heading.clientHeight+2,
                    lineCount:Math.round(button.getBoundingClientRect().height/
                        parseFloat(style.lineHeight))};
                button.textContent=original;
                const why=card.querySelector('.job-verdict-why');
                const whyStyle=why?getComputedStyle(why):null;
                const checks=card.querySelectorAll('.job-verdict-checks');
                return {title,
                    containsHighlights:!!card.querySelector('.job-highlights'),
                    headlineChildren:card.querySelector('.job-headline')?.querySelectorAll('h3').length,
                    why:why?{clamp:whyStyle.webkitLineClamp,overflow:why.scrollHeight>why.clientHeight+2}:null,
                    namedChecks:checks.length,
                    checkText:[...checks].map(el=>el.textContent.slice(0,180))};
            }""")
            assert not card_readability.get("error"), card_readability
            assert card_readability["headlineChildren"] == 1, card_readability
            assert card_readability["title"]["clamp"] == "none", card_readability
            assert card_readability["title"]["visible"] and card_readability["title"]["lineCount"] > 2, card_readability
            assert not card_readability["title"]["overflow"] and not card_readability["title"]["wrapperClipped"], card_readability
            if card_readability["why"]:
                assert card_readability["why"]["clamp"] == "none", card_readability
                assert not card_readability["why"]["overflow"], card_readability
            print("WORKLINKS_CARD_READABILITY=PASS",
                  json.dumps(card_readability, ensure_ascii=False))

            # Mobile deliberately displays just 24 cards at once; advancing
            # the server's 160-row cache can take several smaller More clicks.
            for _ in range(16):
                if len(calls) > 1:
                    break
                button = page.locator("#g2bMore")
                assert button.is_visible(), "More button must expose remaining rows"
                click_verified("#g2bMore")
                page.wait_for_timeout(260)
            page.wait_for_function(
                "() => g2bLoadedOffset >= 320", timeout=15000
            )
            assert calls[:2] == [(0, 160), (160, 160)], calls
            click_verified(".workspace-tab[data-view='support']")
            page.locator("#supportView.on").wait_for()
            count = len(calls)
            click_verified(".workspace-tab[data-view='jobs']")
            page.wait_for_timeout(350)
            assert len(calls) == count, "Tab reentry restarted the full sync"

            # Regression: tab navigation must never synchronously rerun the
            # expensive entire-bid matching/DOM card renderer.
            page.wait_for_timeout(250)
            quick_tabs = page.evaluate("""() => {
                const oldRender = window.renderJobs;
                let rerenders = 0;
                window.renderJobs = function(...args) {
                    rerenders++;
                    return oldRender.apply(this, args);
                };
                const times = [];
                for(let n=0;n<6;n++){
                    const started=performance.now();
                    document.querySelector('.workspace-tab[data-view="support"]').click();
                    document.querySelector('.workspace-tab[data-view="jobs"]').click();
                    times.push(performance.now()-started);
                }
                return {
                    times, rerenders, jobsVisible:document.getElementById('jobsView').classList.contains('on'),
                    cards:document.querySelectorAll('#jobCards [data-job-card]').length
                };
            }""")
            assert quick_tabs["jobsVisible"] and quick_tabs["cards"] > 0, quick_tabs
            assert quick_tabs["rerenders"] == 0, ("Every tab switch must not rerender all bids", quick_tabs)
            assert max(quick_tabs["times"]) < 160, ("Tab interaction blocked the UI", quick_tabs)

            # Measure user-observable SALES paint, not only click-handler time.
            # Throttle CPU like a lower-end mobile device and exercise all three
            # workspace views while background tender verification continues.
            session = page.context.new_cdp_session(page)
            session.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            sales_latency = page.evaluate("""async () => {
                const labels=['sales','support','jobs','sales','support','sales'];
                const times=[], longTasks=[];
                const observer=new PerformanceObserver(list=>{
                    for(const entry of list.getEntries()) longTasks.push(Math.round(entry.duration));
                });
                try { observer.observe({entryTypes:['longtask']}) } catch(e) {}
                for (const view of labels) {
                    const start=performance.now();
                    document.querySelector('.workspace-tab[data-view="'+view+'"]').click();
                    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                    times.push({view,ms:Math.round(performance.now()-start),
                        salesVisible:!!document.querySelector('#salesView.on'),
                        salesCards:document.querySelectorAll('#salesCards .card').length});
                }
                observer.disconnect();
                return {times,longTasks};
            }""")
            session.send("Emulation.setCPUThrottlingRate", {"rate": 1})
            assert all(t["salesVisible"] for t in sales_latency["times"] if t["view"] == "sales")
            assert all(t["salesCards"] == page.evaluate("salesAgencies.length") for t in sales_latency["times"] if t["view"] == "sales"), ("sales tab card count must reflect the live agency list", sales_latency)
            print("WORKLINKS_SALES_MOBILE_PAINT", json.dumps(sales_latency, ensure_ascii=False))
            click_verified(".workspace-tab[data-view='jobs']")
            page.locator("#jobsView.on").wait_for()
            profile = page.evaluate("""() => {
                const names = ['renderJobs','refreshVerdictFilters',
                    'participationVerdict','jobQualificationVerdict','comparePartnerJob',
                    'matchesVerdictFilter','partnerVerdictTypes','jobTimeInfo',
                    'pastCompetitionSummary','repeatYears','jobSoftwareScope',
                    'collapseSimilarNotices','renderPartners'];
                const meters = {};
                for(const name of names) {
                    const fn = window[name];
                    if(typeof fn !== 'function') continue;
                    const meter=meters[name]={calls:0,ms:0,maxMs:0};
                    window[name]=function(...args) {
                        const at=performance.now();
                        try{return fn.apply(this,args)}
                        finally {
                            const ms=performance.now()-at;
                            meter.calls++;meter.ms+=ms;
                            meter.maxMs=Math.max(meter.maxMs,ms);
                        }
                    };
                }
                window.renderJobs();
                return Object.entries(meters).map(([name,m])=>({name,calls:m.calls,
                    inclusiveMs:Math.round(m.ms),maxMs:Math.round(m.maxMs)}))
                    .sort((a,b)=>b.inclusiveMs-a.inclusiveMs);
            }""")
            print("WORKLINKS_JOBS_CPU_PROFILE", json.dumps(profile, ensure_ascii=False))
            assert not errors, "Browser JS errors: %s" % errors
            print("WORKLINKS_MOBILE_LAZY_QA=PASS",
                  json.dumps({"g2b_requests": calls, "total": 480,
                              "after_more": page.evaluate("g2bLoadedOffset"),
                              "js_errors": len(errors)}, ensure_ascii=False))
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
