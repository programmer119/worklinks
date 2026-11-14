"""WorkLinks browser regression: logged-out, manual logout, revoked session."""
import json
import time
from playwright.sync_api import sync_playwright

URL = "https://worklinks.suaveforge.com/startup-support/?view=jobs"
REVISION = "20261114-auth-watch-v3"
CORS = {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "authorization, content-type, accept",
}

def install_fake_auth(page, revoked):
    def route_auth(route):
        req = route.request
        if req.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
            return
        path = req.url.split("?", 1)[0]
        if path.endswith("/v1/config/p47"):
            status, body = 200, {"project": {"slug": "p47"}, "environment": "production"}
        elif path.endswith("/v1/me"):
            status, body = (401, {"error": "invalid_token"}) if revoked["value"] else (
                200, {"user": {"id": "qa-user", "email": "qa@example.com"}, "membership": {"status": "active"}}
            )
        elif path.endswith("/v1/auth/p47/refresh"):
            status, body = (401, {"error": "expired_refresh"}) if revoked["value"] else (
                200, {"accessToken": "qa-token", "refreshToken": "qa-refresh"}
            )
        else:
            status, body = 200, {"ok": True}
        route.fulfill(status=status, body=json.dumps(body), content_type="application/json", headers=CORS)

    def route_state(route):
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
        else:
            route.fulfill(status=200, body=json.dumps({"ok": True, "records": []}),
                          content_type="application/json", headers=CORS)

    page.route("https://api-authhub.suaveforge.com/**", route_auth)
    page.route("**/api/g2b/worklinks-state*", route_state)

def open_session(browser, revoked):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("""
        if (location.hostname === 'worklinks.suaveforge.com') {
          localStorage.setItem(
            'authhub:p47:production:session',
            JSON.stringify({accessToken: 'qa-token', refreshToken: 'qa-refresh'})
          );
        }
    """)
    page = context.new_page()
    page.clock.install()
    install_fake_auth(page, revoked)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.locator(".worklinks-auth-dropdown").wait_for(state="visible", timeout=30000)
    page.locator("#worklinks-auth-gate").wait_for(state="hidden", timeout=30000)
    assert REVISION in page.content(), "Unexpected live account module revision"
    return context, page

def assert_locked(page, expected):
    page.locator("#worklinks-auth-gate").wait_for(state="visible", timeout=20000)
    page.get_by_text(expected, exact=True).wait_for(state="visible", timeout=20000)
    assert page.locator("body > main").evaluate("(e)=>e.inert")
    assert page.locator("body > main").evaluate("(e)=>getComputedStyle(e).visibility") == "hidden"
    assert page.locator("#worklinks-auth-gate-login").is_visible()
    assert page.locator(".worklinks-auth-dropdown").is_hidden()
    print(expected + " + hidden previous jobs = PASS", flush=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    visitor = browser.new_page(viewport={"width": 1440, "height": 900})
    visitor.goto(URL, wait_until="domcontentloaded", timeout=60000)
    visitor.locator("#worklinks-auth-gate-login").wait_for(state="visible", timeout=25000)
    assert REVISION in visitor.content()
    assert visitor.locator("body > main").evaluate("(e)=>e.inert")
    print("VISITOR_AUTH_GATE=PASS", flush=True)
    visitor.close()

    context, page = open_session(browser, {"value": False})
    page.locator(".worklinks-auth-summary").click()
    page.get_by_role("button", name="로그아웃", exact=True).click()
    assert_locked(page, "로그아웃되었습니다.")
    print("MANUAL_LOGOUT_GATE=PASS", flush=True)
    context.close()

    revoked = {"value": False}
    context, page = open_session(browser, revoked)
    revoked["value"] = True
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    assert_locked(page, "로그인이 만료되었습니다.")
    print("REVOKED_SESSION_GATE=PASS", flush=True)
    context.close()

    # No tab switch and no user click: the 45s session heartbeat must still lock it.
    revoked = {"value": False}
    context, page = open_session(browser, revoked)
    revoked["value"] = True
    page.clock.fast_forward(46000)
    assert_locked(page, "로그인이 만료되었습니다.")
    print("ACTIVE_TAB_EXPIRY_HEARTBEAT=PASS", flush=True)
    context.close()
    browser.close()
