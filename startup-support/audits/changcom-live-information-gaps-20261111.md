# 창컴 마감 전·마감 미확인 후보 API·RFP 데이터 완전성 점검

생성 기준: 2026-11-11T12:30:20+09:00

이 보고서는 **원문 수집 상태**만 점검하며 투찰 자격의 법적 확정이 아니다.
API 정보 누락은 '제한 없음'이 아니고, 파일 일부 텍스트 판독은 RFP 전체 검토 완료가 아니다.

## 집계

| 상태 | 건수 |
|---|---:|
| confirmed_open | 1061 |
| deadline_unknown_separate_recheck | 185 |
| extra_partial | 1246 |
| license_confirmed_basic_code_match | 581 |
| license_needs_followup | 520 |
| license_needs_official_license_api_or_rule_review | 520 |
| license_no_published_license_restriction_detected_unverified | 145 |
| license_raw_industry_rule_conflict_review | 491 |
| license_raw_no_license_restriction_detected | 145 |
| license_raw_official_license_unavailable | 29 |
| license_raw_published_industry_codes_match | 581 |
| listed_total | 1246 |
| missing_core_notice_fields | 185 |
| missing_field_마감시각 | 185 |
| previous_recommendations_present | 3 |
| rfp_attachments_unreadable | 110 |
| rfp_manifest_status_unknown_legacy | 213 |
| rfp_needs_followup | 1246 |
| rfp_no_readable_text:no_official_attachment_metadata | 8 |
| rfp_not_scanned | 915 |
| supplemental_not_complete_or_missing | 1246 |

## 판독 실패 세부 원인

| 에러 코드 | 파일 수 |
|---|---:|
| file_extract_failure | 62 |
| no_searchable_text | 40 |
| pdf_unreadable_page | 34 |
| invalid_hwp | 13 |
| unsupported_format | 7 |
| hwp5txt_failed | 5 |
| large_xml_section | 3 |
| large_file | 1 |
| pdf_over_page_limit | 1 |
| nested_archive_requires_review | 1 |

## 과거 유망 후보 세 건

- R26BK01816467:000 : AI 수요예측 기반 결품·과잉재고 분석 및 의사결정 지원 시스템 구축 및 현장 실증(POC) 용역 / API published_industry_codes_match / RFP not_scanned
- R26BK01816907:000 : 실종아동전문팀 홈페이지 보안 취약점 및 기능개선 / API published_industry_codes_match / RFP not_scanned
- R26BK01804703:000 : 이공계 연구생활장려금 지원사업 전산시스템 고도화 / API published_industry_codes_match / RFP not_scanned

## 세부 목록

[전수 CSV](changcom-live-information-gaps-20261111.csv) — 공고별 필드 누락, API 신뢰 상태, RFP 첨부 수 및 미판독 원인.

수집 배치 상한은 API 전체 사용량에 맞춰 별도 조정해야 하며, 실패 또는 파일 용량 초과를 단순 반복 요청으로 해결할 수 없다.
