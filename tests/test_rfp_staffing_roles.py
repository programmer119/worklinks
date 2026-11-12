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
      'files':[{'name':'제안요청서.pdf','readable':True,
                'staffingRoleScanVersion':1,'staffingRoleScanTruncated':False,
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
print('RFP_STAFFING_ROLE_SOURCE_BACKED_EXTRACTION=PASS')
