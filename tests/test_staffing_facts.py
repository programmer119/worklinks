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
# Generic document-source checks: these apply to all procurement IDs, not a
# hand-maintained collection of two exceptional notices.
lx_rfp="""본 사업은 사업대가를 기능점수(FP) 방식(유지관리)과 투입공수 방식(운영)으로 구성된 사업으로, 중단없는 시스템 유지·운영을 위해 발주처와 조직 및 인력, 투입인력 근무조건 등의 협의가 필요함
- SW사업정보 중 기능점수 데이터의 작성을 위해 사업수행 인원 중 기능점수 산정 가능 전문가를 포함토록 함
※ 참여인력이 대표사 또는 공동수급업체 인원인 경우에는 재직증명서를 붙임으로 첨부하고, 그 외 인력(채용예정인력 등)은 추후 추가 협상과정에서 발주기관의 요청이 있을 시 증빙자료를 제출해야 함"""
facts=read(lx_rfp,'노후계획도시_제안요청서.hwp')
types={(f.get('requirementType'),f.get('label')) for f in facts if f['kind']=='staffing_requirement'}
assert ('workplace','근무조건 협의') in types,types
assert ('expertise','FP 산정 전문가 포함') in types,types
assert ('proof','참여인력 재직·경력 증빙') in types,types
assert all(f.get('headcount') is None for f in facts if f['kind']=='staffing_requirement')
assert all(f.get('sourceLine',0)>0 and f.get('sourceText') for f in facts)

seoul_rfp="""요구사항번호MHR-001요구사항 명상주인력 근무조건요구사항 분류유지관리인력 요구사항상세설명정의유지운영 인력의 중단 없는 지원세부내용ㅇ 유지운영 인력은 담당자 부재 시 업무공백이 발생 하지 않도록 업무별 담당을 정/부로 관리해야 하며 해당 업무의 정/부가 동시에 부재되지 않도록 해야 함ㅇ 상주인력의 휴가 등은 사전 승인을 받고 업무상 차질이 없도록 하여야 함산출정보관련요구사항
요구사항 번호 MHR-002요구사항 명 투입인력 및 업무수행요구사항 분류 유지관리 인력 요구사항상세설명정의 투입인력 자격요건 및 임무⋅역할세부내용ㅇ 투입인력 - 사업총괄인력(PM)은 소프트웨어 관련 해당분야에서 10년 이상 업무를 수행한 자로서 계약일(1월)~12월까지 50%이상 참여해야 하며
제출장소 제 출 서 류․ 참여인력 증거서류 ․ 기술 및 경력 증거서류 ․ 재직 증명 서류(건강보험 자격 득실 확인서 등)
ㅇ 참여인력(제안서 인력)은 입찰 공고일 현재 제안사(공동수급체 포함) 구성원의 자사인력으로 구성하여야 한다."""
facts=read(seoul_rfp,'2. 제안요청서.hwpx')
need={'onsite','pm','proof','workforce'}
actual={f.get('requirementType') for f in facts if f['kind']=='staffing_requirement'}
assert need.issubset(actual),(need,actual,facts)
assert all(f.get('headcount') is None for f in facts if f['kind']=='staffing_requirement')
assert not any(f.get('requirementType')=='four_insurance_required' for f in facts)
# The source excerpt must contain its matched clause, not just the first 240
# characters of a merged 3000-character HWPX text row.
long_line='문서 일반 목차 소개 문구 '*80+' 상주인력의 휴가 등은 사전 승인을 받고 업무상 차질이 없도록 하여야 함'
facts=read(long_line,'제안요청서.hwpx')
assert any('사전 승인' in f['sourceText'] for f in facts if f['kind']=='staffing_requirement'),facts
assert not any(f['kind']=='staffing_requirement' for f in read(seoul_rfp,'입찰유의서 및 계약일반조건.zip'))
assert not any(f['kind']=='staffing_requirement' for f in read('산정 예시 상주인력의 휴가 등은 사전 승인을 받고',
                                                      '계약서류_평가예시.hwpx'))
print('STAFFING_FACTS_SEPARATE_ROLE_WORKLOAD_RECOMMENDATION_PASS')
