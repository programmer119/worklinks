#!/usr/bin/env python3
"""No-network 3,000+ notice regression for WorkLinks evidence-based shortlist."""
import datetime as dt
import importlib.util
import pathlib
import json

root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('actionable',root/'scripts/refresh_worklinks_actionable.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
kst=dt.timezone(dt.timedelta(hours=9))
now=dt.datetime(2026,10,20,13,30,tzinfo=kst)
future='2026-11-04 10:00:00'
past='2026-10-19 13:00:00'
def sample(no,kind,title,license_codes=None,order='000',closes=future,subject=''):
    q=None
    if license_codes is not None:
        q={'ok':True,'complete':True,'checkedAt':'2026-10-20T00:00:00Z',
           'requirements':[{'codes':[code],'group':'1','logic':'UNKNOWN'}
                           for code in license_codes]}
    return {'kind':kind,'bidNo':no,'order':order,'title':title,'closes':closes,
            'budget':'100000000','purchsObjPrdctList':subject,'bidEligibility':q}
company={'ok':True,'found':True,'complete':True,
         'checkedAt':'2026-10-20T00:00:00Z',
         'company':{'name':'창컴정보통신 주식회사'},
         'industries':[{'code':'1468','status':'정상'},
                       {'code':'1426','status':'정상'},
                       {'code':'1169','status':''}]}
rows=[sample('R26BK01760001','servc','2027년 정보시스템 유지관리',['1468'],subject='[1^8111189901^정보시스템유지관리서비스]'),
      sample('R26BK01760002','servc','2027년 플랫폼 개발',['1468','0036']),
      sample('R26BK01760003','servc','2027년 인공지능 AI 앱 개발',None),
      sample('R26BK01760004','servc','AI타워 폐합성수지 처리용역',['1468']),
      sample('R26BK01760005','cnstwk','AI 데이터센터 플랫폼 구축공사',['1468']),
      sample('R26BK01760006','thng','온디바이스 소프트웨어 개발',['1468']),
      sample('R26BK01760007','servc','정보시스템 유지관리',['1169']),
      sample('R26BK01760008','servc','2026년 앱 개발',['1468'],order='000'),
      sample('R26BK01760008','servc','2026년 앱 개발 정정',['1468'],order='001'),
      sample('R26BK01760009','servc','정보시스템 유지관리',['1468'],closes=past),
      sample('R26BK01760010','servc','2027년 앱 개발',['1468'],closes='')]
# >4,000 SW indexed candidates must not silently truncate the index.
for i in range(5200):
    rows.append(sample('R26BK'+str(i).zfill(8),'frgcpt',
                       'AI 플랫폼 홍보 현수막 구매',None))
def fetch(path):
    if not path.startswith('/saved?'):raise AssertionError(path)
    from urllib.parse import parse_qs
    query=parse_qs(path.split('?',1)[1])
    off=int(query['offset'][0])
    size=int(query['limit'][0])
    return {'ok':True,'totalCount':len(rows),'items':rows[off:off+size]}
indexed,count=mod.all_indexed(fetch)
assert count==len(rows) and len(indexed)==len(rows)
rfp={'R26BK01760001:000':{'status':'text_extracted_requires_review'}}
out=mod.build(indexed,count,company,now=now,rfp=rfp)
c=out['counts']
assert c['indexedSWTotal']==len(rows)
assert c['latestRevisions']==len(rows)-1
assert c['softwareService']==5,c
assert c['unknownDeadlineRelevant']==1,c
assert c['publishedIndustryAligned']==2 if 'publishedIndustryAligned' in c else True
byNo={r['bidNo']:r for r in out['bids']}
assert byNo['R26BK01760001']['screening']=='published_industry_codes_match'
assert byNo['R26BK01760001']['rfpTextScanned'] is True
assert byNo['R26BK01760001']['eligibilityVerified'] is False
assert byNo['R26BK01760002']['screening']=='industry_rule_conflict_review'
assert byNo['R26BK01760002']['codesNotInCurrentRegistry']==['0036']
assert byNo['R26BK01760003']['screening']=='official_license_unavailable'
assert 'R26BK01760004' not in byNo,'waste-disposal is not a software bid'
assert 'R26BK01760005' not in byNo,'construction is not a software service'
assert byNo['R26BK01760006']['scope']=='software_goods_review'
assert byNo['R26BK01760007']['screening']=='industry_rule_conflict_review'
assert byNo['R26BK01760008']['order']=='001'
assert 'R26BK01760009' not in byNo
assert byNo['R26BK01760010']['deadlineState']=='unknown'
assert byNo['R26BK01760010']['closes'] is None
assert byNo['R26BK01760010']['needsFullNoticeReview'] is True
assert all(x['needsFullNoticeReview'] for x in out['bids'])
assert all(x['eligibilityVerified'] is False for x in out['bids'])
progress=out['verificationProgress']
assert progress['reviewTarget']==len(out['bids'])
assert progress['industryBasicMatched']==sum(
    b['screening']=='published_industry_codes_match' for b in out['bids'])
assert progress['fullLegalEligibilityVerified']==0
assert progress['executionFeasibilityVerified']==0
assert progress['historicalCompetitionVerified']==0
assert progress['costProfitabilityVerified']==0
assert progress['proposalReadyVerified']==0
assert all(b['officialClauseEvidence']=={} for b in out['bids'])

# Partial official API cannot appear to contain no restrictions.
assert mod.industry_evidence({'bidEligibility':{'ok':True,'complete':False,'requirements':[]}},
                             {'1468'},set())[0]=='official_license_unavailable'
assert mod.parse_close('202610231000')==dt.datetime(2026,10,23,10,0,tzinfo=kst)
maint=sample('R26BK09999001','servc','2027년 정보시스템 유지관리',['1468'],closes=future)
hardware=sample('R26BK09999002','servc','2027년 보존복원 운용장비 유지관리',['1468'],closes=future)
ranked=mod.build([maint,hardware],2,company,now=now)
assert len(ranked['bids'])==2
assert ranked['bids'][0]['bidNo']=='R26BK09999001'
assert all(b['eligibilityVerified'] is False for b in ranked['bids'])
print('WORKLINKS_PRACTICAL_SOFTWARE_RANKING=PASS')
print('WORKLINKS_ACTIONABLE_5200_BIDS=PASS',
      json.dumps({k:v for k,v in c.items() if v},ensure_ascii=False))
