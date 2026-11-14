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
    'lanes':{'available':True,'manifest':{'total':1000,'done':900},
             'download':{'total':1000,'done':850,'active':8,'failed':2},
             'scan':{'total':1000,'done':375,'active':4,'failed':0}},
    'activity':{'available':True,
        'workers':{'manifest':{'status':'retry','error':'provider quota',
                              'retryEpoch':1794672000,'updatedEpoch':1794630000,'stale':False},
                   'download':{'status':'running','error':'','retryEpoch':0,
                               'updatedEpoch':1794630000,'stale':False},
                   'scan':{'status':'running','error':'','retryEpoch':0,
                           'updatedEpoch':1794630000,'stale':False}},
        'items':[{'lane':'download','noticeKey':'R26BK00000001:000',
                  'fileName':'사업제안요청서.pdf','phase':'전송 중','status':'working',
                  'bytesDone':524288,'bytesTotal':2097152,
                  'filesDone':1,'filesTotal':3,'retryEpoch':0,
                  'error':'','updatedEpoch':1794630000},
                 {'lane':'scan','noticeKey':'R26BK00000002:000',
                  'fileName':'인력조건.hwp','phase':'텍스트 추출','status':'working',
                  'bytesDone':0,'bytesTotal':0,'filesDone':0,'filesTotal':2,
                  'retryEpoch':0,'error':'','updatedEpoch':1794630000}]},
    'worker':{'available':True,'upgradeActive':True,'continuousDrain':True,
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
    # Job controls are login-gated. This fixture mocks only the progress API;
    # expose its existing nodes for a focused layout test without changing
    # the production authentication behavior.
    page.evaluate("""() => {
      document.querySelectorAll('[inert]').forEach(el=>el.removeAttribute('inert'));
      let n=document.getElementById('rfpRescanLaunch');
      for(;n;n=n.parentElement){
        if(getComputedStyle(n).display==='none')n.style.display='block';
        if(getComputedStyle(n).visibility==='hidden')n.style.visibility='visible';
      }
    }""")
    button=page.locator('#rfpRescanLaunch')
    actual_label=page.locator('#rfpRescanLabel').text_content()
    assert '16.67%' in actual_label,(actual_label,errors,page.locator('#rfpRescanCount').inner_text())
    assert button.is_visible()
    assert page.locator('#rfpRescanCycle').is_visible()
    assert '조회' in page.locator('#rfpRescanCycle').inner_text()
    assert '초' in page.locator('#rfpRescanCycle').inner_text()
    assert page.evaluate("() => getComputedStyle(document.getElementById('rfpRescanCycle')).backgroundImage")=='none', 'a poll timer must not look like circular scan progress'
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

    # Auth overlay can re-apply inert asynchronously in this unsigned test.
    # Dispatch this focused UI event without bypassing production auth routes.
    page.evaluate("() => document.getElementById('rfpRescanLaunch').dispatchEvent(new MouseEvent('click',{bubbles:true}))")
    modal=page.locator('#rfpRescanModal')
    assert modal.get_attribute('aria-hidden')=='false' and page.evaluate("() => document.getElementById('rfpRescanModal').classList.contains('open')")
    page.wait_for_function(
      "() => document.querySelector('#rfpRescanContent')?.textContent.includes('실제 작업 진행 중')",
      timeout=12000)
    body=page.locator('#rfpRescanContent').text_content()
    for term in ('관리 대상','6','최신 판독 완료','1','재판독 필요','구버전',
                 '최초 미판독','역할·인원','16.67%','실제 작업 진행 중','다운로드 8건','판독 4건'):
        assert term in body,(term,body)
    assert '첨부목록 확보' in body and '900 / 1,000건' in body,body
    assert '원본 다운로드' in body and '850 / 1,000건' in body,body
    assert '사업제안요청서.pdf' in body and '0.50 MB / 2.00 MB' in body,body
    assert 'provider quota' in body and '인력조건.hwp' in body,body
    page.evaluate("""() => {
      window._rfpFileLiveRow=document.querySelector('[data-lane="download"] .rfp-live-item');
    }""")

    assert '문서 판독' in body and '375 / 1,000건' in body,body
    assert '진행률 =' not in body and '미판독·실패·구버전' not in body,body
    assert page.locator('.rfp-rescan-livebar.is-active').count()==1
    assert page.locator('[data-rfp-stage="download"].is-active').count()==1
    assert page.locator('[data-rfp-stage="scan"].is-active').count()==1
    assert page.locator('[data-rfp-stage="manifest"].is-active').count()==0
    page.wait_for_function("() => document.getElementById('rfpRescanModalRefresh')?.textContent.startsWith('다음 조회')",timeout=12000)
    page.evaluate("() => {window._rfpOriginalDownloadTrack=document.querySelector('[data-rfp-stage=\"download\"] .rfp-rescan-stage-track');}")
    assert page.locator('#rfpRescanLabel').inner_text().startswith('16.67%'), 'outer progress must stay unchanged'

    # A new server result must actually update both completed numerator and percentage.
    fake['counts'].update(completed=2,remaining=4,unscanned=0)
    fake['lanes']['download']['done']=851
    fake['activity']['items'][0]['bytesDone']=1048576
    fake['lanes']['manifest']['done']=920
    fake['asOf']='2026-11-14T12:01:00+09:00'
    page.evaluate("() => refreshRfpRescanProgress(true)")
    page.wait_for_function(
      "() => document.getElementById('rfpRescanCount')?.textContent.includes('완료 2 / 6건')",
      timeout=12000)
    assert '33.33%' in page.locator('#rfpRescanLabel').text_content()
    assert '최근 판독 +1건' in page.locator('#rfpRescanContent').text_content()
    assert '851 / 1,000건' in page.locator('#rfpRescanContent').text_content()
    assert '1.00 MB / 2.00 MB' in page.locator('#rfpRescanContent').text_content()
    assert page.evaluate("""() => window._rfpFileLiveRow ===
      document.querySelector('[data-lane="download"] .rfp-live-item')"""), 'file row must not remount'

    assert '920 / 1,000건' in page.locator('#rfpRescanContent').text_content()
    assert page.evaluate('() => window._rfpOriginalDownloadTrack===document.querySelector(\'[data-rfp-stage="download"] .rfp-rescan-stage-track\')'), 'progress DOM must not be replaced every 10s'
    assert len(calls)>=2
    assert all('/rfp-rescan-progress?_' in value for value in calls),calls
    page.evaluate("() => document.getElementById('rfpRescanClose').dispatchEvent(new MouseEvent('click',{bubbles:true}))")
    assert modal.get_attribute('aria-hidden')=='true'
    page.evaluate("() => {rfpRescanProgress=null;rfpRescanProgressError='조회 오류';paintRfpRescanProgress();}")
    assert page.locator('#rfpRescanCount').text_content()=='판독 현황 조회 불가'
    assert not errors,errors
    browser.close()
print('WORKLINKS_RFP_RESCAN_LIVE_UI_REGRESSION=PASS')
