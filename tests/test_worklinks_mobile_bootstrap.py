#!/usr/bin/env python3
"""Regression: the support homepage must not start the G2B crawler UI,
and mobile Jobs loads saved public tenders in bounded, user-expandable pages.
Run after playwright/chromium installation.
"""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
calls = []
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
            browser = p.chromium.launch(headless=True)
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

            page.locator(".workspace-tab[data-view='jobs']").click()
            page.locator("#jobsView.on").wait_for(timeout=15000)
            page.wait_for_function(
                "() => g2bServerAvailable && g2bLoadedOffset === 160",
                timeout=20000
            )
            assert calls == [(0, 160)], "Mobile first page must be bounded: %s" % calls
            assert page.locator("#g2bMore").is_visible()
            assert page.evaluate("g2bSavedTotal") == 480
            assert "현재 로드" in page.locator("#partnerSummary").text_content()
            assert "적격 후보" in page.locator("#jobDecisionSummary").text_content()

            for _ in range(6):
                if len(calls) > 1:
                    break
                button = page.locator("#g2bMore")
                assert button.is_visible(), "More button must expose remaining rows"
                button.click()
                page.wait_for_timeout(260)
            page.wait_for_function(
                "() => g2bLoadedOffset >= 320", timeout=15000
            )
            assert calls[:2] == [(0, 160), (160, 160)], calls
            page.locator(".workspace-tab[data-view='support']").click()
            page.locator("#supportView.on").wait_for()
            count = len(calls)
            page.locator(".workspace-tab[data-view='jobs']").click()
            page.wait_for_timeout(350)
            assert len(calls) == count, "Tab reentry restarted the full sync"
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
