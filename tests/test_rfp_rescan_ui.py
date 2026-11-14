#!/usr/bin/env python3
"""Live progress UI: meaningful completed/total counts, 10-second clock and fresh updates."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
url='http://127.0.0.1:18766/startup-support/index.html?view=jobs'
fake={
    'ok':True,'schemaVersion':1,'scope':'unexpired_saved_sw_bid_notices',
    'asOf':'2026-11-14T12:00:00+09:00',
    'remainingPercent':83.3,'rescanPercent':33.3,
    'counts':{'total':6,'completed':1,'remaining':5,'rescanRequired':2,'legacy':2,
              'unscanned':1,'failed':1,'incomplete':1,'unknownDeadline':2},
    'stages':{'classification':{'total':6,'done':3,'remaining':3},
              'roles':{'total':6,'done':2,'remaining':4},
              'facts':{'total':6,'done':2,'remaining':4},
              'hwpx':{'total':2,'done':1,'remaining':1}},
    'worker':{'available':True,'upgradeActive':True,
              'tasks':{'rfpUpgrade':{'status':'started',
                                    'attemptEpoch':1794630000,'successEpoch':0}}}
}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1310,'height':820})
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    calls=[]
    def respond(route):
        calls.append(route.request.url)
        route.fulfill(status=200,content_type='application/json',
                      body=json.dumps(fake,ensure_ascii=False))
    # Match cache-busting query parameters as well as the bare URL.
    page.route('**/api/g2b/rfp-rescan-progress*',respond)
    page.goto(url,wait_until='domcontentloaded',timeout=60000)
    page.wait_for_function(
      "() => document.getElementById('rfpRescanCount')?.textContent.includes('완료 1 / 6건')",
      timeout=25000)
    button=page.locator('#rfpRescanLaunch')
    assert '16.67%' in page.locator('#rfpRescanLabel').inner_text()
    assert button.is_visible()
    assert page.locator('#rfpRescanCycle').is_visible()
    assert page.evaluate(
      "() => document.querySelector('#rfpRescanLaunch').closest('.head-actions') !== null")
    # Countdown is not a fake completion animation; it shows seconds until next HTTP read.
    page.evaluate("() => { rfpRescanNextReadAt=Date.now()+6000; paintRfpCountdown(); }")
    seconds=int(page.locator('#rfpRescanSeconds').inner_text())
    assert 5<=seconds<=6,seconds
    page.wait_for_function(
      "() => {const t=document.getElementById('rfpRescanSeconds')?.textContent; return t !== '…' && Number(t) < 6;}",
      timeout=4500)
    updated=int(page.locator('#rfpRescanSeconds').inner_text())
    assert updated<seconds,(seconds,updated)

    button.click()
    modal=page.locator('#rfpRescanModal')
    assert modal.is_visible()
    page.wait_for_function(
      "() => document.querySelector('#rfpRescanContent')?.textContent.includes('서버 재판독')",
      timeout=12000)
    body=page.locator('#rfpRescanContent').inner_text()
    for term in ('관리 대상','6','최신 판독 완료','1','재판독 필요','구버전',
                 '최초 미판독','역할·인원','16.67%','서버 재판독','실행 중'):
        assert term in body,(term,body)

    # A new server result must actually update both completed numerator and percentage.
    fake['counts'].update(completed=2,remaining=4,unscanned=0)
    fake['asOf']='2026-11-14T12:01:00+09:00'
    page.evaluate("() => refreshRfpRescanProgress(true)")
    page.wait_for_function(
      "() => document.getElementById('rfpRescanCount')?.textContent.includes('완료 2 / 6건')",
      timeout=12000)
    assert '33.33%' in page.locator('#rfpRescanLabel').inner_text()
    assert '완료 +1건' in page.locator('#rfpRescanContent').inner_text()
    assert len(calls)>=2
    assert all('/rfp-rescan-progress?_' in value for value in calls),calls
    page.locator('#rfpRescanClose').click()
    assert modal.get_attribute('aria-hidden')=='true'
    page.evaluate("() => {rfpRescanProgress=null;rfpRescanProgressError='조회 오류';paintRfpRescanProgress();}")
    assert page.locator('#rfpRescanCount').inner_text()=='판독 현황 확인 불가'
    assert not errors,errors
    browser.close()
print('WORKLINKS_RFP_RESCAN_LIVE_UI_REGRESSION=PASS')
