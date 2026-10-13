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
    browser.close()
