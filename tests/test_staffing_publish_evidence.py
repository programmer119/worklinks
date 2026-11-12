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
print('STAFFING_ROLE_EVIDENCE_PUBLISH_GUARD=PASS')
