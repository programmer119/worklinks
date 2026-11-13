#!/usr/bin/env python3
"""Do not publish annex numbers, scoring points or somebody else's headcount."""
import pathlib,runpy
root=pathlib.Path(__file__).resolve().parents[1]
r=runpy.run_path(str(root/'scripts/publish_worklinks_staffing_patch.py'),
                 run_name='staffing_evidence_test')
trust=r['defensible_staffing_row']
def row(role,count,source):
    return {'role':role,'count':count,'sourceText':source}
assert trust(row('PM',1,'PM | 고급 | 1'))
assert trust(row('개발자',2,'개발자 중급 2명 투입'))
assert trust(row('운영 인력',2,'웹/와스 서버 운영 인력은 경험자 2인 이상 투입해야 함'))
assert trust(row('PM',12,'PM(사업총괄) 경력 5년 이상 | 12')) is False
assert trust(row('PM',5,'사업관리자(PM) 이력 기재 방법 | 【별지 5】')) is False
assert trust(row('기술자',20,'보유기술자 등급별 계수를 곱한 값(점) 평가20점 이상')) is False
assert trust(row('PM',1,'사업관리자(PM)을 지정하고 전담유지보수 1명을 상주시킨다')) is False
assert trust(row('PM',3,'PM | 경력 3년 이상 | 3')) is False
fact_guard=r['defensible_staffing_fact']
official={'kind':'staffing_requirement','requirementType':'onsite',
  'label':'상주인력 근무·휴가 조건','headcount':None,'sourceLine':2133,
  'sourceFile':'2. 제안요청서.hwpx',
  'sourceText':'상주인력의 휴가 등은 사전 승인을 받고 업무상 차질이 없도록 하여야 함'}
assert fact_guard(official),official
assert not fact_guard({**official,'label':'상주 8명 필수'}),'invented counts must never publish'
assert not fact_guard({**official,'headcount':8}),'source says no headcount'
assert not fact_guard({**official,'sourceFile':'입찰유의서 계약일반조건.zip'}),'general-law annex cannot supply contract staffing'
assert not fact_guard({**official,'sourceText':'사업과 무관한 안내 문구'}),'required matching source passage missing'
pm={'kind':'staffing_requirement','requirementType':'pm',
    'label':'PM 10년 경력 · 참여율 50% 이상','headcount':None,'sourceLine':2153,
    'sourceFile':'2. 제안요청서.hwpx',
    'sourceText':'사업총괄인력(PM)은 해당분야에서 10년 이상 업무를 수행한 자로서 계약일~12월까지 50%이상 참여해야 함'}
assert fact_guard(pm),'explicit source values support the PM label'
assert not fact_guard({**pm,'label':'PM 20년 경력 · 참여율 50% 이상'}),'cannot change 10 to 20 years'
assert not fact_guard({**pm,'label':'PM 10년 경력 · 참여율 80% 이상'}),'cannot change 50 to 80 percent'
print('STAFFING_ROLE_EVIDENCE_PUBLISH_GUARD=PASS')
