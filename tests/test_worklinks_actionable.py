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
hardware=sample('R26BK09999002','servc','2027년 마을방송 정보시스템 유지관리',['1468'],closes=future)
ranked=mod.build([maint,hardware],2,company,now=now)
assert len(ranked['bids'])==2
assert ranked['bids'][0]['bidNo']=='R26BK09999001'
assert all(b['eligibilityVerified'] is False for b in ranked['bids'])
# A cached award counts only with a worker-verified comparable past notice.
matched=sample('R26BK09999003','servc','2027년 정보시스템 유지관리',['1468'])
matched['repeatHistory']=[
    {'year':2025,'bidNo':'R25BK01111111','title':'2025년 정보시스템 유지관리',
     'verified':True},
    {'year':2024,'bidNo':'R24BK02222222','title':'다른 사업','verified':False}]
old={'R25BK01111111':{'participants':2,'winner':'과거 낙찰업체',
                      'awardAmount':123000000,'awardRate':85,
                      'verifiedAt':'2026-10-20T00:00:00Z'},
     'R24BK02222222':{'participants':1,'winner':'무관 업체',
                      'awardAmount':1000,'awardRate':100,'verifiedAt':''}}
matched_result=mod.build([matched],1,company,now=now,awards=old)
one=matched_result['bids'][0]
assert one['competitionVerified'] is True
assert one['historicalCompetition'][0]['participants']==2
assert len(one['historicalCompetition'])==1
assert matched_result['verificationProgress']['historicalCompetitionVerified']==1
assert one['eligibilityVerified'] is False
# A reviewed tender with fresh SME proof and historical direct-production evidence
# must be visible above the 100s of unreviewed industry matches.
reviewed={'R26BK01760001:000':{'bidNo':'R26BK01760001','order':'000',
 'state':'original_requirements_pending','mandatory':{
 'industryCodes':['1468'],'directProductionCodes':['8111189901'],
 'sme':'소기업 또는 소상공인'}}}
sme={'ok':True,'checkedAt':'2026-10-19T10:00:00+09:00',
     'recordsByBizno':{'1308185973':{'size':'소기업','validState':'valid'}}}
direct={'ok':True,'snapshotDate':'2026-02-01',
        'recordsByBizno':{'1308185973':[{
        'product':'정보시스템유지관리서비스',
        'validFrom':'2025-01-16','validTo':'2027-01-15'}]}}
checked=mod.build(indexed,count,company,now=now,rfp=rfp,
                  reviews=reviewed,sme=sme,direct=direct)
priority=next(x for x in checked['bids'] if x['bidNo']=='R26BK01760001')
assert priority['precheckState']=='documented_precheck'
assert priority['priorityTier']==0
assert priority['basicQualificationEvidence']['currentMatches']==2
assert priority['basicQualificationEvidence']['historicalMatches']==1
assert priority['eligibilityVerified'] is False
assert checked['verificationProgress']['documentedBasicPrechecks']==1
assert checked['bids'][0]['bidNo']=='R26BK01760001'
stale_sme={**sme,'checkedAt':'2026-10-01T10:00:00+09:00'}
stale_result=mod.build([rows[0]],1,company,now=now,reviews=reviewed,
                       sme=stale_sme,direct=direct)
assert stale_result['bids'][0]['precheckState']=='partial_review'
unmatched_direct={**direct,'recordsByBizno':{}}
unknown_result=mod.build([rows[0]],1,company,now=now,reviews=reviewed,
                         sme=sme,direct=unmatched_direct)
assert unknown_result['bids'][0]['precheckState']=='partial_review'
assert unknown_result['bids'][0]['eligibilityVerified'] is False
# Personnel classification: only source-linked, explicit dates produce A/B.
def staffing_clause(quote,url='https://www.g2b.go.kr/pn/official',file='official.hwpx'):
    return {'clauseCandidates':{'staff_proof':[{'text':quote,'url':url,'sourceFile':file}]}}
classify=mod.classify_staffing
hire=classify(staffing_clause('낙찰 후 전문 인력을 신규 채용하여 확보할 수 있다.'),{})
assert hire['class']=='A',hire
existing=classify(staffing_clause('입찰공고일 기준 6개월 이상 재직한 사업 책임자(PM)를 필수로 한다.'),{})
assert existing['class']=='B',existing
both=classify({'clauseCandidates':{'staff_proof':[
    {'text':'낙찰 후 기술 인력 채용 및 확보 가능','url':'https://www.g2b.go.kr/1','sourceFile':'r.hwpx'},
    {'text':'입찰공고일 기준 6개월 이상 재직한 PM 필수','url':'https://www.g2b.go.kr/2','sourceFile':'r.hwpx'}
]}},{})
assert both['class']=='B',both
clear=classify(staffing_clause('본 사업은 투입 인력 요건 없음'),{})
assert clear['class']=='C',clear
unsure=classify(staffing_clause('상주 인력은 수행기간 전담으로 근무하여야 한다.'),{})
assert unsure['class']=='D',unsure
absent=classify({}, {})
assert absent['class']=='D' and absent['evidence'] is None
# An untrusted source cannot become a positive personnel judgement.
external=classify(staffing_clause('낙찰 후 개발자 인력 채용 가능',
                                url='https://unverified.example/notice'),{})
assert external['class']=='D'
human_staff={'officialRfpPerformanceEvidence':{
  'sourceUrl':'https://www.g2b.go.kr/some-attachment',
  'requirements':[{'topic':'on_site_staff','finding':'상주 기술자 근무'}]}}
assert classify({},human_staff)['class']=='D'
staffed_rfp={'R26BK01760001:000':{
 'status':'text_extracted_requires_review',
 'changcomClauseEvidence':staffing_clause('입찰공고일 기준 3개월 재직한 전문기술자 제출 의무')}}
staffed_output=mod.build([rows[0]],1,company,now=now,rfp=staffed_rfp)
assert staffed_output['bids'][0]['staffingClassification']['class']=='B'
assert staffed_output['verificationProgress']['staffingCounts']['B']==1
assert staffed_output['bids'][0]['eligibilityVerified'] is False
print('WORKLINKS_STAFFING_ADBC_CLASSIFICATION=PASS')

print('WORKLINKS_SOURCE_BOUND_BASIC_PRECHECK=PASS')
print('WORKLINKS_PRACTICAL_SOFTWARE_RANKING=PASS')

# Exact-source geographic mismatch: requires official current business location.
real_region={
 'bidNo':'R26BK01760001','order':'000',
 'state':'explicit_mandatory_region_mismatch',
 'mandatory':{'regionCity':'창원시'},'sourceUrl':'https://bizsearch.io.kr/gosi/9888960'
}
rbase={'R26BK01760001:000':real_region}
firm={**company,'company':{'name':'창컴정보통신 주식회사',
                            'regionName':'경기도 부천시 소사구','address':'경기도 부천시'}}
validated=mod.build(indexed,count,firm,now=now,rfp=rfp,reviews=rbase)
record=next(x for x in validated['bids'] if x['bidNo']=='R26BK01760001')
assert record['confirmedRegionalMismatch'] is True
assert record['eligibilityVerified'] is False
assert len(validated['bids'])==len(out['bids'])
assert validated['verificationProgress']['explicitMandatoryMismatch']==1
assert validated['verificationProgress']['precheckedNoticeRequirements']==1
notconfirmed=mod.build(indexed,count,company,now=now,rfp=rfp,reviews=rbase)
assert notconfirmed['verificationProgress']['explicitMandatoryMismatch']==0
already_local={**company,'company':{'regionName':'경상남도 창원시',
                                   'address':'경상남도 창원시'},'complete':True}
no_longer_mismatch=mod.build(indexed,count,already_local,now=now,rfp=rfp,reviews=rbase)
assert no_longer_mismatch['verificationProgress']['explicitMandatoryMismatch']==0
print('WORKLINKS_GROUNDED_MANDATORY_REGION=PASS')
print('WORKLINKS_ACTIONABLE_5200_BIDS=PASS',
      json.dumps({k:v for k,v in c.items() if v},ensure_ascii=False))
