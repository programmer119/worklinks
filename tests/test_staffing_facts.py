#!/usr/bin/env python3
"""Prove source-backed headcount / workload / staffing plans are not conflated."""
import pathlib,sys
root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
from staffing_facts import extract_staffing_facts as read

yongin="""○ 투입공수 방식 SW운영비 산정 (단위 : 원)
업무 구분 직무 투입구분 ⓐ평균임금*
(Month) ⓑ투입기간
(Month) ⓒ투입률
기능개선 및 유지관리 사업 총괄관리 IT PM 협의 3 0.114 0
웹 콘텐츠 개발 및 유지관리 응용SW 개발자 평균 4 0.25 0
기능개선 및 유지관리
(상주인력) 응용SW 개발자 평균 11.04 0.75 0
웹 콘텐츠 디자인 UI/UX 디자이너 협의 3.5 0.2 0
퍼블리싱 UI/UX 개발자 협의 3 0.4 0
총 투입공수 투입기간 * 투입률 11.521999999999998
"""
facts=read(yongin,'공내역서.xlsx')
workloads=[x for x in facts if x['kind']=='workload_role']
total=[x for x in facts if x['kind']=='workload_total']
assert len(workloads)==5,facts
assert len(total)==1 and total[0]['manMonths']==11.522,facts
assert round(sum(x['manMonths'] for x in workloads),3)==11.522,facts
assert all(x['headcount'] is None for x in workloads),facts
assert [x['onsite'] for x in workloads]==[False,False,True,False,False],facts

north="""MHR-002 사업수행 인력투입 요건
핵심인력 분류
사업관리자
(PM)
o주사업자 소속의 IT PM 직무에 해당하는 자
사업수행관리자
(PL)
o최근 5년 이내 3년 이상 SW개발 직무를 수행한 자
인공지능 및
빅데이터 분야
전문가
포털SW 기능개선
인프라관리
상용SW·HW
* 위 인원은 분야를 조정할 수 있으나, 상주인력 월평균 8명 이상을 유지 권고
"""
facts=read(north,'제안요청서.hwpx')
rec=[x for x in facts if x['kind']=='headcount_recommended']
assert len(rec)==1 and rec[0]['count']==8 and rec[0]['mandatory'] is False,facts
assert len([x for x in facts if x['kind']=='role_unspecified'])==5,facts
assert all(x.get('headcount') is None for x in facts if x.get('role')),facts

exercise="""유지관리 인력 요구사항(MHR)
MHR-001 투입 인력 관리 조건
○ 본 사업과 관련하여 투입되는 인력 구성, 조직 체계 등을 제시
○ 제안사는 사업의 성공적인 추진을 위해 투입될 인원 현황을 제시하고 작업 단위별 업무분장 내역을 제시하여야 함
○ 제안사는 투입 인력 구성 시 유사 프로젝트 개발 경험이 있는 전문 기술인력으로 '유지관리 인력 요구사항'을 준수하여야 함
"""
facts=read(exercise,'제안요청서.hwpx')
assert any(x['kind']=='staffing_plan_required' for x in facts),facts
assert all(x.get('count') is None for x in facts),facts
assert not any(x['kind']=='headcount_recommended' for x in facts),facts

generic='산정예시 기술자 8명 이상 평가 배점 20점 이상'
assert not read(generic,'(행안부예규) 지방자치단체 입찰시 낙찰자 결정기준.hwpx')
assert not any(x['kind']=='headcount_recommended' for x in read(generic,'제안요청서.hwpx'))
assert read('기술자 참여 인원수 * 경력별 점수20점 이상','제안요청서.hwpx')==[]
print('STAFFING_FACTS_SEPARATE_ROLE_WORKLOAD_RECOMMENDATION_PASS')
