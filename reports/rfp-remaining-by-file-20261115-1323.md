# 창컴 WorkLinks 3차 판독 미완료 공고 및 파일 전체 목록

**실제 운영 서버 123 읽기 전용 조회:** 2026-11-15 13:23 KST (04:23 UTC)  
**대상:** 원본 다운로드 상태 `ready`이고 판독 상태 `retry` 또는 `scanning`인 공고 **478건**. 그중 `retry` 470건, `scanning` 8건. 별도로 원본 완료·판독 `pending` 6건은 실패 목록에서 제외함.  
**파일별 문제 기록:** **652행**, 파일별 오류 코드가 없지만 공고 검증 미완료 **1건** 별도 기록. 같은 공고의 중복 파일명은 데이터 기록대로 유지함. `scanning`은 아직 최종 실패 확정이 아님.  
**별도 OCR 보정기 후보:** 동시점 414개 공고(`ready`), 94개 `waiting_for_verified_download`, 5개 첨부목록 불일치. 별도 보정기의 집계이므로 판독 재시도 470건과 일대일 대응하지 않음.

## 원인 유형별 파일 수

| 오류 코드·미완료 종류 | 파일 기록 |
|---|---:|
| `pdf_ocr_incomplete` | 260 |
| `no_searchable_text` | 177 |
| `file_extract_failure` | 38 |
| `hwp5txt_failed` | 28 |
| `readable_but_source_scan_incomplete` | 28 |
| `invalid_hwp` | 28 |
| `source_extraction_timeout_deferred` | 26 |
| `readable_but_scanner_truncated` | 16 |
| `ocr_deferred_to_repair` | 13 |
| `unsupported_format` | 13 |
| `unknown_archive_member_requires_review` | 12 |
| `large_xml_section` | 7 |
| `archive_many_xml_files` | 3 |
| `pdf_over_page_limit` | 2 |
| `no_problem_file_but_incomplete` | 1 |
| `isolated_extraction_worker_failed` | 1 |

**판독 기록이 남아 있는 공고 478건 전체를 아래에 파일별로 표시합니다.** `file_extract_failure`, `no_searchable_text` 등은 저장된 코드이며 내부 예외의 세부 원인까지 확정한 뜻이 아닙니다. 확장자와 판독 오류 코드가 다를 수도 있으므로 원본 파일 마법값과 추출기를 비교해야 합니다.

## 공고별 / 파일별 남은 문제

| 구분 | 공고번호 | 파일명 | 문제 코드 | 기록 세부내용 |
|---|---|---|---|---|
| retry | `R26BK01797861:000` | 공내역서.xlsx | `archive_many_xml_files` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806524:000` | 6. 안내자료(선금 및 상생결제제도 안내 등).zip | `archive_many_xml_files` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814778:000` | [붙임] 입찰서류 일체.zip | `archive_many_xml_files` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01763165:001` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01766737:001` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01781600:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01782057:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01786362:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01790085:000` | 입찰공고문_전차선(2공구)v.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01791320:000` | 공고문_ERP시스템 유지관리 용역.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01792436:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01798829:000` | R26BK01798829-000 [붙임] 제안요청서 등.zip | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802945:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804320:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01805314:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01805360:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01805690:000` | 붙임2. 규격서.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806571:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806666:000` | 1. 입찰공고문.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809321:000` | 공고서_R26BK01809321(국가,sw,중기간,수요_경찰청 중앙경찰학교).pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811890:000` | [입찰공고]AAU LMS 용 AI챗봇 도입 사업_재공고.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812929:000` | 입찰 공고(2026-0733).zip | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816714:000` | 1. 물품 구매 입찰 공고문_3차원 형상 측정시스템.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818426:000` | 공고문_2026년 서울특별시 의료장비 통합구매 2차 재공고(서울특별시 보라매병원, 신경내시경시스템).pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818624:000` | 4. 긴급입찰요청서(2027년 광주시 방범용 CCTV 시스템 통합유지보수 용역).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818863:000` | 입찰공고문(2027년 선박 전자증서 발급시스템 유지보수 및 운영).pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819272:000` | 용역붙임자료(2026).zip | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819419:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819500:000` | 입찰공고서(재공고) 1부.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819599:000` | 규격서 등.zip | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819730:000` | 규격서및시방서_환풍기.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819901:000` | 1.2026-058입찰공고(액체수소 공급시스템용 극저온 밸브 제작).pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819974:000` | (입찰)제안요청서_2026년 글로벌 OTT 플랫폼 연계형 제작지원(RAkuten Viki)_조련의 여왕_디지털 색보정(DI) 용역 제안요청서.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820255:000` | 특수조건 안전보건수준평가 등.zip | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820359:000` | 공고문.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820680:000` | 입찰공고문 - 2027년 업무정책시스템 통합 유지관리 용역.pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821914:000` | 1. 공고문(DGIST 제2026-190-1호).pdf | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822238:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823893:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825441:000` | 설계내역서(2027년도 상수도시설물 중앙감시시스템 모니터링 용역).xlsx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828163:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01745687:001` | 2. (탄자니아) 제안요청서.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01745687:001` | 2. (탄자니아) 제안요청서.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01750936:001` | 제안요청서.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01785734:000` | 2. 공고용_제안요청서_무인기 플랫폼 제작 및 시험지원.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01786925:000` | 2. 물품명세서_ 공용 컴퓨팅 시스템.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806397:000` | 2. 물품명세서_임무성능 분석용 전산장비 등.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806913:000` | 붙임. 과업내용서.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808384:000` | 제안요청서_한국자동차연구원.hwpx | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809397:000` | [주식회사 루미너스] 태풍_VFX용역_(재공고).hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809397:000` | [주식회사 루미너스] 태풍_VFX용역_제안요청서(재공고).hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813495:000` | 붙임5. 제안요청서_DHCP시스템외 1종 유지보수_2027년.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814222:000` | 2. 물품명세서_연구개발용 워크스테이션.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815447:000` | 성도고등학교 AI융합형교육실구축 인테리어공사 공내역서.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817639:000` | 구매의뢰수량내역서_CTTS.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817661:000` | 2027학년도 봉양중,경북소프트웨어마이스터고 교복(동,하복) 디자인 사양서.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818127:000` | 공 내역서_엑스포과학공원 노후 PAD S_W 교체공사.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818179:000` | 제출 서류_탕 조리 연구 로봇 시스템.hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819031:000` | [붙임5] 2026 성과공유제 제도 안내문(입찰공고용).hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820206:000` | 2. 물품명세서_펌웨어 알고리즘 시뮬레이션 SW.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820507:000` | [공내역서] 광주AI교육원 BF본인증 보완공사.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823006:000` | 2. 물품명세서_공중교전 소프트웨어 개발환경 II.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823111:000` | 1. (교체-45) 2026년도 실험실습기자재확충 품목명세서.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823651:000` | 붙임10. 수출용신형연구로 화학제주입시스템 상세설계 제조 제안요청서(평가세부기준 포함).hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823651:000` | 붙임9. 수출용신형연구로 화학제주입시스템 상세설계, 제조 입찰안내서(세부기준 포함).hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824033:000` | 1. (교체-55) 2026년도 실험실습기자재확충 품목명세서.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825407:000` | 2. 물품명세서_설계공학용 SW.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826844:000` | (물품내역서) 2026학년도 신산업특화지원사업단 제3차 기자재 구매.xls | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827555:000` | 제출 서류_푸드테크 조리 자동화 시스템(2026.11.12).hwp | `hwp5txt_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01759044:000` | 통합의료정보시스템 고도화 사업 입찰서류.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01764148:000` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01772242:000` | 3. 일반조건.hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01788116:000` | 4. 전자입찰특별유의서.hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804092:000` | 서울특별시 용역계약 특수조건(서울특별시예규)(제746호)(20261001) (1).hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01805597:000` | 계약예규 및 참고서식(공고시 붙임서류).zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806163:000` | 3. 용역 계약 시 나라장터 필첨 서류.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808816:000` | 5. 입찰유의서,계약일반조건 등.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811210:001` | 계약조건(경쟁).zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812217:000` | 1. 용역계약일반조건.hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812217:000` | 2. 용역입찰유의서.hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812217:000` | 3.국가종합전자조달시스템 전자입찰특별유의서(조달청고시)(제2024-23호)(20250106).hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812274:000` | 1. 용역계약일반조건.hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812274:000` | 2. 용역입찰유의서.hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812274:000` | 3.국가종합전자조달시스템 전자입찰특별유의서(조달청고시)(제2024-23호)(20250106).hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815555:000` | 입찰유의서, 계약일반조건 등(26.11.2.).zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816168:000` | 3. 참고서류.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818024:000` | 입찰공고문 등(KREI 정보보호시스템 통합유지관리).zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818912:000` | 첨부파일.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820986:000` | 관련규정_국가계약법_수의(우수)_시운전_국가.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824406:000` | 3. 용역 계약 시 나라장터 필첨 서류.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825567:000` | 5. 입찰_공동계약.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825567:000` | 계약조건(경쟁).zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826370:000` | 관련규정_지방계약법_수의(우수)_시운전_지방.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827125:001` | 입찰 참여 유의사항.zip | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827991:000` | 1.(계약예규) 용역계약일반조건(재정경제부계약예규)(제149호)(20260430).hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827991:000` | 2.(계약예규) 용역입찰유의서(기획재정부계약예규)(제820호)(20251231).hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827991:000` | 3.국가종합전자조달시스템 전자입찰특별유의서(조달청고시)(제2024-23호)(20250106).hwp | `invalid_hwp` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816075:000` | 긴급발주사유서.hwp | `isolated_extraction_worker_failed` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789856:000` | 1_(내역서) 1공구 설계내역서(전차선)_공내역.xlsx | `large_xml_section` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01793416:003` | 2. (설계내역서) 정보통신공사 내역서(1공구)_공내역v.xlsm | `large_xml_section` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01794289:001` | (설계내역서) 정보통신공사 내역서 (2공구)_공내역.xlsx | `large_xml_section` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807866:000` | 참조_27년 통합유지보수 대상장비 목록(공고용).xlsx | `large_xml_section` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814959:000` | 정기구입 목록_26년 4분기.xlsx | `large_xml_section` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824627:000` | 설계서(경북선 상주1 건널목 등 5개소 지능형 CCTV 개량공사).xlsx | `large_xml_section` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826833:000` | 3. 투찰내역서_방글라데시 AI 혁신기술 전문인력 양성사업.xlsm | `large_xml_section` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01830846:000` | (해당 파일 오류 기록 없음) | `no_problem_file_but_incomplete` | 공고 완료 검증 미충족, 파일별 원인 확인 필요 |
| retry | `R26BK01761331:000` | (붙임3) 안전·보건조치 준수 서약서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01764812:000` | 04_입찰 참가 신청서 양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01769051:000` | 입찰업체 서약서 및 공동책임 확인서(서식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01771462:001` | 취소공고서_국가_공동_개발_단독_수요기관평가.hwpx | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01771582:000` | 붙임3. 사전공개내용 주요 변경사항.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01772242:000` | 8. 입찰참가신청서(서식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01780184:000` | [붙임1] 입찰공고 요약보고(2027년 농식품바우처 통합플랫폼 운영 및 유지관리).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01782260:000` | 청렴계약 및 공정거래 이행각서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01782476:000` | 9. 소프트웨어사업관련 법령준수 자체점검표_IP교환기 상용SW.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01782482:000` | 9. 소프트웨어사업관련 법령준수 자체점검표_CTI시스템 상용SW.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01785012:001` | 취소 공고서.hwpx | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01785438:001` | 취소공고서_국가_제한_개발_단독_수요기관평가.hwpx | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01786136:000` | 04_입찰 참가 신청서 양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01786249:002` | 구매규격서 외자KIMS 2026-3-2호.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01787906:000` | 9. 소프트웨어사업관련 법령준수 자체점검표_RDBMS(ORACLE)상용SW.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01788886:001` | 취소 공고서.hwpx | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789246:000` | 11. 소프트웨어사업 영향평가 결과서.pdf | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789246:000` | 12. 과업심의 결과서.pdf | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789296:000` | 11. 소프트웨어사업 영향평가 결과서.pdf | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789296:000` | 12. 과업심의 결과서.pdf | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789856:000` | 3_2_[시방서] 자재시방서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01790085:000` | 3_2_[시방서] 자재시방서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01790119:000` | 3_2_[시방서] 자재시방서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01790885:000` | 04_입찰 참가 신청서 양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01791237:000` | 26-서울-102. 공통규격서_4K복강경시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01792503:000` | 1.용도설명서(DC파라미터측정시스템).hwpx | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01793369:001` | (양식) 제안서접수조서_자산경영시스템(ISO55001) 고도화 및 갱신용역.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01794083:000` | 26-보라매-144. 공통규격서_액체질소저장시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01795941:000` | 4. 긴급공고요청사유서_2027~2029년 정보시스템 통합유지관리 용역.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01798615:000` | 26-보라매-120. 공통규격서_슬라이드스캐너(디지털병리솔루션 포함).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01800323:003` | 3. 긴급공고 사유서_인프라.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01800329:002` | 3. 긴급공고 사유서_응용.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01800658:000` | 4. 긴급공고 사유서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01801800:000` | 26-보라매-118. 공통규격서_4K.ICG복강경시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01801815:000` | 붙임2. 구매규격서(SAR모니터링).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802833:002` | 내자 2026-236 - 라만 분광기 측정 시스템 - 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802833:002` | 내자 2026-236 - 라만 분광기 측정 시스템 - 용도설명서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804761:000` | 4-3. 수의계약사유서(유지관리또는커스터마이징)_.hwpx | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01805351:000` | 입찰참가신청서(용역, 공사).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806319:000` | 2. 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806319:000` | 3. 평가표.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806397:000` | 3. 세부 규격(명세)서_임무성능 분석용 전산장비 등.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806663:000` | 가격입찰서,_입찰보증금지급각서(서식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806929:000` | 2. 물품구매규격서_액체크로마토그래피 시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807007:000` | 2. 물품구매규격서_이미지분석시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807168:000` | 2. 물품구매규격서_ 소동물 초음파 이미징.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808105:000` | 2. 용도설명서_SW 구성요소 분석 솔루션 및 SW 정적분석 자동화 솔루션.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808105:000` | 3. 물품시방서_SW 구성요소 분석 솔루션 및 SW 정적분석 자동화 솔루션.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809480:000` | 1. 입찰 제안요청서(2027년도 공영주차장·차고지 주차관제시스템 통합유.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809521:000` | 2. 용도설명서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01810900:000` | (붙임2) 청렴계약이행서약서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01810900:000` | (붙임3) 안전·보건조치 준수 서약서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01810946:001` | 내자 2026-254 의료 AI 연구용 고성능 컴퓨팅 서버 - 용도설명서 및 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811457:000` | 6.수의계약 체결 제한 여부 확인서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811518:000` | 입찰참가신청서(2단계 경쟁 등).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812217:000` | 10.입찰참가신청서(양식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812274:000` | 10.입찰참가신청서(양식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813136:000` | 2. 물품구매규격서_광합성측정장치.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813292:000` | 6.수의계약 체결 제한 여부 확인서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813330:000` | 2. 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813497:000` | 제안서 평가표_경남 제조 특화 AI 대전환 데이터 플랫폼 구축.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814222:000` | 3. 세부명세서_연구개발용 워크스테이션.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814436:000` | 2026년도 통계 소프트웨어 규격서(SPSS, SAS).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815827:000` | 2.용도설명서_광학식 비접촉 3차원 형상 측정 시스템 구매.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815827:000` | 3.제품사양서_광학식 비접촉 3차원 형상 측정 시스템 구매.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816039:000` | (물품규격서) 리플로우 오븐 시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816599:000` | 3. 규격서(에너지신산업 제조공정 협동로봇 시스템).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816614:000` | 입찰보증금 지급각서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816649:000` | 첨부1. 규격비교표.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816649:000` | 첨부2. 퇴직자 영입(근무) 현황 확인서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816714:000` | 3. 규격서(3차원 형상 측정시스템).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816872:000` | 가격입찰서,_입찰보증금지급각서(서식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817002:000` | 3. 규격서(3차원 적층 제조시스템).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817589:000` | 1. 긴급발주요청서_2024년 천안시 거점형 스마트시티 조성사업-헬스케어 데이터 실증 및 수집.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817675:000` | 입찰서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817719:000` | 2-1.과업내용서 사전공개대비 비교표.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817719:000` | 4.제안서 접수조서 양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817757:000` | 피지컬AI 사물인터넷 로봇 교육용 실습장치_오픈개방형_기자재규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817760:001` | 2026년 (국비) 교육·연구용 기자재 SEM-EDS 시스템(중고)_납품특수조건.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817760:001` | 2026년 (국비) 교육·연구용 기자재 SEM-EDS 시스템(중고)_물품내역서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818041:000` | 입찰참가신청서(용역, 공사).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818426:000` | 26-보라매-062. 공통규격서_신경내시경시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818683:000` | 2.용도설명서_구조해석 소프트웨어 유지 및 지원서비스.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818683:000` | 3.물품시방서_구조해석 소프트웨어 유지 및 지원서비스.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818688:000` | 물품사양서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818772:000` | 물품사양서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819031:000` | [붙임1] 입찰공고 요약보고(2027년 임산부 관리시스템(에코이몰) 유지관리 및 기능개선 용역.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819049:000` | 3. 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819135:000` | 3. 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819153:000` | 3. 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819527:001` | 물품규격적합확인서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819527:001` | 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819531:000` | 산출내역서_공고(1).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819531:000` | 제안요청서_공고(1).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819716:000` | 물품규격적합확인서_소액수의견적입찰용.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819807:000` | 입찰참가신청서_TTA(물품).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820052:000` | 수의계약체결제한여부확인서_KAIST_소액수의_소기업소상공인.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820135:000` | 붙임2_사양서_3차원 홀로토모그래피 현미경 시스템_수정.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820250:000` | 규격비교표.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820359:000` | 첨부1. 규격비교표.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820359:000` | 첨부2. 퇴직자 영입(근무) 현황 확인서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820422:000` | 입찰참가자격등록신청서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820422:000` | 청렴계약 이행 서약서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820450:000` | 용역계약 일반조건.hwpx | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820519:000` | [첨부5]청렴계약이행 입찰유의서 등_2026년 통행료징수시스템 예비품(트래들) 구매.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820537:000` | 물품구매규격서(디지털진단용엑스선촬영장치).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820593:000` | 2. 가격산출 내역서_반자동융착기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820593:000` | 4. 품목명세서_반자동융착기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820708:000` | 2-1. 상세규격서_무인대출반납기_261105.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820708:000` | 2-2. 상세규격서_스피드게이트_261105.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820708:000` | 3. BIDDING SPECIFICATION(양식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820770:000` | 내자 2026-259 - 다중 GPU 고성능 컴퓨팅 서버 - 용도설명서 및 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820788:000` | 물품구매 품목별 세부사양서(덕산고 AI융합교실 교육용키트).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820849:000` | [붙임] 입찰참가신청서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820884:000` | 구매물품사양서(태블릿 구매).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820953:000` | 2. 가격산출 내역서_튜브충진실링기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820953:000` | 4. 품목명세서_튜브충진실링기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820975:000` | [붙임] 입찰참가신청서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821005:000` | 2. 가격산출 내역서_파라메터 검사기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821005:000` | 4. 품목명세서_파라메터 검사기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821077:000` | 내자 2026-260 - 반도체 소자 분석 측정 시스템 - 용도설명서 및 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821189:000` | 26-보라매-064. 공통규격서_4K카메라시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821403:000` | 2026-256 - 공진기 기반 물성 분석 플랫폼 구축 - 용도설명서 및 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821528:000` | 붙임1. 품목 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821528:000` | 붙임3. 확약서(서식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821743:000` | 수의계약체결제한여부확인서_KAIST_소액수의_소기업소상공인.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821802:000` | 별첨양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821914:000` | 2. 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821914:000` | 3. BIDDING SPECIFICATION(양식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822215:000` | 7-1. 현장(사양)설명회 참가신청서 1부.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822275:000` | 7-1. 현장(사양)설명회 참가신청서 1부.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822321:000` | 내자2026-239 - AI연구·교육 환경 고도화를 위한 서버 시스템 자원 확충 - 용도설명서 및 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822518:000` | 물품규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822533:000` | 4. 산출내역서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822764:000` | 2. 가격산출 내역서_자동포장기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822764:000` | 4. 품목명세서_자동포장기.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822827:001` | 1. 고성능 계산용 컴퓨터 서버 (물품구매규격서).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823111:000` | 2-1. (내자)물품구매규격서(의복압측정시스템).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823111:000` | 2-2. (내자)물품구매규격서(동작분석기).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823126:000` | 1. 연구장비 규격서_서버2.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823180:000` | 구매의뢰수량내역서_1793003400085.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823385:000` | 3. 규격서_전자동 정제 시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823385:000` | 5. 규격비교표 서식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823391:000` | 20261111 붙임_기자재구매사양서(CNC선반).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824715:000` | 청렴계약 이행서약서 및 이행각서_양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824801:000` | 2. 상세규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824801:000` | 3. BIDDING SPECIFICATION(양식).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824990:000` | 구매의뢰수량내역서_1791969319977.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825369:000` | 물품규격서_인천가톨릭대학교 도서관서버 교체사업.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825541:000` | 물품구매규격서(AI 보행보조재활로봇).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825668:000` | 3.규격입찰서_양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825889:000` | 수의계약체결제한여부확인서_KAIST_소액수의_소기업소상공인.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825916:001` | 구매물품 세부규격서v1.0.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826340:000` | 2. 물품규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826340:000` | 3. 물품인수확인서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826340:000` | 4. 온라인입금의뢰서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826684:000` | 2. 규격서(수강신청 미들웨어).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826773:000` | 3. (붙임4,5)입찰참가신청서 및 청렴계약 이행각서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826991:000` | 2.사양서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827399:000` | 3. 상세규격 및 용도설명서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827399:000` | 4. 구매물품내역서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827797:000` | 11. 소프트웨어사업 영향평가 결과서.pdf | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827797:000` | 12. 과업심의 결과서.pdf | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827986:000` | 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828461:000` | 3. 규격입찰서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829098:000` | 별첨양식.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829225:000` | 붙임. 규격서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829598:000` | 청렴계약이행서약서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829729:000` | (붙임2) 청렴계약이행서약서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829729:000` | (붙임3) 안전·보건조치 준수 서약서.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829895:000` | 03_규격서_자외선차단지수시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829923:000` | 입찰공고자료(26G056-H).zip | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829962:000` | 입찰공고자료(26G057-H).zip | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830099:000` | 03-1_규격서_친환경원료생산시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830116:000` | 26-보라매-041. 공통규격서_표면유도방사선치료시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830128:000` | 03-2_규격서_안정성평가시스템.hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830452:000` | 상세규격서(12채널 입력 데이터 수집 하드웨어).hwp | `no_searchable_text` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01787906:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823180:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823859:000` | 물품공급 및 기술지원 확약서.tif | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823859:000` | 물품공급 및 기술지원 확약서.tif | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824990:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825180:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825193:000` | 과업내용 종합심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825216:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825226:000` | 과업 심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825235:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825248:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828675:000` | 과업심의결과서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829059:000` | 기술사양서.png | `ocr_deferred_to_repair` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01751142:000` | 입찰 공고(2026-0633).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01759055:000` | 입찰공고문 일체.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01763188:000` | 입찰 공고(2026-0662).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01763450:000` | 기술지원협약서.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01763537:000` | 8. 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01763579:000` | 8. 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01766710:000` | 긴급입찰 사유서(조달의뢰).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01767174:000` | KOICA 입찰 관련 규정 및 지침(260922).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01771582:000` | 붙임4. 소개자료 및 운영현황.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01777477:000` | 긴급입찰사유서(국회 통합디지털센터).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01777788:000` | 전자입찰공고(2026.10.19).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01778884:000` | 2027년 위기청소년통합지원정보시스템 운영 및 유지보수 관련 기술지원협약서(27종).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01778884:000` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01779951:000` | 입찰 재공고문 일체.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01782476:000` | 10. 소프트웨어사업 영향평가 검토결과서(IP교환기 상용SW 유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01782482:000` | 10. 소프트웨어사업 영향평가 검토결과서(CTI시스템 상용SW 유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01785438:001` | 학생의 실질적 AI 역량 강화를 위한 주권 AI 구축 사업 계획(안)_총장결재.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01787270:000` | 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01787906:000` | 10. 소프트웨어사업 영향평가 검토결과서(RDBMS(ORACLE) 상용SW 유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789246:000` | 기술지원협약서.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01789296:000` | 기술지원협약서.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01791199:000` | 붙임2. 2026년 한국학술지인용색인(KCI) DB 구축 사업 긴급사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01793424:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01795767:000` | 3. (엔진) 국문규격서.hwp | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01795767:000` | 4. 하이브리드 추진시스템용 수소혼소엔진 및 전기추진 통합 모듈 견적서_260907.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01795767:000` | 5. (엔진)긴급입찰사유서-직인날인본.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01795941:000` | 7) 공공기관 사칭 범죄 주의 안내문.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01796087:000` | 4. 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01797861:000` | 3.긴급계약사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01797963:000` | 사업 계획서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01799200:000` | 규격서 등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01799247:000` | 과업지시서(2027년 생활안전용 CCTV시스템 통합 유지관리).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01799247:000` | 긴급입찰사유서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01799247:000` | 물품공급  및 기술지원 협약서(합본)_2027년 생활안전용 CCTV시스템 통합 유지관리 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01799524:000` | 10. 소프트웨어사업 영향평가 결과서-2027년 IMIS 및 SMMS 시스템 유지보수 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01799724:000` | 6. 소프트웨어사업 영향평가 결과서-2027년 K-AMI GIS 및 Platform 시스템 유지보수 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01800740:000` | 3. 물품공급및기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01801110:000` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01801110:000` | 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01801713:000` | 기술지원협약서[2027년 정보시스템 통합유지관리 용역(긴급)].pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802563:001` | (첨부필요) 긴급입찰 사유서_PA202602473.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802640:000` | 붙임4. 긴급입찰공고사유서(2027-28년 국립재난안전연구원 행정정보시스템 및 전산장비 유지관리).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802702:000` | 물품공급 및 기술지원 협약서(2027년).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802703:000` | 물품공급 및 기술지원협약서(수정).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802775:000` | (과업지시서)2027년 부안군 CCTV 및 통합관제센터 유지관리용역_261105.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802775:000` | (물품공급기술지원협약서)2027년 부안군 CCTV 및 통합관제센터 유지관리용역_261105.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01802960:000` | (물품공급 및 기술지원 협약서)_2027년 파주시도서관 정보화시스템 통합유지관리 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01803526:001` | 기술지원협약서(날인).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01803526:001` | 긴급입찰 사유서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01803526:001` | 지역제한 사유서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01803611:000` | 긴급 입찰 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01803700:000` | (붙임) 물품공급기술지원협약서(2027 고양시).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01803700:000` | (붙임) 물품공급기술지원협약서(2027 고양시).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804092:000` | 붙임10_2027년 물품공급및기술지원 협약서(2종).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804417:000` | (기술지원 협약서)2027년 김포시 정보통신인프라 통합 유지관리 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804474:000` | 2027년 CCTV 통합관제시스템 통합 유지보수 용역 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804586:000` | (사업계획서)2027~2028년 정보화시설 유지관리 사업 계획.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01804698:000` | 2027년 성남시 공간정보시스템 통합유지관리 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806183:000` | (붙임) 물품공급 및 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806192:000` | 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806277:000` | 3. 과업지시서_2026학년도 글로벌 보건의료 시스템 현장실습 프로그램 운영 용역.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806277:000` | 5. 긴급입찰요청사유서_2026 글로벌 보건의료 시스템 현장실습 프로그램 운영 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806387:000` | 2027년 ERP시스템 유지보수 기술지원 협약서(직인날인).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806666:000` | 3. 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01806796:000` | 3. 유지보수 대상장비 목록 및 정보통신망 구성도.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807194:000` | 8_단일규격사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807233:000` | [별첨 1-1] 물품공급 및 기술지원협약(falconstor).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807233:000` | 붙임 3.  긴급입찰사유서(안).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807458:000` | 3.기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807665:000` | 2. 2027년 Allbaro 및 폐기물처분부담금 협업콜센터 위탁운영 과업내용서_회신2.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807665:000` | 4. 용역계약 추가특수조건(공공부문 도급 노동자 보호 조건)_수정회신.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807665:000` | 5. 개인정보처리위탁 특수조건.hwp | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807665:000` | 6. 긴급입찰 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808308:000` | 기술지원협약서 통합본.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808698:000` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808803:000` | 2-1. 공사원가계산서_저장탱크-수정.xlsx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808803:000` | 3. 국문규격서_261014.hwp | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808803:000` | 긴급입찰사유서-직인날인본.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808803:000` | 부산대 수소선박센터 센서성능검사 견적 261016.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809317:000` | 2027년 공간정보시스템 통합유지보수 용역(기술지원협약서).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809385:000` | 물품공급기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809525:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01809762:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01810345:001` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01810351:000` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01811211:000` | 소프트웨어사업 영향평가 검토결과서(2027년).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811416:000` | 견적서1_AI 데이터 고성능 스토리지 시스템 견적서_HITACHI v2.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811416:000` | 구매규격서_선박 블록 조립공정 AI 데이터 고성능 스토리지 시스템_RF.hwp | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811416:000` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811457:000` | 0.한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811464:000` | 3. 기술지원협약서(27년 유지관리).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811869:000` | 긴급입찰 사유서(2027년 의왕시 정보자원 통합 유지관리 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01811976:000` | 붙임4 영남이공대학교 산학협력단 사업자등록증.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812018:000` | 붙임4 영남이공대학교 산학협력단 사업자등록증.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812572:001` | 261016 평택(스도) 기술지원협약서(10부).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812609:000` | 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812695:000` | 시방서 등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812910:000` | 국제입찰(제외) 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812910:000` | 긴급입찰사유서(2027년 농림축산검역 정보자원 통합유지관리 사업).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01812957:000` | 물품공급 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813104:000` | 물품공급 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813292:000` | 0.한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813949:000` | 기술지원협약서(디지털홍보영상시스템).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01813949:000` | 긴급입찰 사유서(2027년_2028년 정부세종청사 인터넷전화 및 방송통신시설 유지관리 용역).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814204:000` | 긴급 발주요청 사유서(날인).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814268:000` | 물품공급 및 기술지원 협약서(2027년 스마트도시 솔루션 통합유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814390:000` | 긴급입찰 사유서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814658:000` | 261016 평택(스도) 기술지원협약서(10부).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814888:000` | [붙임4-4] 소프트웨어사업 영향 평가결과서(2027년 노후위험 시설물 안전관리 시스템 통합유지관리).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814888:000` | [붙임4-5] 물품공급 및 기술지원 협약서(2027년 노후위험 시설물 안전관리 시스템 통합유지관리).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815023:000` | 5) 공공기관 사칭 범죄 주의 안내문.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815237:000` | 3. 치과 구강스캐너 외 13종 규격서.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815420:000` | 물품공급 및 기술지원 협약서(12사 14종).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815699:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815766:000` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01816121:000` | 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01816121:000` | 지역제한 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816180:000` | [산출내역서, 신규버전] '27~28년도 선박장거리위치추적시스템(LRIT) 위탁운영_260929.xlsx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816419:000` | 별첨1_기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816419:000` | 별첨3_소프트웨어사업영향평가별과서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816523:000` | 물품공급 및 기술지원협약서(이노뎁).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816523:000` | 물품공급 및 기술지원협약서(후지쯔).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816535:000` | 붙임5. 물품공급 및 기술지원협약서(39개 업체 취합본).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816569:000` | 시방서(장마 동정마을 하수도 증설사업 수밀시험 및 CCTV조사 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816664:000` | 2027년 정읍시 통합관제센터 및 현장 CCTV 유지보수 용역 과업지시서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816865:000` | 물품공급 및 기술지원 협약서 - 2027년 하남시 버스정보시스템(BIS) 유지보수 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816944:000` | 제안요청서 등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01817330:000` | 기술지원협약서 목록(2027년 스마트도시 시스템 통합유지관리 용역).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01817330:000` | 기술지원협약서(2027년 스마트도시 시스템 통합유지관리용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817385:000` | 물품공급·기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817472:000` | 3. 긴급입찰 사유서(정보시스템 통합유지보수 사업).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01817748:000` | 3. 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818312:000` | 제안요청서 등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818568:000` | 3-1. 기술지원협약서(두산 디지털이노베이션BU).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818568:000` | 3-2. 기술지원협약서(이지트래픽).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818805:000` | 03 긴급입찰사유서(2027년 공간정보시스템 통합 유지관리 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818805:000` | 04 기술지원협약서(브이앤지).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819419:000` | 제안요청서 및 기술원협약서.Zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819537:000` | 전자입찰공고(2026.11.10).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819664:000` | (붙임3) 물품규격서_[실험실습기자재(학과신규3차)] 디지털 위상차 현미경 등 3종 구매.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820077:000` | 물품공급 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820213:000` | 구매규격서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820568:000` | 물품공급 및 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01820598:000` | 붙임3. 긴급공고 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821259:001` | 5. (한국방송광고진흥공사) 선금지급 특수조건.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821259:001` | 7. [참고] 직원 사칭 허위구매 사기 주의 안내.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821423:000` | 11. 물품공급·기술지원 협약서(2027년 재난상황실 및 재난 예경보시스템 통합 유지보수 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821423:000` | 2. [본문]2027년 재난상황실 및 재난 예경보시스템 통합 유지보수 용역.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821503:000` | 붙임4. 물품공급 및 기술지원협약서(2027년 정보통신 통합 유지보수 용역).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821525:000` | 2. 입찰공고 붙임자료 일체.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821736:000` | 2. 입찰공고 붙임자료 일체.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821858:000` | 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821858:000` | 긴급입찰 사유서(2027년 통합관제시스템 및 현장CCTV 유지보수 용역).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821918:000` | 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821923:000` | 기술지원협약서(2027년 경상남도 홈페이지 통합유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822069:001` | 5. (한국방송광고진흥공사) 선금지급 특수조건.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822069:001` | 7. [참고] 직원 사칭 허위구매 사기 주의 안내.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| scanning | `R26BK01822302:001` | 긴급 입찰 사유서(2027년 어업관리단 종합정보시스템 유지관리).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822388:000` | [긴급입찰 사유서] 2027년도 도로기상정보시스템 유지관리 및 기능개선 사업.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822388:000` | 통합발주 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822405:001` | 긴급 입찰 사유서(2027년 전산장비(PC, 네트워크 및 전화장비) 유지관리).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822414:001` | 긴급 입찰 사유서(2027년 어업지도선 네트워크 및 CCTV 유지관리).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822577:000` | 긴급입찰사유서(간호학과 실험실습기자재).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822620:000` | 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822734:000` | 물품공급·기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822948:000` | 4. 긴급입찰요구사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822991:000` | 4. 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823163:000` | 물품공급·기술지원 협약서[2027년~2028년 충무시설 영상회의시스템 등 통합 유지관리 용역].pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823180:000` | 6. 물품공급 또는 기술지원협약서_이메일 APT 보안 라이선스 외 3종 구매.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823180:000` | 8. 소프트웨어사업 영향평가 검토결과서_이메일 APT 보안 라이선스 외 3종 구매.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823198:000` | (붙임) 3. 유지보수등급측정표(2027년 행정정보시스템 통합유지관리 용역).xlsx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823198:000` | (붙임) 4. 기술지원협약서 목록(2027년 행정정보시스템 통합 유지관리 용역).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823203:000` | (붙임8)긴급발주 요청서(2027년 행정정보시스템 통합유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823371:000` | 제안요청서 등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823510:000` | 제안요청서 등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823696:000` | 3. 물품공급 및 기술지원협약서[2027년 학습관리시스템 유지관리 용역].zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823706:000` | 붙임4. 보안성검토 문서(2026년 환경안전통합관리시스템 구축(2차).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823838:000` | 물품공급 및 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823840:000` | 2026년 통합자동제어설비 유지관리용역 과업지시서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823840:000` | 물품공급 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823853:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823916:000` | 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823992:001` | 규격서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823994:000` | 붙임4_SW과업심의결과서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824253:000` | (공고문 첨부용)[상생결제제도 안내자료] 1차이하 협력기업(요약본).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824253:000` | 공고문[2026-3203]_AI 기반 교통관리시스템 구축 사업관리용역.pdf | `pdf_ocr_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01824268:000` | 물품공급·기술지원 협약서(공간정보시스템 통합유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824444:000` | 긴급입찰 사유서(통합관제센터 및 현장 CCTV 유지관리용역) (1).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824444:000` | 물품공급·기술지원 협약서(관인날인).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824522:000` | 붙임8.물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824549:000` | 개인정보_취급위탁계약_특수조건(1301공소청콜센터_시스템_유지관리).hwp | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824549:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824549:000` | 긴급입찰_사유서(1301공소청콜센터_시스템_유지관리).hwp | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824549:000` | 일반용역계약_특수조건(1301공소청콜센터_시스템_유지관리).hwp | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824569:000` | 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824598:000` | 3. 물품공급및기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824754:000` | 3. 물품공급,기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824990:000` | 붙임11. 기술지원 안내서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824990:000` | 붙임9. 소프트웨어사업 영향평가 결과서_2027년 MySQL 라이선스 구매.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825048:000` | 3. 긴급입찰 사유서_2027년도 재난 예경보시스템 통합 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825048:000` | 제안요청서등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825180:000` | 소프트웨어사업 영향평가 검토결과서_15.네트워크접근관리시스템(NAC) 외 1종 SW 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825188:000` | (물품공급및기술지원 협약서)2027년 창원시 CCTV통합관제시스템 유지보수 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825193:000` | 소프트웨어사업 영향평가 검토결과서_17.메일분석용APT시스템 외 2종 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825212:000` | 2-2. 견적서(전기차 주행 특성 기반 탑승 편의성 을 위한 디지털트윈 플랫폼 구축 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825216:000` | 소프트웨어사업 영향평가 검토결과서_25.웹쉘탐지시스템 외 1종 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825226:000` | 소프트웨어사업 영향평가 검토결과서_19.문서암호화(DRM) SW 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825235:000` | 소프트웨어사업 영향평가 검토결과서_22.웹 취약점 진단관리 SW 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825248:000` | 소프트웨어사업 영향평가 검토결과서_23.보안설정 취약점 진단시스템 관리 SW 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825372:000` | 261111 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825631:000` | (붙임3) 산출기초조사서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825636:000` | 261111 기술지원협약서(2027~2028년 공공자가망·와이파이 통합유지관리 용역)(구매협의 수정).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825843:000` | 기술지원협약서(아이앤씨솔루션).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825843:000` | 기술지원협약서(지오투정보기술).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825843:000` | 긴급발주 사유서(공간정보시스템).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01825973:000` | 03. 물품공급 기술지원 협약서(DBMS).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826043:000` | 3. 물품공급. 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826091:000` | 긴급입찰 사유서(27년 정보화사업_최종).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826122:000` | 2027년 통합도서관리시스템 유지관리 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826158:000` | (긴급입찰사유서) 해운항만물류정보시스템 위탁운영(2027~2028).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826216:000` | (긴급입찰 사유서) 수산정보통합시스템 운영·유지관리(2027~2028).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826221:000` | 붙임4 영남이공대학교 산학협력단 사업자등록증.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826240:000` | 긴급입찰 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826373:000` | 제안요청서 등.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826377:000` | 기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826380:000` | 소프트웨어사업 영향평가 검토 결과보고(2027년 국가정보통신망 통합유지관리 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826550:000` | 긴급발주요청 사유서(2027년 정보공개시스템 운영 유지관리).hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826665:000` | 최종_긴급입찰사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826701:000` | 산출내역서(2027년도 통신시스템 통합유지보수)_공개용.xlsx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826833:000` | 7. KOICA 입찰 관련 규정 및 지침(260811).zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826844:000` | (규격서)2026학년도 신산업특화사업단 제3차 실험실습기자재 구매.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826958:000` | (기술지원협약서)2027년도 5등급 차량운행제한 단속시스템 유지보수 용역.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827147:000` | 기술지원 협약서(2027~2028년 서버 통합 유지관리 사업).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827520:000` | (붙임5) 긴급입찰사유서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827797:000` | 6. 기술지원협약서_오라클.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827874:000` | 물품공급.기술지원 협약서(2027년 부동산종합공부시스템 유지보수 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01827991:000` | 0.한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828288:000` | 사업계획서.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828632:000` | 물품공급·기술지원 협약서(직인완료).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828675:000` | 소프트웨어사업 영향평가 검토결과서_20.보안취약점 점검시스템 SW 유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828697:000` | (붙임)과업내용서[2027년 정보통신시스템 통합유지관리].hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828697:000` | (붙임)물품공급 및 기술지원 협약서[2027년 정보통신시스템 통합유지관리].pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828734:000` | 긴급입찰 사유서(2027년 정보보호시스템 유지관리 용역).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828882:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828906:000` | 물품기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828922:000` | 4. 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828947:000` | [붙임6]긴급입찰공고사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828947:000` | 물품공급기술지원 협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829002:000` | 0 2027년 물품공급 및 기술지원협약서_(주)사이냅소프트.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829002:000` | 0 2027년 물품공급 및 기술지원협약서_(주)유풍정보기술.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829044:000` | 10. 소프트웨어사업 영향평가 검토결과서(디지털TRS 상용SW 유지보수).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829292:000` | (기술지원협약서)오산시 도서관 정보화시스템 통합유지보수.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829292:000` | (긴급입찰 사유서)오산시 도서관 정보화시스템 통합유지보수.hwpx | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829363:000` | 정보통신 통합 유지보수 용역 기술지원협약서.zip | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829449:000` | 긴급 구매 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829449:000` | 단일 규격 사유서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829783:000` | 3.물품공급 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01829964:000` | [물품공급 또는 기술지원협약서] 지능형 포렌식센터 구축을 위한 침해사고 분석 장비 도입(포렌식용 다기능 워크스테이션).pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830262:000` | 3. 도면.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830313:000` | 기술지원협약서.pdf | `pdf_ocr_incomplete` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01774133:000` | 4. 입찰안내서_안산송산 집단에너지 열네트워크 구축사업 열수송관 공사.pdf | `pdf_over_page_limit` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830313:000` | ★[용역] 입찰유의서, 계약일반조건, 특수조건, 적격심사 및 협상기준(행안부), 서약서 양식 (11.6.부터).zip | `pdf_over_page_limit` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01767174:000` | 5. 투찰내역서.xlsm | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01778153:000` | 3. 원가계산용역 보고서.pdf | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01797202:000` | 제안요청서_지능형무역투자플랫폼 (수정).hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01807233:000` | 붙임 2.  제안요청서(안)_구매업무협의 및 사전규격반영.hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01819559:000` | (파일명 공란) | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01819559:000` | [붙임] 제안요청서(1110)_최종.hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01820077:000` | [제393호,시행2026.11.2]지방자치단체 입찰시 낙찰자 결정기준.hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01820568:000` | [제393호,시행2026.11.2]지방자치단체 입찰시 낙찰자 결정기준.hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01823838:000` | [개정전문] 지방자치단체 입찰시 낙찰자 결정기준(2026.11.2.시행).hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01823853:000` | [개정전문] 지방자치단체 입찰시 낙찰자 결정기준(2026.11.2.시행).hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01824754:000` | (행안부예규) 지방자치단체 입찰시 낙찰자 결정기준(2026.11.2.).hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01825683:000` | (제안요청서) 2027년 교육행정기관 통합누리집 유지관리(20261104).hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01826043:000` | (행안부예규) 지방자치단체 입찰시 낙찰자 결정기준(2026.11.2.).hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01828094:000` | (제안요청서)2027년 정부24 운영 및 유지관리 사업_261113.hwpx | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01828094:000` | (파일명 공란) | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01828557:000` | 용역계약 일반조건(2026. 11. 6.).zip | `readable_but_scanner_truncated` | 읽힘; 자격조건 판독 잘림; 인원 판독 잘림; 원문 검사 미완료 |
| retry | `R26BK01786079:000` | 상생결제제도 안내 자료.zip | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01786079:000` | 입찰공고문_홈쇼핑 모니터링 시스템.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01805847:000` | 03.품목명세서.hwp | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01807679:000` | 입찰공고문_NIA2026-128호(재공고_수정).pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01809545:000` | 입찰공고문(2027년 종묘 종합경비시스템 유지보수 용역) 재공고.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01813528:000` | 8. 긴급입찰사유서(2027년 공단 정보시스템 통합 유지관리 및 운영).hwp | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01816681:000` | 2. 입찰공고문(규격가격)_OHT 픽업용 AI 모션제어 시스템.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01817569:000` | 1. 입찰공고문(규격가격).pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01818498:000` | 1. 입찰공고문(규격가격).pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01818651:000` | 입찰공고문(규격가격)_초음파 검사 AI 학습 및 추론용 엣지 컴퓨터.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01818912:000` | (긴급)물품구매(제조)입찰공고_통합모니터링 등 설치.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01819516:000` | 입찰공고문.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01821035:000` | 입찰공고문(규격가격)_HIL기반 통합제어기 기능안전 검증환경 유지보수.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01821259:001` | 6. [참고] 상생결제 안내.zip | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01821476:000` | 에기평 정밀화학과제 입찰 공고문_생물배양시스템(게시).pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01822069:001` | 6. [참고] 상생결제 안내.zip | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01824113:000` | 입찰(재)공고문(3차).pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01824155:000` | 입찰공고문(규격가격)_토크 데이터 확보용 너트러너 및 반력바 일체형 체결 작업 장치.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01824341:000` | [입찰공고] 경영정보시스템 운용도급.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01825844:000` | 2. 입찰공고문(규격가격)_베어링 전식 시험용 데이터 수집 및 인터페이스 모듈 외 1 종.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01826101:000` | 입찰공고문(협상).pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01826771:000` | 입찰공고문(규격가격)_AI 기반 고성능 자율주행 통합제어기.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01826922:000` | 3. 도면.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01827540:000` | 04 수의계약일반조건[제395호, 26.11.06].pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01827848:000` | 5. 단일 규격 사유서 및 구매규격 경쟁 가능 확인서.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01828170:000` | 1. 입찰개요(2027년 손실보상시스템 운영 유지관리 용역).hwp | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01830216:000` | (안내자료) 상생결제 제도 개요 및 활용 방법_계약상대자.pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01830515:000` | 道 공무원 공공기관 사칭 범죄 예방대책 등 유의사항 안내(소상공인， 민간업체 배포용).pdf | `readable_but_source_scan_incomplete` | 읽힘; 원문 검사 미완료 |
| retry | `R26BK01744201:001` | 4.  사업 참고자료(우즈베키스탄).pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01763165:001` | (제안요청서)_'27~'28년 취업 후 학자금 상환 전산시스템 운영 및 유지관리_수정.hwpx | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01763165:001` | (파일명 공란) | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01774133:000` | 3. 공사도면_안산송산 집단에너지 열네트워크 구축사업 열수송관 공사.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01777801:000` | 전자입찰공고(2026.10.19).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01801865:000` | 입찰 공고(2026-0716).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01801940:000` | 입찰 공고(2026-0717).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01807458:000` | ★[용역] 입찰유의서, 계약일반조건, 특수조건, 적격심사 및 협상기준(행안부), 서약서 양식 (11.2.부터).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808941:000` | 5. (재) KOICA 입찰 관련 규정, 표준계약서 등(260725)(변경없음).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815555:000` | 물량내역서 등(2026년 지하철2호선 신림역 등 2개역 환기시스템 개량 전기공사).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815606:000` | 3. 시방서, 도면 등.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815606:000` | 공사계약일반조건.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816461:000` | 03. 26-50 설계도면.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821259:001` | 4. (한국방송광고진흥공사) 물품 구매 특수 조건.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822069:001` | 4. (한국방송광고진흥공사) 물품 구매 특수 조건.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822070:000` | 5.평면도(부분확대포함).pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822551:000` | (공고)규격서 1식_국립청주박물관 디지털문화관.zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01822557:000` | 공고문(2027년 시흥시 대표 누리집(홈페이지) 통합 유지관리)_최종.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823651:000` | 붙임3. 설계도서.zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01824367:000` | [붙임2] 시방서.pdf | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826833:000` | (파일명 공란) | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826833:000` | 1. 제안요청서_방글라데시 AI 혁신기술 전문인력 양성사업_최종.hwp | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826833:000` | 1. 제안요청서_방글라데시 AI 혁신기술 전문인력 양성사업_최종.hwp | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826833:000` | 4. 사업참고자료.zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826833:000` | 표준계약조건(260630).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01830523:000` | 용역계약조건등(20261106).zip | `source_extraction_timeout_deferred` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01744201:001` | 사업 참고자료(우즈베키스탄).pdf | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01744201:001` | 제안요청서(우즈베키스탄) .pdf | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01744201:001` | 투찰내역서(우즈베키스탄).xlsm | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01776256:000` | 입찰참가서식.zip | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01799826:000` | 공고문.zip | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01814802:000` | 제안요청서 등.zip | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815005:000` | 공고파일.zip | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01816525:000` | 전자입찰참가 서식.zip | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821884:000` | 제안요청서.hwpx | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01821884:000` | 협상에 의한 계약 추진 사유.hwp | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01823798:000` | 시방서 등.zip | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01826481:000` | 제안요청서 등.zip | `unknown_archive_member_requires_review` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01791324:000` | R26BK01791324-000_20261027092358_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01791324:000` | R26BK01791324-000_20261027092358_외자공고서_D02.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01793365:000` | R26BK01793365-000_20261029132341_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01793365:000` | R26BK01793365-000_20261029132341_외자공고서_D02.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808384:000` | R26BK01808384-000_20261104103914_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01808384:000` | R26BK01808384-000_20261104103914_외자공고서_D02.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815115:000` | R26BK01815115-000_20261106141759_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815115:000` | R26BK01815115-000_20261106141759_외자공고서_D02.htm | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01815758:000` | 청렴계약이행서약서.xls | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818863:000` | 입찰공고문(2027년 선박 전자증서 발급시스템 유지보수 및 운영).hml | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01818936:000` | 입찰공고문(2027년 수입 공 컨테이너 종합정보관리시스템 위탁운영).hml | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01819057:000` | 입찰재공고문(2026년 항만시설 디지털 플랫폼 구축사업).hml | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |
| retry | `R26BK01828076:000` | 입찰공고문(연근해어업 통합관리시스템 운영 및 유지관리(2027))(채번).hml | `unsupported_format` | 읽기 미완료; 원문 검사 미완료 |

## 원본 진단 기록

- [운영 DB 파일별 실측 로그](https://github.com/suaveforge/monitor/actions/runs/43676515767)
- [별도 OCR 보정기 대상과 현재 스케줄러 상태](https://github.com/suaveforge/monitor/actions/runs/43676518994)

보정기 스냅샷과 독립 실행 중인 3차 판독 큐는 업데이트 시차가 있으므로, 보고서의 두 집계를 단순 합산하지 않습니다.
