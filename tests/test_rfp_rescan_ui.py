#!/usr/bin/env python3
"""Browser regression: the top account-neighbor progress reflects server counts."""
import json
import os
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
    'stages':{
      'classification':{'total':6,'done':3,'remaining':3},
      'roles':{'total':6,'done':2,'remaining':4},
      'facts':{'total':6,'done':2,'remaining':4},
      'hwpx':{'total':2,'done':1,'remaining':1}
    }
}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1310,'height':820})
    page_errors=[]
    page.on('pageerror',lambda err:page_errors.append(str(err)))
    calls=[]
    def respond(route):
        calls.append(route.request.url)
        route.fulfill(status=200,content_type='application/json',
                      body=json.dumps(fake,ensure_ascii=False))
    page.route('**/api/g2b/rfp-rescan-progress',respond)
    page.goto(url,wait_until='domcontentloaded',timeout=60000)
    page.wait_for_function(
      "() => document.getElementById('rfpRescanLabel')?.textContent.includes('33.3%')",
      timeout=25000)
    button=page.locator('#rfpRescanLaunch')
    account=page.locator('#worklinks-auth-header')
    # Even when the account script loads later, the intended grid areas must be adjacent.
    assert page.evaluate(
      "() => getComputedStyle(document.querySelector('.pagehead')).gridTemplateAreas.includes('rfpstatus account')")
    assert button.bounding_box()['x']<account.bounding_box()['x']
    button.click()
    modal=page.locator('#rfpRescanModal')
    assert modal.get_attribute('aria-hidden')=='false'
    assert modal.is_visible()
    text=page.locator('#rfpRescanContent').inner_text()
    for term in ['관리 대상','6','최신 판독 완료','판독 필요','5','구버전','2','최초 미판독','1',
                 '실패','검증 미완료','역할·인원','인력 요구사항','HWPX 해석','33.3%']:
        assert term in text,(term,text)
    assert len(calls)>=1
    page.locator('#rfpRescanClose').click()
    assert modal.get_attribute('aria-hidden')=='true'
    # Unknown data must never be shown as 0%/100%.
    page.evaluate("() => {rfpRescanProgress=null; rfpRescanProgressError='집계 오류'; paintRfpRescanProgress()}")
    assert page.locator('#rfpRescanLabel').inner_text()=='판독 현황 확인 필요'
    browser.close()
print('WORKLINKS_RFP_RESCAN_UI_BROWSER=PASS')
