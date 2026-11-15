#!/usr/bin/env python3
"""Browser regression for watched-member keep notifications in other tabs/views."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

KEEP=Path('startup-support/worklinks-keep.js').read_text(encoding='utf-8')
HTML="""<!doctype html><html lang="ko"><head><title>WorkLinks</title></head><body>
<section id="jobsView" class="on"></section>
<div id="keepToolbar" hidden>
  <button id="keepModeAll">전체</button>
  <button id="keepModeMine">내 킵</button><span id="keepMineCount"></span>
  <button id="keepModeWatch">관전</button>
  <label id="keepMemberWrap" hidden>
    <select id="keepMemberSelect"><option value="">관전 대상 선택</option></select>
  </label>
  <button id="keepNotifyButton" hidden>알림 켜기</button>
  <input id="keepShareEnabled" type="checkbox">
  <input id="keepShareAlias"><button id="keepSaveShare"></button>
  <p id="keepStatus"></p>
</div>
<script>
document.documentElement.dataset.worklinksAuthState='granted';
window.qaUser='qa-viewer-22222222';
window.qaItems=[{id:'bid-a',title:'기존 사업',savedAt:'2026-11-15T10:00:00Z'}];
window.qaNotifications=[];
window.Notification=class {
  static permission='granted';
  constructor(title,options){this.title=title;this.options=options;
    window.qaNotifications.push({title,body:options.body});}
  close(){}
  static async requestPermission(){return 'granted'}
};
window.worklinksKeepCurrentUser=()=>window.qaUser;
window.worklinksKeepRequest=async path=>{
  if(path==='/worklinks-keep')return {ok:true,items:[],shareEnabled:true,shareAlias:'QA'};
  if(path==='/worklinks-keep-members')return {ok:true,members:[
    {id:'member-11111111',name:'홍길동',count:window.qaItems.length}]};
  if(path.startsWith('/worklinks-keep-watch?'))return {ok:true,readOnly:true,
    items:structuredClone(window.qaItems),
    member:{id:'member-11111111',name:'홍길동'}};
  throw Error('Unexpected request '+path);
};
window.scheduleJobsRender=()=>{};
window.worklinksHydrateKeptJobs=async()=>{};
window.setWorkspaceView=(view)=>{
  document.querySelector('#jobsView').classList.toggle('on',view==='jobs');
};
</script>
<script type="module" src="./worklinks-keep.js"></script>
</body></html>"""

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1360,'height':768})
    page=context.new_page()
    page.route('https://worklinks.suaveforge.com/startup-support/test-keep-alert',lambda route:
        route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
    page.route('https://worklinks.suaveforge.com/startup-support/worklinks-keep.js',lambda route:
        route.fulfill(status=200,content_type='application/javascript; charset=utf-8',body=KEEP))
    page.goto('https://worklinks.suaveforge.com/startup-support/test-keep-alert')
    page.wait_for_function("!!window.worklinksKeeps && !!document.querySelector('#keepToolbar:not([hidden])')")
    page.locator('#keepModeWatch').click()
    page.wait_for_function("document.querySelector('#keepMemberSelect').options.length===2")
    page.locator('#keepMemberSelect').select_option('member-11111111')
    page.wait_for_function("window.worklinksKeeps.activeItems().length===1")
    assert page.locator('#worklinksWatchAlert').count()==0, 'Existing bookmarks must not notify'
    assert page.locator('#keepNotifyButton').is_visible(), 'Notification control must be available'

    # The user moves to another workspace or another browser tab while watching.
    page.evaluate("""() => {
      document.querySelector('#jobsView').classList.remove('on');
      document.hasFocus=()=>false;
      window.qaItems.push({id:'bid-b',title:'새로 추가한 AI 시스템 사업',
        savedAt:'2026-11-15T10:01:00Z'});
    }""")
    page.evaluate("async () => await window.worklinksKeeps.pollWatch()")
    page.wait_for_function("document.querySelector('#worklinksWatchAlert')?.textContent.includes('AI 시스템')")
    alert=page.locator('#worklinksWatchAlert').inner_text()
    assert '홍길동' in alert and '1건' in alert and 'AI 시스템' in alert,alert
    assert page.evaluate('window.qaNotifications.length')==1, 'Background native notice absent'

    page.evaluate("async () => await window.worklinksKeeps.pollWatch()")
    assert page.evaluate('window.qaNotifications.length')==1, 'Repeated polling notified twice'

    # A second new bid updates the alert, while another workspace remains active.
    page.evaluate("""() => {
      window.qaItems.push({id:'bid-c',title:'추가된 세 번째 사업',
        savedAt:'2026-11-15T10:02:00Z'});
    }""")
    page.evaluate("async () => await window.worklinksKeeps.pollWatch()")
    page.wait_for_function("document.querySelector('#worklinksWatchAlert')?.textContent.includes('2건')")
    assert page.evaluate('window.qaNotifications.length')==2
    # Clicking the alert opens the normal spectator view.
    page.locator('[data-watch-open]').click()
    assert page.evaluate("document.querySelector('#jobsView').classList.contains('on')")
    assert page.locator('#worklinksWatchAlert').count()==0

    # Session change immediately clears alerts and prevents cross-account leaks.
    page.evaluate("""() => {
      window.qaUser='';
      window.dispatchEvent(new Event('worklinks:partner-access'));
    }""")
    assert page.locator('#keepToolbar').is_hidden()
    assert page.locator('#worklinksWatchAlert').count()==0
    print('WORKLINKS_SPECTATOR_BACKGROUND_KEEP_NOTIFICATION=PASS')
    browser.close()
