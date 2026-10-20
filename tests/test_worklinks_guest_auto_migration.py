"""Live WorkLinks page + simulated AuthHub user: automatic guest migration regression."""
import json
from playwright.sync_api import sync_playwright

SITE = 'https://worklinks.suaveforge.com/startup-support/'
CORS = {
    'access-control-allow-origin':'https://worklinks.suaveforge.com',
    'access-control-allow-headers':'authorization,content-type',
    'access-control-allow-methods':'GET,POST,OPTIONS'
}
GUEST = {
    'applied':'externaltools_startup_support_status_v1',
    'hidden':'worklinks_startup_support_hidden_v1',
    'business':'worklinks_startup_support_business_v1'
}
ACCOUNT = {
    'applied':'worklinks_support_applied_v2:',
    'hidden':'worklinks_support_hidden_v2:',
    'business':'worklinks_support_business_v2:'
}
SESSION_KEY = 'authhub:p47:production:session'

def json_reply(route, data, status=200):
    route.fulfill(status=status,content_type='application/json',headers=CORS,body=json.dumps(data,ensure_ascii=False))

def check(predicate, description):
    if not predicate: raise AssertionError(description)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    ctx=browser.new_context()
    page=ctx.new_page()
    who=['worklinks-qa-account-a']
    remote={'worklinks-qa-account-a':{},'worklinks-qa-account-b':{}}
    requests=[]
    should_fail=[False]
    def config(route):
        if route.request.method=='OPTIONS':return json_reply(route,{},204)
        json_reply(route,{'ok':True,'project':'p47','enabled':True,'authApi':'https://api-authhub.suaveforge.com'})
    def me(route):
        if route.request.method=='OPTIONS':return json_reply(route,{},204)
        json_reply(route,{'user':{'id':who[0],'email':'qa@example.test'},'membership':{'status':'active'}})
    def state(route):
        if route.request.method=='OPTIONS':return json_reply(route,{},204)
        acc=who[0]
        if route.request.method=='GET':
            rows=list(remote[acc].values())
            return json_reply(route,{'ok':True,'records':rows})
        entry=json.loads(route.request.post_data or '{}')
        requests.append((acc,entry))
        if should_fail[0]:return json_reply(route,{'ok':False,'error':'simulated_unavailable'},503)
        remote[acc][entry['kind']+':'+entry['id']]={**entry,'updatedAt':'2026-10-13T03:00:00Z'}
        json_reply(route,{'ok':True,'id':entry['id'],'kind':entry['kind'],'value':entry['value']})
    page.route('**/api/g2b/worklinks-auth-config',config)
    page.route('**/v1/me*',me)
    page.route('**/api/g2b/worklinks-state',state)
    page.goto(SITE,wait_until='domcontentloaded',timeout=60000)
    page.locator('#worklinks-auth-info').wait_for(timeout=30000)
    # Guest has support submission, hidden item and "business" classification.
    page.evaluate("""(names)=>{
      localStorage.setItem(names.applied,JSON.stringify({'yangcheon-school':true,'unsubmitted':false}));
      localStorage.setItem(names.hidden,JSON.stringify({'archived-hidden-demo':true}));
      localStorage.setItem(names.business,JSON.stringify({'business-track-demo':true}));
      localStorage.setItem('authhub:p47:production:session',JSON.stringify({accessToken:'qa.mock.session',refreshToken:'qa-refresh'}));
    }""",GUEST)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("""()=>{
      return document.querySelector('#worklinks-auth-info')?.textContent?.includes('서버 저장 완료')
    }""",timeout=30000)
    rows=remote[who[0]]
    check(set(rows)=={'applied:yangcheon-school','hidden:archived-hidden-demo','business:business-track-demo'},'three kinds not auto-migrated')
    check(all(x['value'] is True for x in rows.values()),'migration values incorrect')
    check(page.locator('#worklinks-import').count()==0,'manual import still exists')
    for kind,key in ACCOUNT.items():
        result=page.evaluate("""([key,user])=>JSON.parse(localStorage.getItem(key+user)||'{}')""",[key,who[0]])
        check(any(v is True for v in result.values()),kind+' account local storage missing')
    pending=page.evaluate("""(u)=>JSON.parse(localStorage.getItem('worklinks_support_pending_v2:'+u)||'{}')""",who[0])
    check(not pending,'server-confirmed pending entries not cleared')
    first_count=len(requests)
    print('GUEST_AUTO_MIGRATION_ALL_3_KINDS=PASS',flush=True)
    print('GUEST_MIGRATION_SERVER_PERSISTED=PASS',flush=True)

    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('브라우저+서버 동기화')""",timeout=30000)
    check(len(requests)==first_count,'re-login duplicated an already persisted import')
    print('MIGRATION_IDEMPOTENT_ON_RELOAD=PASS',flush=True)

    # A member's later explicit uncheck must never be reversed by old guest=true.
    page.evaluate("""()=>{
      window.saved['yangcheon-school']=false;
      localStorage.setItem(window.statusKey,JSON.stringify(window.saved));
      window.worklinksStatusChanged('applied','yangcheon-school',false);
    }""")
    page.wait_for_function("""()=>Object.keys(JSON.parse(localStorage.getItem('worklinks_support_pending_v2:worklinks-qa-account-a')||'{}')).length===0""",timeout=30000)
    check(remote[who[0]]['applied:yangcheon-school']['value'] is False,'member uncheck was not saved')
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('동기화')""",timeout=30000)
    check(remote[who[0]]['applied:yangcheon-school']['value'] is False,'guest data re-enabled a member-unchecked entry on re-login')
    check(page.evaluate("""()=>JSON.parse(localStorage.getItem('worklinks_support_applied_v2:worklinks-qa-account-a'))['yangcheon-school']===false"""),'guest data resurrected a member-unchecked local value')
    check(page.evaluate("""()=>JSON.parse(localStorage.getItem('externaltools_startup_support_status_v1'))['yangcheon-school']===true"""),'guest original was unexpectedly deleted')
    print('GUEST_HISTORY_NOT_RESURRECTED_AFTER_UNCHECK=PASS',flush=True)

    # Prevent an unrelated AuthHub user from inheriting this browser's original guest state.
    who[0]='worklinks-qa-account-b'
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("""()=>document.querySelector('#worklinks-auth-controls .worklinks-auth-user')?.textContent?.includes('qa@example.test')""",timeout=30000)
    page.wait_for_timeout(800)
    check(not remote[who[0]],'guest history leaked into another account')
    check(not page.evaluate("""u=>JSON.parse(localStorage.getItem('worklinks_support_applied_v2:'+u)||'{}')['yangcheon-school']===true""",who[0]),'cross-account local data leak')
    print('GUEST_IMPORT_ACCOUNT_ISOLATION=PASS',flush=True)
    ctx.close()

    # A failed API write must keep the original guest and account's pending queue.
    ctx2=browser.new_context()
    page2=ctx2.new_page()
    who[0]='worklinks-qa-account-a'
    remote[who[0]]={}
    should_fail[0]=True
    page2.route('**/api/g2b/worklinks-auth-config',config)
    page2.route('**/v1/me*',me)
    page2.route('**/api/g2b/worklinks-state',state)
    page2.goto(SITE,wait_until='domcontentloaded')
    page2.evaluate("""()=>{localStorage.setItem('externaltools_startup_support_status_v1',JSON.stringify({'yangcheon-school':true}));localStorage.setItem('authhub:p47:production:session',JSON.stringify({accessToken:'qa.mock.session'}))}""")
    page2.reload(wait_until='domcontentloaded')
    page2.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('재시도 대기')""",timeout=30000)
    check(page2.evaluate("""()=>JSON.parse(localStorage.getItem('externaltools_startup_support_status_v1'))['yangcheon-school']===true"""),'failed migration deleted legacy guest data')
    check(bool(page2.evaluate("""()=>Object.keys(JSON.parse(localStorage.getItem('worklinks_support_pending_v2:worklinks-qa-account-a')||'{}')).length""")),'failed migration did not retain pending')
    should_fail[0]=False
    page2.reload(wait_until='domcontentloaded')
    page2.wait_for_function("""()=>Object.keys(JSON.parse(localStorage.getItem('worklinks_support_pending_v2:worklinks-qa-account-a')||'{}')).length===0""",timeout=30000)
    check(remote[who[0]].get('applied:yangcheon-school',{}).get('value') is True,'pending guest record not uploaded after retry')
    print('MIGRATION_OFFLINE_QUEUE_AND_RETRY=PASS',flush=True)
    ctx2.close()

    # The hosted signup/login handoff comes back to auth-callback.html with a
    # one-use code. The callback must save AuthHub session on WorkLinks' origin,
    # redirect home and automatically merge the prior guest status.
    ctx3=browser.new_context()
    page3=ctx3.new_page()
    who[0]='worklinks-qa-account-a'
    remote[who[0]]={}
    page3.route('**/api/g2b/worklinks-auth-config',config)
    page3.route('**/v1/me*',me)
    page3.route('**/api/g2b/worklinks-state',state)
    def exchange(route):
        if route.request.method=='OPTIONS':return json_reply(route,{},204)
        payload=json.loads(route.request.post_data or '{}')
        check(payload.get('code')=='qa-signup-code','OAuth callback code not exchanged')
        json_reply(route,{'accessToken':'qa.mock.session','refreshToken':'qa-refresh','onboarding':{'isNewUser':True,'isNewMembership':True}})
    page3.route('**/v1/auth/p47/exchange*',exchange)
    page3.goto(SITE,wait_until='domcontentloaded')
    page3.evaluate("""()=>localStorage.setItem('externaltools_startup_support_status_v1',JSON.stringify({'yangcheon-school':true}))""")
    page3.goto(SITE+'auth-callback.html?code=qa-signup-code&state=%2Fstartup-support%2F',wait_until='domcontentloaded')
    page3.wait_for_url(SITE,timeout=30000)
    page3.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('서버 저장 완료')""",timeout=30000)
    check(remote[who[0]].get('applied:yangcheon-school',{}).get('value') is True,'signup callback did not auto-migrate guest submission')
    check(page3.evaluate("""()=>!!JSON.parse(localStorage.getItem('authhub:p47:production:session')||'null')?.accessToken"""),'AuthHub callback session not retained')
    print('SIGNUP_CALLBACK_AUTO_MIGRATION=PASS',flush=True)
    ctx3.close()

    # On the first login to an existing member, remote=false wins a conflict
    # with guest=true without deleting the guest's original browser history.
    ctx4=browser.new_context()
    page4=ctx4.new_page()
    who[0]='worklinks-qa-account-a'
    remote[who[0]]={'applied:yangcheon-school':{'kind':'applied','id':'yangcheon-school','value':False,'title':'prior member choice'}}
    page4.route('**/api/g2b/worklinks-auth-config',config)
    page4.route('**/v1/me*',me)
    page4.route('**/api/g2b/worklinks-state',state)
    page4.goto(SITE,wait_until='domcontentloaded')
    page4.evaluate("""()=>{
      localStorage.setItem('externaltools_startup_support_status_v1',JSON.stringify({'yangcheon-school':true}));
      localStorage.setItem('authhub:p47:production:session',JSON.stringify({accessToken:'qa.mock.session'}));
    }""")
    page4.reload(wait_until='domcontentloaded')
    page4.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('동기화')""",timeout=30000)
    check(remote[who[0]]['applied:yangcheon-school']['value'] is False,'existing remote=false overwritten by guest=true')
    check(page4.evaluate("""()=>JSON.parse(localStorage.getItem('worklinks_support_applied_v2:worklinks-qa-account-a'))['yangcheon-school']===false"""),'member remote=false not rendered')
    print('SERVER_FALSE_CONFLICT_PRESERVED=PASS',flush=True)
    # The guest check remains recoverable, without silently overwriting a
    # member's previous false value. Restoration needs a deliberate click.
    page4.get_by_role('button',name='지원기록 점검').click()
    page4.locator('[data-recover-id="yangcheon-school"]').wait_for(timeout=15000)
    check(remote[who[0]]['applied:yangcheon-school']['value'] is False,
          'history recovery overwrote a member choice without consent')
    page4.locator('[data-recover-id="yangcheon-school"]').click()
    page4.wait_for_function("""()=>JSON.parse(
      localStorage.getItem('worklinks_support_applied_v2:worklinks-qa-account-a')||'{}'
    )['yangcheon-school']===true""",timeout=10000)
    page4.wait_for_function("""()=>Object.keys(JSON.parse(
      localStorage.getItem('worklinks_support_pending_v2:worklinks-qa-account-a')||'{}'
    )).length===0""",timeout=15000)
    check(remote[who[0]]['applied:yangcheon-school']['value'] is True,
          'explicit recovery not persisted to member server')
    page4.reload(wait_until='domcontentloaded')
    page4.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('동기화')""",timeout=15000)
    check(page4.evaluate("""()=>!!window.saved['yangcheon-school']"""),
          'recovered support completion disappeared after login refresh')
    print('GUEST_APPLIED_CONFLICT_RECOVERED_WITH_EXPLICIT_CLICK=PASS',flush=True)
    ctx4.close()

    # GET outages must not be interpreted as an empty member DB, and must not
    # transmit a guest import before remote data has been reconciled.
    ctx5=browser.new_context()
    page5=ctx5.new_page()
    remote[who[0]]={}
    fail_get=[True]
    writes_before=len(requests)
    def failing_get(route):
        if route.request.method=='GET' and fail_get[0]:
            return json_reply(route,{'ok':False,'error':'temporary_server_read_failure'},503)
        return state(route)
    page5.route('**/api/g2b/worklinks-auth-config',config)
    page5.route('**/v1/me*',me)
    page5.route('**/api/g2b/worklinks-state',failing_get)
    page5.goto(SITE,wait_until='domcontentloaded')
    page5.evaluate("""()=>{
      localStorage.setItem('externaltools_startup_support_status_v1',JSON.stringify({'yangcheon-school':true}));
      localStorage.setItem('authhub:p47:production:session',JSON.stringify({accessToken:'qa.mock.session'}));
    }""")
    page5.reload(wait_until='domcontentloaded')
    page5.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('서버 기록 조회 실패')""",timeout=30000)
    check(len(requests)==writes_before,'uploaded without reading existing member state')
    check(page5.evaluate("""()=>JSON.parse(localStorage.getItem('externaltools_startup_support_status_v1'))['yangcheon-school']===true"""),'outage deleted original guest history')
    fail_get[0]=False
    page5.evaluate("()=>window.dispatchEvent(new Event('online'))")
    page5.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('서버 저장 완료')""",timeout=30000)
    check(remote[who[0]]['applied:yangcheon-school']['value'] is True,'online retry did not finish automatic migration')
    print('SERVER_READ_FAILURE_PRESERVES_AND_RETRIES=PASS',flush=True)
    ctx5.close()

    # After the member identity has been verified, an expired API token must
    # refresh only within the same AuthHub identity and retry the queued write.
    ctx6=browser.new_context()
    page6=ctx6.new_page()
    who[0]='worklinks-qa-account-a'
    remote[who[0]]={}
    refresh_count=[0]
    def expired_api(route):
        if route.request.method=='POST' and route.request.headers.get('authorization')=='Bearer qa.expired':
            return json_reply(route,{'ok':False,'error':'invalid_authhub_session'},401)
        return state(route)
    def renew(route):
        refresh_count[0]+=1
        return json_reply(route,{'accessToken':'qa.renewed','refreshToken':'qa.new.refresh','expiresIn':3600})
    page6.route('**/api/g2b/worklinks-auth-config',config)
    page6.route('**/v1/me*',me)
    page6.route('**/v1/auth/p47/refresh*',renew)
    page6.route('**/api/g2b/worklinks-state',expired_api)
    page6.goto(SITE,wait_until='domcontentloaded')
    page6.evaluate("""()=>{
      localStorage.setItem('externaltools_startup_support_status_v1',JSON.stringify({'yangcheon-school':true}));
      localStorage.setItem('authhub:p47:production:session',JSON.stringify({accessToken:'qa.expired',refreshToken:'qa.old.refresh'}));
    }""")
    page6.reload(wait_until='domcontentloaded')
    page6.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('서버 저장 완료')""",timeout=30000)
    check(remote[who[0]]['applied:yangcheon-school']['value'] is True,'expired token did not retry the pending record')
    check(refresh_count[0]==1,'AuthHub refresh unexpectedly repeated')
    check(page6.evaluate("""()=>JSON.parse(localStorage.getItem('authhub:p47:production:session'))?.accessToken==='qa.renewed'"""),'renewed session not persisted')
    print('EXPIRED_AUTHHUB_TOKEN_AUTO_REFRESH_AND_RETRY=PASS',flush=True)
    ctx6.close()

    # A completely fresh browser has no guest migration or account-local history.
    # It must reconstruct all three kinds from authenticated server records alone.
    ctx7=browser.new_context()
    page7=ctx7.new_page()
    who[0]='worklinks-qa-account-a'
    remote[who[0]]={
        'applied:yangcheon-school':{'kind':'applied','id':'yangcheon-school','value':True,'title':'양천 창업학교','url':'https://example.org/a'},
        'hidden:archived-hidden-demo':{'kind':'hidden','id':'archived-hidden-demo','value':True,'title':'숨김 공고','url':'https://example.org/b'},
        'business:business-track-demo':{'kind':'business','id':'business-track-demo','value':True,'title':'사업자 공고','url':'https://example.org/c'}
    }
    page7.route('**/api/g2b/worklinks-auth-config',config)
    page7.route('**/v1/me*',me)
    page7.route('**/api/g2b/worklinks-state',state)
    page7.goto(SITE,wait_until='domcontentloaded')
    check(page7.evaluate("""()=>localStorage.getItem('worklinks_support_guest_migration_owner_v1')===null"""),'new browser was not blank')
    page7.evaluate("""()=>localStorage.setItem('authhub:p47:production:session',JSON.stringify({accessToken:'qa.other.device'}))""")
    page7.reload(wait_until='domcontentloaded')
    page7.wait_for_function("""()=>document.querySelector('#worklinks-auth-info')?.textContent?.includes('브라우저+서버 동기화')""",timeout=30000)
    for kind, id in [('applied','yangcheon-school'),('hidden','archived-hidden-demo'),('business','business-track-demo')]:
        local=page7.evaluate("""([kind,id])=>JSON.parse(localStorage.getItem('worklinks_support_'+kind+'_v2:worklinks-qa-account-a')||'{}')[id]===true""",[kind,id])
        check(local,'server '+kind+' missing on a fresh browser')
    check(page7.evaluate("""()=>localStorage.getItem('worklinks_support_guest_migration_owner_v1')===null"""),'cross-device restoration unexpectedly claimed guest migration')
    print('FRESH_BROWSER_SERVER_RESTORE_ALL_3_KINDS=PASS',flush=True)
    ctx7.close()
    browser.close()
