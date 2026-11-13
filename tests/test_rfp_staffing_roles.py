#!/usr/bin/env python3
"""No-network tests for source-grounded RFP staffing/role headcounts."""
import pathlib
import runpy

root=pathlib.Path(__file__).resolve().parents[1]
p=runpy.run_path(str(root/'scripts/refresh_worklinks_rfp.py'),run_name='test_staffing_roles')
parse=p['extract_staffing_roles']
summary=p['staffing_summary']
url='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/source'
sample="""투입인력 계획
직무 기술등급 투입인원
PM
고급
1
개발자 중급 2
QA 1명
운영자 2명 비상주
개발자 중급 2
"""
roles=parse(sample,'제안요청서.pdf',url)
found={(x['role'],x['grade'],x['count']) for x in roles}
assert ('PM','고급',1) in found,roles
assert ('개발자','중급',2) in found,roles
assert ('QA','',1) in found,roles
assert ('운영자','',2) in found,roles
assert len(roles)==4,roles
assert next(x for x in roles if x['role']=='운영자')['onsite']=='비상주',roles
assert all(x['sourceFile']=='제안요청서.pdf' and x['sourceUrl']==url for x in roles)

assert parse('사업 담당 PM의 2027년 수행 예정 기간, 개발자 경력 5년',
             '사업계획서.pdf')==[]
assert parse('PM 2MM 투입 예정, 운영자 5개월 경력', '공고문.pdf')==[]
assert parse('사업관리자 인원 수가 10명이라는 일반적인 설명', '공고문.pdf')==[]

explicit=parse('프로젝트 관리자 1명. 개발자 2명 이상. 디자이너 1명',
               '인력운영계획.docx')
assert {x['role'] for x in explicit}=={'프로젝트 관리자','개발자','디자이너'},explicit
assert next(x for x in explicit if x['role']=='개발자')['countKind']=='minimum',explicit

table=parse('직무 | 기술등급 | 투입인원\nPM | 고급 | 1\nDBA | 중급 | 2',
            '운영인력.xlsx')
assert {x['role']:x['count'] for x in table}=={'PM':1,'DBA':2},table

item={'status':'text_extracted_requires_review','manifestComplete':True,
      'files':[{'name':'제안요청서.pdf','readable':True,'sourceTextScanComplete':True,
                'staffingRoleScanVersion':p['STAFFING_ROLE_SCAN_VERSION'],'staffingRoleScanTruncated':False,
                'staffingRoles':roles}]}
summed=summary(item)
assert len(summed)==4,summed
assert next(x for x in summed if x['role']=='PM')['sourceText'],summed
index=p['compact_coverage'](item)
assert index['staffingRoleScanComplete'] is True,index
assert len(index['staffingRoles'])==4,index
assert not p['compact_coverage']({'manifestComplete':False,'files':item['files']})['staffingRoleScanComplete']
legacy={'name':'요약.pdf','clauseCandidates':[{'sourceText':'PM 1명 필수, 개발자 2명'}]}
excerpt=p['staffing_from_saved_excerpts'](legacy)
assert excerpt and all(x['scope']=='excerpt' for x in excerpt),excerpt
assert p['compact_coverage']({'manifestComplete':True,'files':[legacy]})['staffingRoleScanComplete'] is False

api=runpy.run_path(str(root/'server/g2b-proxy.py'),run_name='test_staffing_api')
unknown=api['saved_rfp_search_state'](None,compact=True)
assert unknown['seen'] is False and unknown['staffingRoles']==[]
assert unknown['staffingRoleScanComplete'] is False
state=api['saved_rfp_search_state'](index,compact=True)
assert state['staffingRoleScanComplete'] is True,state
assert len(state['staffingRoles'])==4,state
assert state['staffingRoles'][0]['sourceUrl']==url,state
dirty=dict(index)
dirty['staffingRoles']=list(index['staffingRoles'])+[dict(index['staffingRoles'][0],sourceUrl='https://evil.example/rfp')]
safe=api['saved_rfp_search_state'](dirty,compact=False)
assert safe['staffingRoles'][-1]['sourceUrl']=='',safe
assert not parse('직무 기술등급 인원\nPM(사업총괄) 경력 5년 이상 | 12','인력표.pdf')
assert not parse('투입인력 기술등급 인원\n기술자 부문 배점 20점 이상 6.0','인력표.pdf')
assert not parse('사업관리자(PM)를 지정하고 전담유지보수 1명을 상주시킨다','인력표.pdf')
# Same-stem official PDF can satisfy only the staffing scope of a
# deliberately skipped HWP. The skipped source stays explicitly unreadable.
pdf={'name':'공고서.pdf','readable':True,'sourceTextScanComplete':True,
     'sourceSha256':'a'*64,'qualificationScanTruncated':False,
     'staffingRoleScanVersion':p['STAFFING_ROLE_SCAN_VERSION'],
     'staffingRoleScanTruncated':False,'staffingRoles':[]}
hwp={'name':'공고서.hwpx','readable':False,'skippedDuplicateFormat':True,
     'sourceTextScanComplete':False,'alternatePdfEvidence':'공고서.pdf',
     'alternatePdfSourceSha256':'a'*64}
bundle={'manifestComplete':True,'status':'text_extracted_requires_review',
        'files':[hwp,pdf]}
assert p['compact_coverage'](bundle)['staffingRoleScanComplete'] is True
assert hwp['readable'] is False
fake={'files':[dict(hwp,alternatePdfSourceSha256='0'*64),pdf],
      'manifestComplete':True}
assert p['compact_coverage'](fake)['staffingRoleScanComplete'] is False
assert p['staffing_scan_pending'](bundle) is False

# Generic legal boilerplate/award score examples do not state the current
# project's named, committed staffing.
general='(행안부예규) 지방자치단체 입찰시 낙찰자 결정기준(2026.11.2.).hwpx'
example='산정예시 <기술자 보유> 특급기술자 1인 (경력․관리능력 3년)'
assert parse(example,general)==[]
assert parse('기술자 1명','제안요청서.hwpx')
assert parse('산정예시 기술자 1명','제안요청서.hwpx')==[]
legacy_example={'manifestComplete':True,'files':[{'name':general,
  'readable':True,'sourceTextScanComplete':True,
  'staffingRoleScanVersion':p['STAFFING_ROLE_SCAN_VERSION'],'staffingRoles':[{
    'role':'기술자','count':1,'sourceFile':general,'sourceText':example}]}]}
assert p['staffing_summary'](legacy_example)==[]
# 350k+ characters of generic legal guidance cannot prevent a complete
# project-only role inspection. Do not pretend that guidance was fully read.
generic_law={'name':general,'readable':True,'sourceTextScanComplete':False,
             'staffingRoleScanVersion':p['STAFFING_ROLE_SCAN_VERSION'],'staffingRoleScanTruncated':True}
scope_law={'manifestComplete':True,'files':[generic_law,pdf]}
law_index=p['compact_coverage'](scope_law)
assert law_index['staffingRoleScanComplete'] is True
assert law_index['files'][0]['staffingScopeExcluded'] is True
assert law_index['files'][0]['sourceTextScanComplete'] is False

# A nationwide standard-contract ZIP is not a missing project staffing spec.
# Preserve its unreadable fact, with explicit provenance of the exclusion.
packet={'name':'★[용역] 입찰유의서, 계약일반조건, 특수조건, 적격심사 및 협상기준(행안부).zip',
        'readable':False,'sourceTextScanComplete':False,
        'errorCategory':'pdf_over_page_limit'}
assert p['staffing_general_annex_file'](packet['name'])
scope={'manifestComplete':True,'files':[packet,pdf]}
out=p['compact_coverage'](scope)
assert out['staffingRoleScanComplete'] is True
assert out['files'][0]['readable'] is False
assert out['files'][0]['staffingScopeExcluded'] is True
assert not p['staffing_general_annex_file']('2027년 사업 수행 인력 제안요청서.hwpx')


# Regression fixtures for explicit table and named proposal roles.
table_general=parse('직무 | 등급 | 인원\nPM | 고급 | 1\n개발 | 중급 | 2', '인원표.pdf')
assert {(r['role'],r['count']) for r in table_general}=={('PM',1),('개발',2)},table_general
team=parse('PM 1명, PL 2명, AI 전문가 2명, 포털 개발 2명, 인프라 1명','제안요청서.pdf')
assert {(r['role'],r['count']) for r in team}=={('PM',1),('PL',2),('AI 전문가',2),('포털 개발',2),('인프라',1)},team
assert parse('상주 개발인력 11개월, 투입률 75%', '공내역서.pdf')==[]
stale=dict(item,staffingRoleScanComplete=True,
           files=[dict(item['files'][0],staffingRoleScanVersion=2)])
assert p['staffing_scan_pending'](stale) is True

print('RFP_STAFFING_ROLE_SOURCE_BACKED_EXTRACTION=PASS')
