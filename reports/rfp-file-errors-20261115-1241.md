# RFP 판독 오류 공고·파일 전체 목록 (2026-11-15 12:41 KST)

서버 123 **운영 DB 읽기 전용 실측**. 2차 원본 다운로드 검증 완료(`download_status=ready`) 상태에서 3차 판독 `retry` **298건**, `scanning` **8건**, 총 **306개 공고**의 각 파일 판독 기록입니다. `scanning`은 진행 중이므로 현재 오류로 확정하지 않습니다. 수집기/다운로더 실패를 합산하지 않았습니다.

- 판독 대기(`pending`) 185건은 이 오류 목록에 포함하지 않습니다.
- 실제 파일 오류 코드와 `readable=true`이지만 `sourceTextScanComplete=false`인 상태를 구분합니다.
- 같은 공고에 복수 파일 문제가 있을 수 있습니다. PDF 대체로 생략한 HWP/HWPX는 문제 파일에서 제외합니다.
- 조회 당시의 기록이므로 재처리 후에는 달라질 수 있습니다.

| 공고번호 | 단계 상태 | 파일명 | 실제 오류 또는 미완료 근거 |
|---|---|---|---|
| `R26BK01820519:000` | `scanning` | [첨부5]청렴계약이행 입찰유의서 등_2026년 통행료징수시스템 예비품(트래들) 구매.hwp | `no_searchable_text` |
| `R26BK01820568:000` | `scanning` | 물품공급 및 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01820568:000` | `scanning` | [제393호,시행2026.11.2]지방자치단체 입찰시 낙찰자 결정기준.hwpx | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01820052:000` | `scanning` | 수의계약체결제한여부확인서_KAIST_소액수의_소기업소상공인.hwp | `no_searchable_text` |
| `R26BK01820507:000` | `scanning` | [공내역서] 광주AI교육원 BF본인증 보완공사.xls | `hwp5txt_failed` |
| `R26BK01820255:000` | `scanning` | 특수조건 안전보건수준평가 등.zip | `file_extract_failure` |
| `R26BK01820422:000` | `scanning` | 입찰참가자격등록신청서.hwp | `no_searchable_text` |
| `R26BK01820422:000` | `scanning` | 청렴계약 이행 서약서.hwp | `no_searchable_text` |
| `R26BK01819730:000` | `scanning` | 규격서및시방서_환풍기.pdf | `file_extract_failure` |
| `R26BK01820250:000` | `scanning` | 규격비교표.hwp | `no_searchable_text` |
| `R26BK01820359:000` | `retry` | 공고문.pdf | `file_extract_failure` |
| `R26BK01820359:000` | `retry` | 첨부1. 규격비교표.hwp | `no_searchable_text` |
| `R26BK01820359:000` | `retry` | 첨부2. 퇴직자 영입(근무) 현황 확인서.hwp | `no_searchable_text` |
| `R26BK01820077:000` | `retry` | 물품공급 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01820077:000` | `retry` | [제393호,시행2026.11.2]지방자치단체 입찰시 낙찰자 결정기준.hwpx | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01820213:000` | `retry` | 구매규격서.pdf | `pdf_ocr_incomplete` |
| `R26BK01819901:000` | `retry` | 1.2026-058입찰공고(액체수소 공급시스템용 극저온 밸브 제작).pdf | `file_extract_failure` |
| `R26BK01820206:000` | `retry` | 2. 물품명세서_펌웨어 알고리즘 시뮬레이션 SW.xls | `hwp5txt_failed` |
| `R26BK01820135:000` | `retry` | 붙임2_사양서_3차원 홀로토모그래피 현미경 시스템_수정.hwp | `no_searchable_text` |
| `R26BK01819599:000` | `retry` | 규격서 등.zip | `file_extract_failure` |
| `R26BK01819527:001` | `retry` | 상세규격서.hwp | `no_searchable_text` |
| `R26BK01819527:001` | `retry` | 물품규격적합확인서.hwp | `no_searchable_text` |
| `R26BK01819974:000` | `retry` | (입찰)제안요청서_2026년 글로벌 OTT 플랫폼 연계형 제작지원(RAkuten Viki)_조련의 여왕_디지털 색보정(DI) 용역 제안요청서.pdf | `file_extract_failure` |
| `R26BK01819500:000` | `retry` | 입찰공고서(재공고) 1부.pdf | `file_extract_failure` |
| `R26BK01819531:000` | `retry` | 산출내역서_공고(1).hwp | `no_searchable_text` |
| `R26BK01819531:000` | `retry` | 제안요청서_공고(1).hwp | `no_searchable_text` |
| `R26BK01819807:000` | `retry` | 입찰참가신청서_TTA(물품).hwp | `no_searchable_text` |
| `R26BK01819716:000` | `retry` | 물품규격적합확인서_소액수의견적입찰용.hwp | `no_searchable_text` |
| `R26BK01819516:000` | `retry` | 입찰공고문.pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01819664:000` | `retry` | (붙임3) 물품규격서_[실험실습기자재(학과신규3차)] 디지털 위상차 현미경 등 3종 구매.pdf | `pdf_ocr_incomplete` |
| `R26BK01819049:000` | `retry` | 3. 규격서.hwp | `no_searchable_text` |
| `R26BK01819272:000` | `retry` | 용역붙임자료(2026).zip | `file_extract_failure` |
| `R26BK01819135:000` | `retry` | 3. 규격서.hwp | `no_searchable_text` |
| `R26BK01819460:000` | `retry` | 3. 규격서[신속동료구조 훈련 물품 및 구조 훈련 장비 구매].hwpx | `no_searchable_text` |
| `R26BK01819460:000` | `retry` | 4. 물품공급.기술지원 협약서[신속동료구조 훈련 물품].pdf | `pdf_ocr_incomplete` |
| `R26BK01818912:000` | `retry` | (긴급)물품구매(제조)입찰공고_통합모니터링 등 설치.pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01818912:000` | `retry` | 첨부파일.zip | `invalid_hwp` |
| `R26BK01819419:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01819419:000` | `retry` | 제안요청서 및 기술원협약서.Zip | `pdf_ocr_incomplete` |
| `R26BK01819031:000` | `retry` | [붙임1] 입찰공고 요약보고(2027년 임산부 관리시스템(에코이몰) 유지관리 및 기능개선 용역.hwp | `no_searchable_text` |
| `R26BK01819031:000` | `retry` | [붙임5] 2026 성과공유제 제도 안내문(입찰공고용).hwp | `hwp5txt_failed` |
| `R26BK01819153:000` | `retry` | 3. 규격서.hwp | `no_searchable_text` |
| `R26BK01818936:000` | `retry` | 입찰공고문(2027년 수입 공 컨테이너 종합정보관리시스템 위탁운영).hml | `unsupported_format` |
| `R26BK01818568:000` | `retry` | 3-1. 기술지원협약서(두산 디지털이노베이션BU).pdf | `pdf_ocr_incomplete` |
| `R26BK01818568:000` | `retry` | 3-2. 기술지원협약서(이지트래픽).pdf | `pdf_ocr_incomplete` |
| `R26BK01818688:000` | `retry` | 물품사양서.hwp | `no_searchable_text` |
| `R26BK01818683:000` | `retry` | 2.용도설명서_구조해석 소프트웨어 유지 및 지원서비스.hwp | `no_searchable_text` |
| `R26BK01818683:000` | `retry` | 3.물품시방서_구조해석 소프트웨어 유지 및 지원서비스.hwp | `no_searchable_text` |
| `R26BK01818772:000` | `retry` | 물품사양서.hwp | `no_searchable_text` |
| `R26BK01818805:000` | `retry` | 03 긴급입찰사유서(2027년 공간정보시스템 통합 유지관리 용역).pdf | `pdf_ocr_incomplete` |
| `R26BK01818805:000` | `retry` | 04 기술지원협약서(브이앤지).pdf | `pdf_ocr_incomplete` |
| `R26BK01818651:000` | `retry` | 입찰공고문(규격가격)_초음파 검사 AI 학습 및 추론용 엣지 컴퓨터.pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01818498:000` | `retry` | 1. 입찰공고문(규격가격).pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01818863:000` | `retry` | 입찰공고문(2027년 선박 전자증서 발급시스템 유지보수 및 운영).hml | `unsupported_format` |
| `R26BK01818863:000` | `retry` | 입찰공고문(2027년 선박 전자증서 발급시스템 유지보수 및 운영).pdf | `file_extract_failure` |
| `R26BK01818127:000` | `retry` | 공 내역서_엑스포과학공원 노후 PAD S_W 교체공사.xls | `hwp5txt_failed` |
| `R26BK01817719:000` | `retry` | 2-1.과업내용서 사전공개대비 비교표.hwp | `no_searchable_text` |
| `R26BK01817719:000` | `retry` | 4.제안서 접수조서 양식.hwp | `no_searchable_text` |
| `R26BK01818426:000` | `retry` | 26-보라매-062. 공통규격서_신경내시경시스템.hwp | `no_searchable_text` |
| `R26BK01818426:000` | `retry` | 공고문_2026년 서울특별시 의료장비 통합구매 2차 재공고(서울특별시 보라매병원, 신경내시경시스템).pdf | `file_extract_failure` |
| `R26BK01818179:000` | `retry` | 제출 서류_탕 조리 연구 로봇 시스템.hwp | `hwp5txt_failed` |
| `R26BK01818312:000` | `retry` | 제안요청서 등.zip | `pdf_ocr_incomplete` |
| `R26BK01817675:000` | `retry` | 입찰서.hwp | `no_searchable_text` |
| `R26BK01818041:000` | `retry` | 입찰참가신청서(용역, 공사).hwp | `no_searchable_text` |
| `R26BK01817757:000` | `retry` | 피지컬AI 사물인터넷 로봇 교육용 실습장치_오픈개방형_기자재규격서.hwp | `no_searchable_text` |
| `R26BK01817760:001` | `retry` | 2026년 (국비) 교육·연구용 기자재 SEM-EDS 시스템(중고)_납품특수조건.hwp | `no_searchable_text` |
| `R26BK01817760:001` | `retry` | 2026년 (국비) 교육·연구용 기자재 SEM-EDS 시스템(중고)_물품내역서.hwp | `no_searchable_text` |
| `R26BK01817748:000` | `retry` | 3. 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01817639:000` | `retry` | 구매의뢰수량내역서_CTTS.hwp | `hwp5txt_failed` |
| `R26BK01817893:000` | `retry` | 4. 물품내역서 및 규격서.pdf | `pdf_ocr_incomplete` |
| `R26BK01816944:000` | `retry` | 제안요청서 등.zip | `pdf_ocr_incomplete` |
| `R26BK01817661:000` | `retry` | 2027학년도 봉양중,경북소프트웨어마이스터고 교복(동,하복) 디자인 사양서.xls | `hwp5txt_failed` |
| `R26BK01817589:000` | `retry` | 1. 긴급발주요청서_2024년 천안시 거점형 스마트시티 조성사업-헬스케어 데이터 실증 및 수집.hwp | `no_searchable_text` |
| `R26BK01817386:000` | `retry` | 물품공급 기술지원협약서(2027년 CCTV통합관제시스템).pdf | `pdf_ocr_incomplete` |
| `R26BK01817002:000` | `retry` | 3. 규격서(3차원 적층 제조시스템).hwp | `no_searchable_text` |
| `R26BK01817569:000` | `retry` | 1. 입찰공고문(규격가격).pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01817385:000` | `retry` | 물품공급·기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01816714:000` | `retry` | 1. 물품 구매 입찰 공고문_3차원 형상 측정시스템.pdf | `file_extract_failure` |
| `R26BK01816714:000` | `retry` | 3. 규격서(3차원 형상 측정시스템).hwp | `no_searchable_text` |
| `R26BK01816569:000` | `retry` | 시방서(장마 동정마을 하수도 증설사업 수밀시험 및 CCTV조사 용역).pdf | `pdf_ocr_incomplete` |
| `R26BK01816523:000` | `retry` | 물품공급 및 기술지원협약서(이노뎁).pdf | `pdf_ocr_incomplete` |
| `R26BK01816523:000` | `retry` | 물품공급 및 기술지원협약서(후지쯔).pdf | `pdf_ocr_incomplete` |
| `R26BK01816681:000` | `retry` | 2. 입찰공고문(규격가격)_OHT 픽업용 AI 모션제어 시스템.pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01816039:000` | `retry` | (물품규격서) 리플로우 오븐 시스템.hwp | `no_searchable_text` |
| `R26BK01816649:000` | `retry` | 첨부1. 규격비교표.hwp | `no_searchable_text` |
| `R26BK01816649:000` | `retry` | 첨부2. 퇴직자 영입(근무) 현황 확인서.hwp | `no_searchable_text` |
| `R26BK01816599:000` | `retry` | 3. 규격서(에너지신산업 제조공정 협동로봇 시스템).hwp | `no_searchable_text` |
| `R26BK01813549:000` | `retry` | 과업심의결과서.PNG | `ocr_deferred_to_repair` |
| `R26BK01813549:000` | `retry` | 붙임10. 소프트웨어사업 영향평가 결과서_업무망 DNS시스템외 1종 유지보수_2027년.pdf | `pdf_ocr_incomplete` |
| `R26BK01815555:000` | `retry` | 물량내역서 등(2026년 지하철2호선 신림역 등 2개역 환기시스템 개량 전기공사).zip | `source_extraction_timeout_deferred` |
| `R26BK01815555:000` | `retry` | 입찰유의서, 계약일반조건 등(26.11.2.).zip | `invalid_hwp` |
| `R26BK01816461:000` | `retry` | 03. 26-50 설계도면.pdf | `source_extraction_timeout_deferred` |
| `R26BK01816525:000` | `retry` | 전자입찰참가 서식.zip | `unknown_archive_member_requires_review` |
| `R26BK01815766:000` | `retry` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01815827:000` | `retry` | 2.용도설명서_광학식 비접촉 3차원 형상 측정 시스템 구매.hwp | `no_searchable_text` |
| `R26BK01815827:000` | `retry` | 3.제품사양서_광학식 비접촉 3차원 형상 측정 시스템 구매.hwp | `no_searchable_text` |
| `R26BK01815606:000` | `retry` | 3. 시방서, 도면 등.pdf | `source_extraction_timeout_deferred` |
| `R26BK01815606:000` | `retry` | 공사계약일반조건.pdf | `source_extraction_timeout_deferred` |
| `R26BK01815972:000` | `retry` | 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01815115:000` | `retry` | R26BK01815115-000_20261106141759_외자공고서_D02.htm | `unsupported_format` |
| `R26BK01815115:000` | `retry` | R26BK01815115-000_20261106141759_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` |
| `R26BK01815023:000` | `retry` | 5) 공공기관 사칭 범죄 주의 안내문.pdf | `pdf_ocr_incomplete` |
| `R26BK01815237:000` | `retry` | 3. 치과 구강스캐너 외 13종 규격서.zip | `pdf_ocr_incomplete` |
| `R26BK01815420:000` | `retry` | 물품공급 및 기술지원 협약서(12사 14종).pdf | `pdf_ocr_incomplete` |
| `R26BK01815447:000` | `retry` | 성도고등학교 AI융합형교육실구축 인테리어공사 공내역서.xls | `hwp5txt_failed` |
| `R26BK01813292:000` | `retry` | 0.한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` |
| `R26BK01813292:000` | `retry` | 6.수의계약 체결 제한 여부 확인서.hwp | `no_searchable_text` |
| `R26BK01814888:000` | `retry` | [붙임4-4] 소프트웨어사업 영향 평가결과서(2027년 노후위험 시설물 안전관리 시스템 통합유지관리).pdf | `pdf_ocr_incomplete` |
| `R26BK01814888:000` | `retry` | [붙임4-5] 물품공급 및 기술지원 협약서(2027년 노후위험 시설물 안전관리 시스템 통합유지관리).pdf | `pdf_ocr_incomplete` |
| `R26BK01813495:000` | `retry` | 과업심의결과서.PNG | `ocr_deferred_to_repair` |
| `R26BK01813495:000` | `retry` | 붙임5. 제안요청서_DHCP시스템외 1종 유지보수_2027년.hwp | `hwp5txt_failed` |
| `R26BK01813495:000` | `retry` | 붙임10. 소프트웨어사업 영향평가 결과서_DHCP시스템외 1종 유지보수_2027년.pdf | `pdf_ocr_incomplete` |
| `R26BK01813330:000` | `retry` | 2. 규격서.hwp | `no_searchable_text` |
| `R26BK01814222:000` | `retry` | 2. 물품명세서_연구개발용 워크스테이션.xls | `hwp5txt_failed` |
| `R26BK01814222:000` | `retry` | 3. 세부명세서_연구개발용 워크스테이션.hwp | `no_searchable_text` |
| `R26BK01814959:000` | `retry` | 정기구입 목록_26년 4분기.xlsx | `large_xml_section` |
| `R26BK01814365:000` | `retry` | 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01814204:000` | `retry` | 긴급 발주요청 사유서(날인).pdf | `pdf_ocr_incomplete` |
| `R26BK01814802:000` | `retry` | 제안요청서 등.zip | `unknown_archive_member_requires_review` |
| `R26BK01814436:000` | `retry` | 2026년도 통계 소프트웨어 규격서(SPSS, SAS).hwp | `no_searchable_text` |
| `R26BK01811518:000` | `retry` | 입찰참가신청서(2단계 경쟁 등).hwp | `no_searchable_text` |
| `R26BK01811976:000` | `retry` | 붙임4 영남이공대학교 산학협력단 사업자등록증.pdf | `pdf_ocr_incomplete` |
| `R26BK01813104:000` | `retry` | 물품공급 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01811464:000` | `retry` | 3. 기술지원협약서(27년 유지관리).pdf | `pdf_ocr_incomplete` |
| `R26BK01812695:000` | `retry` | 시방서 등.zip | `pdf_ocr_incomplete` |
| `R26BK01811457:000` | `retry` | 0.한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` |
| `R26BK01811457:000` | `retry` | 6.수의계약 체결 제한 여부 확인서.hwp | `no_searchable_text` |
| `R26BK01813136:000` | `retry` | 2. 물품구매규격서_광합성측정장치.hwp | `no_searchable_text` |
| `R26BK01812609:000` | `retry` | 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01812274:000` | `retry` | 0. 한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` |
| `R26BK01812274:000` | `retry` | 1. 용역계약일반조건.hwp | `invalid_hwp` |
| `R26BK01812274:000` | `retry` | 2. 용역입찰유의서.hwp | `invalid_hwp` |
| `R26BK01812274:000` | `retry` | 3.국가종합전자조달시스템 전자입찰특별유의서(조달청고시)(제2024-23호)(20250106).hwp | `invalid_hwp` |
| `R26BK01812274:000` | `retry` | 10.입찰참가신청서(양식).hwp | `no_searchable_text` |
| `R26BK01812018:000` | `retry` | 붙임4 영남이공대학교 산학협력단 사업자등록증.pdf | `pdf_ocr_incomplete` |
| `R26BK01811416:000` | `retry` | 구매규격서_선박 블록 조립공정 AI 데이터 고성능 스토리지 시스템_RF.hwp | `pdf_ocr_incomplete` |
| `R26BK01811416:000` | `retry` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01811416:000` | `retry` | 견적서1_AI 데이터 고성능 스토리지 시스템 견적서_HITACHI v2.pdf | `pdf_ocr_incomplete` |
| `R26BK01811890:000` | `retry` | [입찰공고]AAU LMS 용 AI챗봇 도입 사업_재공고.pdf | `file_extract_failure` |
| `R26BK01811551:000` | `retry` | 3. 긴급입찰 사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01809521:000` | `retry` | 2. 용도설명서.hwp | `no_searchable_text` |
| `R26BK01811210:001` | `retry` | 계약조건(경쟁).zip | `invalid_hwp` |
| `R26BK01807194:000` | `retry` | 8_단일규격사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01809545:000` | `retry` | 입찰공고문(2027년 종묘 종합경비시스템 유지보수 용역) 재공고.pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01808803:000` | `retry` | 3. 국문규격서_261014.hwp | `pdf_ocr_incomplete` |
| `R26BK01808803:000` | `retry` | 긴급입찰사유서-직인날인본.pdf | `pdf_ocr_incomplete` |
| `R26BK01808803:000` | `retry` | 부산대 수소선박센터 센서성능검사 견적 261016.pdf | `pdf_ocr_incomplete` |
| `R26BK01808803:000` | `retry` | 2-1. 공사원가계산서_저장탱크-수정.xlsx | `pdf_ocr_incomplete` |
| `R26BK01810946:001` | `retry` | 내자 2026-254 의료 AI 연구용 고성능 컴퓨팅 서버 - 용도설명서 및 상세규격서.hwp | `no_searchable_text` |
| `R26BK01810887:000` | `retry` | 서울물재생시설공단 공고 제2026-04-063호.pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01809385:000` | `retry` | 물품공급기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01808698:000` | `retry` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01809480:000` | `retry` | 1. 입찰 제안요청서(2027년도 공영주차장·차고지 주차관제시스템 통합유.hwp | `no_searchable_text` |
| `R26BK01808384:000` | `retry` | 제안요청서_한국자동차연구원.hwpx | `hwp5txt_failed` |
| `R26BK01808384:000` | `retry` | R26BK01808384-000_20261104103914_외자공고서_D02.htm | `unsupported_format` |
| `R26BK01808384:000` | `retry` | R26BK01808384-000_20261104103914_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` |
| `R26BK01807665:000` | `retry` | 2. 2027년 Allbaro 및 폐기물처분부담금 협업콜센터 위탁운영 과업내용서_회신2.hwpx | `pdf_ocr_incomplete` |
| `R26BK01807665:000` | `retry` | 4. 용역계약 추가특수조건(공공부문 도급 노동자 보호 조건)_수정회신.hwpx | `pdf_ocr_incomplete` |
| `R26BK01807665:000` | `retry` | 5. 개인정보처리위탁 특수조건.hwp | `pdf_ocr_incomplete` |
| `R26BK01807665:000` | `retry` | 6. 긴급입찰 사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01809321:000` | `retry` | 공고서_R26BK01809321(국가,sw,중기간,수요_경찰청 중앙경찰학교).pdf | `file_extract_failure` |
| `R26BK01809397:000` | `retry` | [주식회사 루미너스] 태풍_VFX용역_(재공고).hwp | `hwp5txt_failed` |
| `R26BK01809397:000` | `retry` | [주식회사 루미너스] 태풍_VFX용역_제안요청서(재공고).hwp | `hwp5txt_failed` |
| `R26BK01809317:000` | `retry` | 2027년 공간정보시스템 통합유지보수 용역(기술지원협약서).pdf | `pdf_ocr_incomplete` |
| `R26BK01808105:000` | `retry` | 2. 용도설명서_SW 구성요소 분석 솔루션 및 SW 정적분석 자동화 솔루션.hwp | `no_searchable_text` |
| `R26BK01808105:000` | `retry` | 3. 물품시방서_SW 구성요소 분석 솔루션 및 SW 정적분석 자동화 솔루션.hwp | `no_searchable_text` |
| `R26BK01807458:000` | `retry` | ★[용역] 입찰유의서, 계약일반조건, 특수조건, 적격심사 및 협상기준(행안부), 서약서 양식 (11.2.부터).zip | `source_extraction_timeout_deferred` |
| `R26BK01807458:000` | `retry` | 3.기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01807679:000` | `retry` | 입찰공고문_NIA2026-128호(재공고_수정).pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01806913:000` | `retry` | 붙임. 과업내용서.hwp | `hwp5txt_failed` |
| `R26BK01806929:000` | `retry` | 2. 물품구매규격서_액체크로마토그래피 시스템.hwp | `no_searchable_text` |
| `R26BK01807007:000` | `retry` | 2. 물품구매규격서_이미지분석시스템.hwp | `no_searchable_text` |
| `R26BK01807168:000` | `retry` | 2. 물품구매규격서_ 소동물 초음파 이미징.hwp | `no_searchable_text` |
| `R26BK01806666:000` | `retry` | 1. 입찰공고문.pdf | `file_extract_failure` |
| `R26BK01806666:000` | `retry` | 3. 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01806397:000` | `retry` | 2. 물품명세서_임무성능 분석용 전산장비 등.xls | `hwp5txt_failed` |
| `R26BK01806397:000` | `retry` | 3. 세부 규격(명세)서_임무성능 분석용 전산장비 등.hwp | `no_searchable_text` |
| `R26BK01806387:000` | `retry` | 2027년 ERP시스템 유지보수 기술지원 협약서(직인날인).pdf | `pdf_ocr_incomplete` |
| `R26BK01805597:000` | `retry` | 계약예규 및 참고서식(공고시 붙임서류).zip | `invalid_hwp` |
| `R26BK01806277:000` | `retry` | 3. 과업지시서_2026학년도 글로벌 보건의료 시스템 현장실습 프로그램 운영 용역.hwpx | `pdf_ocr_incomplete` |
| `R26BK01806277:000` | `retry` | 5. 긴급입찰요청사유서_2026 글로벌 보건의료 시스템 현장실습 프로그램 운영 용역.pdf | `pdf_ocr_incomplete` |
| `R26BK01806319:000` | `retry` | 2. 규격서.hwp | `no_searchable_text` |
| `R26BK01806319:000` | `retry` | 3. 평가표.hwp | `no_searchable_text` |
| `R26BK01805847:000` | `retry` | 03.품목명세서.hwp | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01804761:000` | `retry` | 4-3. 수의계약사유서(유지관리또는커스터마이징)_.hwpx | `no_searchable_text` |
| `R26BK01806192:000` | `retry` | 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01804698:000` | `retry` | 2027년 성남시 공간정보시스템 통합유지관리 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01805690:000` | `retry` | 붙임2. 규격서.pdf | `file_extract_failure` |
| `R26BK01805351:000` | `retry` | 입찰참가신청서(용역, 공사).hwp | `no_searchable_text` |
| `R26BK01800740:000` | `retry` | 3. 물품공급및기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01804474:000` | `retry` | 2027년 CCTV 통합관제시스템 통합 유지보수 용역 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01804894:000` | `retry` | 긴급발주사유서_구축.pdf | `pdf_ocr_incomplete` |
| `R26BK01804092:000` | `retry` | 붙임10_2027년 물품공급및기술지원 협약서(2종).pdf | `pdf_ocr_incomplete` |
| `R26BK01804092:000` | `retry` | 서울특별시 용역계약 특수조건(서울특별시예규)(제746호)(20261001) (1).hwp | `invalid_hwp` |
| `R26BK01802945:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01800658:000` | `retry` | 4. 긴급공고 사유서.hwp | `no_searchable_text` |
| `R26BK01801815:000` | `retry` | 붙임2. 구매규격서(SAR모니터링).hwp | `no_searchable_text` |
| `R26BK01801800:000` | `retry` | 26-보라매-118. 공통규격서_4K.ICG복강경시스템.hwp | `no_searchable_text` |
| `R26BK01802833:002` | `retry` | 내자 2026-236 - 라만 분광기 측정 시스템 - 상세규격서.hwp | `no_searchable_text` |
| `R26BK01802833:002` | `retry` | 내자 2026-236 - 라만 분광기 측정 시스템 - 용도설명서.hwp | `no_searchable_text` |
| `R26BK01799724:000` | `retry` | 6. 소프트웨어사업 영향평가 결과서-2027년 K-AMI GIS 및 Platform 시스템 유지보수 용역.pdf | `pdf_ocr_incomplete` |
| `R26BK01798615:000` | `retry` | 26-보라매-120. 공통규격서_슬라이드스캐너(디지털병리솔루션 포함).hwp | `no_searchable_text` |
| `R26BK01799524:000` | `retry` | 10. 소프트웨어사업 영향평가 결과서-2027년 IMIS 및 SMMS 시스템 유지보수 용역.pdf | `pdf_ocr_incomplete` |
| `R26BK01798829:000` | `retry` | R26BK01798829-000 [붙임] 제안요청서 등.zip | `file_extract_failure` |
| `R26BK01797963:000` | `retry` | 사업 계획서.hwpx | `pdf_ocr_incomplete` |
| `R26BK01796087:000` | `retry` | 4. 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01799200:000` | `retry` | 규격서 등.zip | `pdf_ocr_incomplete` |
| `R26BK01794908:001` | `retry` | 10. 소프트웨어사업 영향평가 결과서_27년 MDMS용 GIS 및 GIS DB 유지보수.pdf | `pdf_ocr_incomplete` |
| `R26BK01795767:000` | `retry` | 3. (엔진) 국문규격서.hwp | `pdf_ocr_incomplete` |
| `R26BK01795767:000` | `retry` | 4. 하이브리드 추진시스템용 수소혼소엔진 및 전기추진 통합 모듈 견적서_260907.pdf | `pdf_ocr_incomplete` |
| `R26BK01795767:000` | `retry` | 5. (엔진)긴급입찰사유서-직인날인본.pdf | `pdf_ocr_incomplete` |
| `R26BK01794289:001` | `retry` | (설계내역서) 정보통신공사 내역서 (2공구)_공내역.xlsx | `large_xml_section` |
| `R26BK01792503:000` | `retry` | 1.용도설명서(DC파라미터측정시스템).hwpx | `no_searchable_text` |
| `R26BK01790885:000` | `retry` | 04_입찰 참가 신청서 양식.hwp | `no_searchable_text` |
| `R26BK01794083:000` | `retry` | 26-보라매-144. 공통규격서_액체질소저장시스템.hwp | `no_searchable_text` |
| `R26BK01791324:000` | `retry` | R26BK01791324-000_20261027092358_외자공고서_D02.htm | `unsupported_format` |
| `R26BK01791324:000` | `retry` | R26BK01791324-000_20261027092358_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` |
| `R26BK01793369:001` | `retry` | (양식) 제안서접수조서_자산경영시스템(ISO55001) 고도화 및 갱신용역.hwp | `no_searchable_text` |
| `R26BK01793365:000` | `retry` | R26BK01793365-000_20261029132341_외자공고서_D02.htm | `unsupported_format` |
| `R26BK01793365:000` | `retry` | R26BK01793365-000_20261029132341_SUMMARY_OF_BIDDING_D03.htm | `unsupported_format` |
| `R26BK01793424:000` | `retry` | 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01793416:003` | `retry` | 2. (설계내역서) 정보통신공사 내역서(1공구)_공내역v.xlsm | `large_xml_section` |
| `R26BK01791320:000` | `retry` | 공고문_ERP시스템 유지관리 용역.pdf | `file_extract_failure` |
| `R26BK01801865:000` | `retry` | 입찰 공고(2026-0716).zip | `source_extraction_timeout_deferred` |
| `R26BK01779951:000` | `retry` | 입찰 재공고문 일체.zip | `pdf_ocr_incomplete` |
| `R26BK01812929:000` | `retry` | 입찰 공고(2026-0733).zip | `file_extract_failure` |
| `R26BK01801940:000` | `retry` | 입찰 공고(2026-0717).zip | `source_extraction_timeout_deferred` |
| `R26BK01791199:000` | `retry` | 붙임2. 2026년 한국학술지인용색인(KCI) DB 구축 사업 긴급사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01790119:000` | `retry` | 3_2_[시방서] 자재시방서.hwp | `no_searchable_text` |
| `R26BK01791237:000` | `retry` | 26-서울-102. 공통규격서_4K복강경시스템.hwp | `no_searchable_text` |
| `R26BK01789669:000` | `retry` | 3_긴급공고 요청 사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01790085:000` | `retry` | 입찰공고문_전차선(2공구)v.pdf | `file_extract_failure` |
| `R26BK01790085:000` | `retry` | 3_2_[시방서] 자재시방서.hwp | `no_searchable_text` |
| `R26BK01787270:000` | `retry` | 물품공급 또는 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01789856:000` | `retry` | 1_(내역서) 1공구 설계내역서(전차선)_공내역.xlsx | `large_xml_section` |
| `R26BK01789856:000` | `retry` | 3_2_[시방서] 자재시방서.hwp | `no_searchable_text` |
| `R26BK01827991:000` | `retry` | 0.한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` |
| `R26BK01827991:000` | `retry` | 1.(계약예규) 용역계약일반조건(재정경제부계약예규)(제149호)(20260430).hwp | `invalid_hwp` |
| `R26BK01827991:000` | `retry` | 2.(계약예규) 용역입찰유의서(기획재정부계약예규)(제820호)(20251231).hwp | `invalid_hwp` |
| `R26BK01827991:000` | `retry` | 3.국가종합전자조달시스템 전자입찰특별유의서(조달청고시)(제2024-23호)(20250106).hwp | `invalid_hwp` |
| `R26BK01819057:000` | `retry` | 입찰재공고문(2026년 항만시설 디지털 플랫폼 구축사업).hml | `unsupported_format` |
| `R26BK01822557:000` | `retry` | 공고문(2027년 시흥시 대표 누리집(홈페이지) 통합 유지관리)_최종.pdf | `source_extraction_timeout_deferred` |
| `R26BK01786249:002` | `retry` | 구매규격서 외자KIMS 2026-3-2호.hwp | `no_searchable_text` |
| `R26BK01822734:000` | `retry` | 물품공급·기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01828076:000` | `retry` | 입찰공고문(연근해어업 통합관리시스템 운영 및 유지관리(2027))(채번).hml | `unsupported_format` |
| `R26BK01777477:000` | `retry` | 긴급입찰사유서(국회 통합디지털센터).pdf | `pdf_ocr_incomplete` |
| `R26BK01822991:000` | `retry` | 4. 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01824715:000` | `retry` | 청렴계약 이행서약서 및 이행각서_양식.hwp | `no_searchable_text` |
| `R26BK01821923:000` | `retry` | 기술지원협약서(2027년 경상남도 홈페이지 통합유지보수).pdf | `pdf_ocr_incomplete` |
| `R26BK01821858:000` | `retry` | 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01821858:000` | `retry` | 긴급입찰 사유서(2027년 통합관제시스템 및 현장CCTV 유지보수 용역).hwpx | `pdf_ocr_incomplete` |
| `R26BK01822388:000` | `retry` | [긴급입찰 사유서] 2027년도 도로기상정보시스템 유지관리 및 기능개선 사업.pdf | `pdf_ocr_incomplete` |
| `R26BK01822388:000` | `retry` | 통합발주 사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01822238:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01816872:000` | `retry` | 가격입찰서,_입찰보증금지급각서(서식).hwp | `no_searchable_text` |
| `R26BK01822405:001` | `retry` | 긴급 입찰 사유서(2027년 전산장비(PC, 네트워크 및 전화장비) 유지관리).pdf | `pdf_ocr_incomplete` |
| `R26BK01821503:000` | `retry` | 붙임4. 물품공급 및 기술지원협약서(2027년 정보통신 통합 유지보수 용역).zip | `pdf_ocr_incomplete` |
| `R26BK01816865:000` | `retry` | 물품공급 및 기술지원 협약서 - 2027년 하남시 버스정보시스템(BIS) 유지보수 용역.pdf | `pdf_ocr_incomplete` |
| `R26BK01814658:000` | `retry` | 261016 평택(스도) 기술지원협약서(10부).pdf | `pdf_ocr_incomplete` |
| `R26BK01816535:000` | `retry` | 붙임5. 물품공급 및 기술지원협약서(39개 업체 취합본).pdf | `pdf_ocr_incomplete` |
| `R26BK01816614:000` | `retry` | 입찰보증금 지급각서.hwp | `no_searchable_text` |
| `R26BK01814268:000` | `retry` | 물품공급 및 기술지원 협약서(2027년 스마트도시 솔루션 통합유지보수).pdf | `pdf_ocr_incomplete` |
| `R26BK01816419:000` | `retry` | 별첨3_소프트웨어사업영향평가별과서.pdf | `pdf_ocr_incomplete` |
| `R26BK01816419:000` | `retry` | 별첨1_기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01816664:000` | `retry` | 2027년 정읍시 통합관제센터 및 현장 CCTV 유지보수 용역 과업지시서.hwpx | `pdf_ocr_incomplete` |
| `R26BK01815758:000` | `retry` | 청렴계약이행서약서.xls | `unsupported_format` |
| `R26BK01815699:000` | `retry` | 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01813497:000` | `retry` | 제안서 평가표_경남 제조 특화 AI 대전환 데이터 플랫폼 구축.hwp | `no_searchable_text` |
| `R26BK01814390:000` | `retry` | 긴급입찰 사유서.hwpx | `pdf_ocr_incomplete` |
| `R26BK01812217:000` | `retry` | 1. 용역계약일반조건.hwp | `invalid_hwp` |
| `R26BK01812217:000` | `retry` | 2. 용역입찰유의서.hwp | `invalid_hwp` |
| `R26BK01812217:000` | `retry` | 3.국가종합전자조달시스템 전자입찰특별유의서(조달청고시)(제2024-23호)(20250106).hwp | `invalid_hwp` |
| `R26BK01812217:000` | `retry` | 10.입찰참가신청서(양식).hwp | `no_searchable_text` |
| `R26BK01812217:000` | `retry` | 0. 한국과학기술정보연구원 직원 사칭 사기 주의 안내.pdf | `pdf_ocr_incomplete` |
| `R26BK01809762:000` | `retry` | 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01812957:000` | `retry` | 물품공급 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01812910:000` | `retry` | 긴급입찰사유서(2027년 농림축산검역 정보자원 통합유지관리 사업).pdf | `pdf_ocr_incomplete` |
| `R26BK01812910:000` | `retry` | 국제입찰(제외) 사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01806183:000` | `retry` | (붙임) 물품공급 및 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01813528:000` | `retry` | 8. 긴급입찰사유서(2027년 공단 정보시스템 통합 유지관리 및 운영).hwp | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01808816:000` | `retry` | 5. 입찰유의서,계약일반조건 등.zip | `invalid_hwp` |
| `R26BK01808308:000` | `retry` | 기술지원협약서 통합본.pdf | `pdf_ocr_incomplete` |
| `R26BK01805314:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01806796:000` | `retry` | 3. 유지보수 대상장비 목록 및 정보통신망 구성도.pdf | `pdf_ocr_incomplete` |
| `R26BK01763537:000` | `retry` | 8. 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01810900:000` | `retry` | (붙임2) 청렴계약이행서약서.hwp | `no_searchable_text` |
| `R26BK01810900:000` | `retry` | (붙임3) 안전·보건조치 준수 서약서.hwp | `no_searchable_text` |
| `R26BK01767174:000` | `retry` | 5. 투찰내역서.xlsm | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01767174:000` | `retry` | KOICA 입찰 관련 규정 및 지침(260922).zip | `pdf_ocr_incomplete` |
| `R26BK01806571:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01805360:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01782482:000` | `retry` | 9. 소프트웨어사업관련 법령준수 자체점검표_CTI시스템 상용SW.hwp | `no_searchable_text` |
| `R26BK01782482:000` | `retry` | 10. 소프트웨어사업 영향평가 검토결과서(CTI시스템 상용SW 유지보수).pdf | `pdf_ocr_incomplete` |
| `R26BK01744201:001` | `retry` | 4.  사업 참고자료(우즈베키스탄).pdf | `source_extraction_timeout_deferred` |
| `R26BK01744201:001` | `retry` | 제안요청서(우즈베키스탄) .pdf | `unknown_archive_member_requires_review` |
| `R26BK01744201:001` | `retry` | 투찰내역서(우즈베키스탄).xlsm | `unknown_archive_member_requires_review` |
| `R26BK01744201:001` | `retry` | 사업 참고자료(우즈베키스탄).pdf | `unknown_archive_member_requires_review` |
| `R26BK01806163:000` | `retry` | 3. 용역 계약 시 나라장터 필첨 서류.zip | `invalid_hwp` |
| `R26BK01771582:000` | `retry` | 붙임3. 사전공개내용 주요 변경사항.hwp | `no_searchable_text` |
| `R26BK01771582:000` | `retry` | 붙임4. 소개자료 및 운영현황.zip | `pdf_ocr_incomplete` |
| `R26BK01804417:000` | `retry` | (기술지원 협약서)2027년 김포시 정보통신인프라 통합 유지관리 용역.pdf | `pdf_ocr_incomplete` |
| `R26BK01763579:000` | `retry` | 8. 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01761331:000` | `retry` | (붙임2) 청렴계약이행서약서.hwp | `no_searchable_text` |
| `R26BK01761331:000` | `retry` | (붙임3) 안전·보건조치 준수 서약서.hwp | `no_searchable_text` |
| `R26BK01782260:000` | `retry` | 청렴계약 및 공정거래 이행각서.hwp | `no_searchable_text` |
| `R26BK01759044:000` | `retry` | 통합의료정보시스템 고도화 사업 입찰서류.zip | `invalid_hwp` |
| `R26BK01764812:000` | `retry` | 04_입찰 참가 신청서 양식.hwp | `no_searchable_text` |
| `R26BK01763450:000` | `retry` | 기술지원협약서.zip | `pdf_ocr_incomplete` |
| `R26BK01764148:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwp | `invalid_hwp` |
| `R26BK01782476:000` | `retry` | 9. 소프트웨어사업관련 법령준수 자체점검표_IP교환기 상용SW.hwp | `no_searchable_text` |
| `R26BK01782476:000` | `retry` | 10. 소프트웨어사업 영향평가 검토결과서(IP교환기 상용SW 유지보수).pdf | `pdf_ocr_incomplete` |
| `R26BK01769051:000` | `retry` | 입찰업체 서약서 및 공동책임 확인서(서식).hwp | `no_searchable_text` |
| `R26BK01782057:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01772242:000` | `retry` | 3. 일반조건.hwp | `invalid_hwp` |
| `R26BK01772242:000` | `retry` | 8. 입찰참가신청서(서식).hwp | `no_searchable_text` |
| `R26BK01750936:001` | `retry` | 제안요청서.hwp | `hwp5txt_failed` |
| `R26BK01780184:000` | `retry` | [붙임1] 입찰공고 요약보고(2027년 농식품바우처 통합플랫폼 운영 및 유지관리).hwp | `no_searchable_text` |
| `R26BK01766710:000` | `retry` | 긴급입찰 사유서(조달의뢰).pdf | `pdf_ocr_incomplete` |
| `R26BK01788116:000` | `retry` | 4. 전자입찰특별유의서.hwp | `invalid_hwp` |
| `R26BK01789296:000` | `retry` | 11. 소프트웨어사업 영향평가 결과서.pdf | `no_searchable_text` |
| `R26BK01789296:000` | `retry` | 12. 과업심의 결과서.pdf | `no_searchable_text` |
| `R26BK01789296:000` | `retry` | 기술지원협약서.zip | `pdf_ocr_incomplete` |
| `R26BK01792436:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01778153:000` | `retry` | 3. 원가계산용역 보고서.pdf | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01789246:000` | `retry` | 11. 소프트웨어사업 영향평가 결과서.pdf | `no_searchable_text` |
| `R26BK01789246:000` | `retry` | 12. 과업심의 결과서.pdf | `no_searchable_text` |
| `R26BK01789246:000` | `retry` | 기술지원협약서.zip | `pdf_ocr_incomplete` |
| `R26BK01786079:000` | `retry` | 입찰공고문_홈쇼핑 모니터링 시스템.pdf | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01786079:000` | `retry` | 상생결제제도 안내 자료.zip | 원문 조건 스캔 미완료 (`sourceTextScanComplete=false`) |
| `R26BK01771462:001` | `retry` | 취소공고서_국가_공동_개발_단독_수요기관평가.hwpx | `no_searchable_text` |
| `R26BK01771462:001` | `retry` | 긴급입찰사유.pdf | `pdf_ocr_incomplete` |
| `R26BK01787906:000` | `retry` | 10. 소프트웨어사업 영향평가 검토결과서(RDBMS(ORACLE) 상용SW 유지보수).pdf | `pdf_ocr_incomplete` |
| `R26BK01787906:000` | `retry` | 과업심의결과서.png | `ocr_deferred_to_repair` |
| `R26BK01787906:000` | `retry` | 9. 소프트웨어사업관련 법령준수 자체점검표_RDBMS(ORACLE)상용SW.hwp | `no_searchable_text` |
| `R26BK01786136:000` | `retry` | 04_입찰 참가 신청서 양식.hwp | `no_searchable_text` |
| `R26BK01788886:001` | `retry` | 취소 공고서.hwpx | `no_searchable_text` |
| `R26BK01778884:000` | `retry` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01778884:000` | `retry` | 2027년 위기청소년통합지원정보시스템 운영 및 유지보수 관련 기술지원협약서(27종).pdf | `pdf_ocr_incomplete` |
| `R26BK01795941:000` | `retry` | 4. 긴급공고요청사유서_2027~2029년 정보시스템 통합유지관리 용역.hwp | `no_searchable_text` |
| `R26BK01795941:000` | `retry` | 7) 공공기관 사칭 범죄 주의 안내문.pdf | `pdf_ocr_incomplete` |
| `R26BK01786362:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01803611:000` | `retry` | 긴급 입찰 사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01785012:001` | `retry` | 취소 공고서.hwpx | `no_searchable_text` |
| `R26BK01829923:000` | `retry` | 입찰공고자료(26G056-H).zip | `no_searchable_text` |
| `R26BK01818024:000` | `retry` | 입찰공고문 등(KREI 정보보호시스템 통합유지관리).zip | `invalid_hwp` |
| `R26BK01815005:000` | `retry` | 공고파일.zip | `unknown_archive_member_requires_review` |
| `R26BK01829962:000` | `retry` | 입찰공고자료(26G057-H).zip | `no_searchable_text` |
| `R26BK01803700:000` | `retry` | (붙임) 물품공급기술지원협약서(2027 고양시).pdf | `pdf_ocr_incomplete` |
| `R26BK01803700:000` | `retry` | (붙임) 물품공급기술지원협약서(2027 고양시).pdf | `pdf_ocr_incomplete` |
| `R26BK01804320:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01781600:000` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01803526:001` | `retry` | 기술지원협약서(날인).pdf | `pdf_ocr_incomplete` |
| `R26BK01803526:001` | `retry` | 지역제한 사유서.hwpx | `pdf_ocr_incomplete` |
| `R26BK01803526:001` | `retry` | 긴급입찰 사유서.hwpx | `pdf_ocr_incomplete` |
| `R26BK01802702:000` | `retry` | 물품공급 및 기술지원 협약서(2027년).pdf | `pdf_ocr_incomplete` |
| `R26BK01797861:000` | `retry` | 공내역서.xlsx | `archive_many_xml_files` |
| `R26BK01797861:000` | `retry` | 3.긴급계약사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01802775:000` | `retry` | (과업지시서)2027년 부안군 CCTV 및 통합관제센터 유지관리용역_261105.hwpx | `pdf_ocr_incomplete` |
| `R26BK01802775:000` | `retry` | (물품공급기술지원협약서)2027년 부안군 CCTV 및 통합관제센터 유지관리용역_261105.pdf | `pdf_ocr_incomplete` |
| `R26BK01800323:003` | `retry` | 3. 긴급공고 사유서_인프라.hwp | `no_searchable_text` |
| `R26BK01801110:000` | `retry` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01801110:000` | `retry` | 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01801713:000` | `retry` | 기술지원협약서[2027년 정보시스템 통합유지관리 용역(긴급)].pdf | `pdf_ocr_incomplete` |
| `R26BK01800329:002` | `retry` | 3. 긴급공고 사유서_응용.hwp | `no_searchable_text` |
| `R26BK01799826:000` | `retry` | 공고문.zip | `unknown_archive_member_requires_review` |
| `R26BK01807866:000` | `retry` | 참조_27년 통합유지보수 대상장비 목록(공고용).xlsx | `large_xml_section` |
| `R26BK01802960:000` | `retry` | (물품공급 및 기술지원 협약서)_2027년 파주시도서관 정보화시스템 통합유지관리 용역.pdf | `pdf_ocr_incomplete` |
| `R26BK01802640:000` | `retry` | 붙임4. 긴급입찰공고사유서(2027-28년 국립재난안전연구원 행정정보시스템 및 전산장비 유지관리).pdf | `pdf_ocr_incomplete` |
| `R26BK01785438:001` | `retry` | 취소공고서_국가_제한_개발_단독_수요기관평가.hwpx | `no_searchable_text` |
| `R26BK01785438:001` | `retry` | 학생의 실질적 AI 역량 강화를 위한 주권 AI 구축 사업 계획(안)_총장결재.pdf | `pdf_ocr_incomplete` |
| `R26BK01802703:000` | `retry` | 물품공급 및 기술지원협약서(수정).pdf | `pdf_ocr_incomplete` |
| `R26BK01802563:001` | `retry` | (첨부필요) 긴급입찰 사유서_PA202602473.pdf | `pdf_ocr_incomplete` |
| `R26BK01799247:000` | `retry` | 긴급입찰사유서.hwpx | `pdf_ocr_incomplete` |
| `R26BK01799247:000` | `retry` | 물품공급  및 기술지원 협약서(합본)_2027년 생활안전용 CCTV시스템 통합 유지관리 용역.pdf | `pdf_ocr_incomplete` |
| `R26BK01799247:000` | `retry` | 과업지시서(2027년 생활안전용 CCTV시스템 통합 유지관리).hwpx | `pdf_ocr_incomplete` |
| `R26BK01809525:000` | `retry` | 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01811869:000` | `retry` | 긴급입찰 사유서(2027년 의왕시 정보자원 통합 유지관리 용역).pdf | `pdf_ocr_incomplete` |
| `R26BK01806663:000` | `retry` | 가격입찰서,_입찰보증금지급각서(서식).hwp | `no_searchable_text` |
| `R26BK01812572:001` | `retry` | 261016 평택(스도) 기술지원협약서(10부).pdf | `pdf_ocr_incomplete` |
| `R26BK01820450:000` | `retry` | 용역계약 일반조건.hwpx | `no_searchable_text` |
| `R26BK01816168:000` | `retry` | 3. 참고서류.zip | `invalid_hwp` |
| `R26BK01818624:000` | `retry` | 4. 긴급입찰요청서(2027년 광주시 방범용 CCTV 시스템 통합유지보수 용역).hwpx | `file_extract_failure` |
| `R26BK01816075:000` | `retry` | 긴급발주사유서.hwp | `isolated_extraction_worker_failed` |
| `R26BK01804586:000` | `retry` | (사업계획서)2027~2028년 정보화시설 유지관리 사업 계획.hwpx | `pdf_ocr_incomplete` |
| `R26BK01763165:001` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01763165:001` | `retry` | (제안요청서)_'27~'28년 취업 후 학자금 상환 전산시스템 운영 및 유지관리_수정.hwpx | `source_extraction_timeout_deferred` |
| `R26BK01763165:001` | `retry` | (파일명 공란) | `source_extraction_timeout_deferred` |
| `R26BK01816121:000` | `retry` | 물품공급 및 기술지원 협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01816121:000` | `retry` | 지역제한 사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01766737:001` | `retry` | 네트워크 장비 구축·운영사업 추가특수조건(조달청지침)(제8258호)(20210615).hwpx | `file_extract_failure` |
| `R26BK01811211:000` | `retry` | 소프트웨어사업 영향평가 검토결과서(2027년).pdf | `pdf_ocr_incomplete` |
| `R26BK01817330:000` | `retry` | 기술지원협약서 목록(2027년 스마트도시 시스템 통합유지관리 용역).hwpx | `pdf_ocr_incomplete` |
| `R26BK01817330:000` | `retry` | 기술지원협약서(2027년 스마트도시 시스템 통합유지관리용역).pdf | `pdf_ocr_incomplete` |
| `R26BK01810351:000` | `retry` | 긴급입찰사유서.pdf | `pdf_ocr_incomplete` |
| `R26BK01830846:000` | `retry` | 3. BIDDING SPECIFICATION(양식).hwp | `no_searchable_text` |
| `R26BK01810345:001` | `retry` | 기술지원협약서.pdf | `pdf_ocr_incomplete` |
| `R26BK01822302:001` | `retry` | 긴급 입찰 사유서(2027년 어업관리단 종합정보시스템 유지관리).pdf | `pdf_ocr_incomplete` |
| `R26BK01816180:000` | `retry` | [산출내역서, 신규버전] '27~28년도 선박장거리위치추적시스템(LRIT) 위탁운영_260929.xlsx | `pdf_ocr_incomplete` |
| `R26BK01817472:000` | `retry` | 3. 긴급입찰 사유서(정보시스템 통합유지보수 사업).pdf | `pdf_ocr_incomplete` |
| `R26BK01745687:001` | `retry` | 2. (탄자니아) 제안요청서.hwp | `hwp5txt_failed` |
| `R26BK01745687:001` | `retry` | 2. (탄자니아) 제안요청서.hwp | `hwp5txt_failed` |
| `R26BK01819559:000` | `retry` | [붙임] 제안요청서(1110)_최종.hwpx | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01819559:000` | `retry` | (파일명 공란) | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01813949:000` | `retry` | 기술지원협약서(디지털홍보영상시스템).pdf | `pdf_ocr_incomplete` |
| `R26BK01813949:000` | `retry` | 긴급입찰 사유서(2027년_2028년 정부세종청사 인터넷전화 및 방송통신시설 유지관리 용역).hwpx | `pdf_ocr_incomplete` |
| `R26BK01821884:000` | `retry` | 협상에 의한 계약 추진 사유.hwp | `unknown_archive_member_requires_review` |
| `R26BK01821884:000` | `retry` | 제안요청서.hwpx | `unknown_archive_member_requires_review` |
| `R26BK01777335:000` | `retry` | (붙임) 2027년 유지보수 등급 측정표.xlsx | `pdf_ocr_incomplete` |
| `R26BK01807233:000` | `retry` | 붙임 2.  제안요청서(안)_구매업무협의 및 사전규격반영.hwpx | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01807233:000` | `retry` | 붙임 3.  긴급입찰사유서(안).hwpx | `pdf_ocr_incomplete` |
| `R26BK01807233:000` | `retry` | [별첨 1-1] 물품공급 및 기술지원협약(falconstor).pdf | `pdf_ocr_incomplete` |
| `R26BK01797202:000` | `retry` | 제안요청서_지능형무역투자플랫폼 (수정).hwpx | 텍스트 판독 잘림 (qualification/role scan truncated) |
| `R26BK01826833:000` | `retry` | 3. 투찰내역서_방글라데시 AI 혁신기술 전문인력 양성사업.xlsm | `large_xml_section` |
| `R26BK01826833:000` | `retry` | 7. KOICA 입찰 관련 규정 및 지침(260811).zip | `pdf_ocr_incomplete` |
| `R26BK01814778:000` | `retry` | [붙임] 입찰서류 일체.zip | `archive_many_xml_files` |
| `R26BK01808941:000` | `retry` | 5. (재) KOICA 입찰 관련 규정, 표준계약서 등(260725)(변경없음).zip | `nested_archive_requires_review` |
| `R26BK01806524:000` | `retry` | 6. 안내자료(선금 및 상생결제제도 안내 등).zip | `archive_many_xml_files` |
| `R26BK01774133:000` | `retry` | 3. 공사도면_안산송산 집단에너지 열네트워크 구축사업 열수송관 공사.pdf | `pdf_ocr_incomplete` |
| `R26BK01774133:000` | `retry` | 4. 입찰안내서_안산송산 집단에너지 열네트워크 구축사업 열수송관 공사.pdf | `pdf_over_page_limit` |

### 원본 검증 및 집계 정보
- 보고 대상 **306개 공고** (`retry` 298, `scanning` 8), 문제 파일 기록 **419행**. 파일별 오류가 없는 공고 **0건**.
- 추출 출처: [운영 서버 읽기 전용 GitHub Actions 로그](https://github.com/suaveforge/monitor/actions/runs/43673446518).
- 후속 조치 시 파일 확장자만 보고 원인을 단정하지 말 것: 실제 바이너리 시그니처 확인 필요 (예: XLSX에 pdf_ocr_incomplete, XLS에 hwp5txt_failed).
