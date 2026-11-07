import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from worklinks_local_budget import assess, deadline_from, amount_info, KST, SOURCES, trusted_notice_url, extract_notice_candidates, strong_notice_title, WATCH_DETAILS, COMPETITION_EVIDENCE, primary_notice_text
from bs4 import BeautifulSoup
from unittest.mock import patch
import requests
from worklinks_local_budget import scan_source, OFFICIAL_SOURCE_FALLBACKS

NOW = dt.datetime(2026,11,1,12,0,tzinfo=KST)

class LocalBudgetTest(unittest.TestCase):
    def test_closing_range_uses_end_not_start(self):
        self.assertEqual(deadline_from('접수기간 2026.11.02 ~ 2026.11.27'), '2026-11-27')
    def test_unlabeled_dates_not_deadlines(self):
        self.assertIsNone(deadline_from('게시일 2026.11.01, 행사일 2026.11.14'))
    def test_small_official_award(self):
        x = assess('제1회 지역 AI 영상 아이디어 공모전', '전 국민 누구나, 공고 신청. 접수기간 2026.11.02 ~ 2026.11.27. 상금 150만원. 이메일 접수.', '문경시', 'https://example.go.kr/notice/view?id=1', NOW)
        self.assertIsNotNone(x)
        self.assertEqual(x['deadline'], '2026-11-27')
        self.assertEqual(x['monitorTrack'], 'yearEndLocalBudget')
        self.assertGreater(x['reviewScore'], 3)
    def test_no_investment_only(self):
        self.assertIsNone(assess('스타트업 IR 투자상담 프로그램 모집 공고', '투자상담, 멘토링', '청양군', 'https://example.go.kr/notice/2', NOW))
    def test_no_award_guarantee(self):
        self.assertEqual(amount_info('지원사업 모집공고', '지원사업 공고')[0], '금전 혜택 미확인')
    def test_source_expansion(self):
        self.assertGreaterEqual(len(SOURCES), 15)
        self.assertTrue(any(spec[3] == 'tp_hub' for spec in SOURCES))
    def test_reject_external_untrusted_detail(self):
        self.assertIsNone(trusted_notice_url('https://not-official.example.com/view?id=3', 'https://www.technopark.or.kr/www/linkBoard/list.do', 'tp_hub'))
    def test_javascript_literal_navigation(self):
        soup = BeautifulSoup('<a href="javascript:void(0)" onclick="location.href=\'https://www.oc.go.kr/www/selectBbsNttView.do?nttNo=1\'">2026년 창업지원사업 공고</a>', 'html.parser')
        found, unresolved = extract_notice_candidates(soup, 'https://www.oc.go.kr/www/selectBbsNttList.do?bbsNo=36', 'local')
        self.assertEqual(len(found), 1)
        self.assertEqual(unresolved, 0)
    def test_prestartup_cash_priority(self):
        row = assess('2026 예비창업자 사업화 지원금 공고', '전 국민 누구나 예비창업자 신청 가능. 상금 200만원. 접수기간 2026.11.02 ~ 2026.11.27. 이메일 접수.', '충북', 'https://example.go.kr/notice/view?id=4', NOW)
        self.assertEqual(row['quickWinTier'], 'cash_candidate')
        self.assertTrue(row['preStartupHint'])
    def test_reject_lease_only(self):
        self.assertIsNone(assess('2026년 귀농인의 집 입주자 재공고', '귀농인의 집 주택 11호 입주자 모집 신청', '옥천군', 'https://example.go.kr/notice/view?id=4', NOW))
    def test_kimse_relevance(self):
        row=assess('고령친화 헬스케어 실증지원 사업 모집', '예비창업자 지원사업 신청 2026.11.01~2026.11.24.', '서울', 'https://example.go.kr/notice/view?id=5', NOW)
        self.assertTrue(row['kimseRelevantHint'])


    def test_kimse_healthcare_incubating_lab_not_lost_by_title_gate(self):
        row=assess('보건의료빅데이터 창업 인큐베이팅 랩 모집',
                   '예비창업자 무료 컨설팅 신청 및 교육 제공. 신청기간 2026.11.01~2026.12.31.',
                   '서울', 'https://example.go.kr/notice/view?id=501', NOW)
        self.assertIsNotNone(row)
        self.assertTrue(row['kimseRelevantHint'])
        self.assertEqual(row['quickWinTier'], 'kimse_candidate')

    def test_kimse_cognitive_voice_biomarker_opportunity(self):
        row=assess('음성 바이오마커 인지건강 실증 참여기업 모집',
                   '예비창업자와 스타트업 참여 신청. 시험평가 및 데이터 분석 지원.',
                   '서울', 'https://example.go.kr/notice/view?id=502', NOW)
        self.assertIsNotNone(row)
        self.assertTrue(row['kimseRelevantHint'])

    def test_kimse_health_data_support_can_surface(self):
        row=assess('의료 데이터 개방 환경 지원 공고',
                   '예비창업자 연구용 데이터 환경 신청 가능, 무료 이용 제공.',
                   '서울', 'https://example.go.kr/notice/view?id=503', NOW)
        self.assertIsNotNone(row)
        self.assertTrue(row['kimseRelevantHint'])

    def test_bizinfo_observed_id(self):
        html = """<a href="javascript:void(0)" onclick="goBiz('PBLN_000000000127529')">2026년 지원금 바우처 사업화 지원 공고</a>"""
        soup=BeautifulSoup(html, 'html.parser')
        c, broken=extract_notice_candidates(soup, 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do', 'national')
        self.assertEqual(len(c), 1)
        self.assertIn('pblancId=PBLN_000000000127529', next(iter(c)))
    def test_epeople_related_notice_cannot_extend_expiry(self):
        soup=BeautifulSoup('<main><div>2026년 4월 이벤트 참여기간: 2026.05.21 ~ 2026.05.26 투표종료</div><div>연관생각</div><div>진행중 2026.11.01 ~ 2026.11.06</div></main>', 'html.parser')
        main=primary_notice_text(soup, 'participation')
        self.assertNotIn('2026.11.06', main)
        self.assertEqual(deadline_from('2026년 4월 이벤트\\n'+main), '2026-05-26')
    def test_merchant_notice_is_not_award(self):
        self.assertIsNone(assess('청양사랑상품권 가맹점', '상품권 가맹점 사용내역 공개 안내', '청양군', 'https://example.go.kr/notice/view?id=50', NOW))
    def test_weekday_marked_participation_deadline(self):
        self.assertEqual(deadline_from('참여기간 : 2026년 7월 16일(목) ~ 2026년 7월 30일(목)'), '2026-07-30')
        self.assertEqual(deadline_from('설문조사기간 2026.11.02 ~ 11.26'), '2026-11-26')
    def test_old_survey_does_not_reappear(self):
        result=assess('2026 독자 설문조사 이벤트', '전 국민 참여 가능, 상품권 1만원 추첨. 참여기간 2026.07.16.(목) ~ 2026.07.30.(목)', '서울', 'https://example.go.kr/notice/view?id=20', dt.datetime(2026,11,3,12,tzinfo=KST))
        self.assertIsNone(result)
    def test_expired_range_in_title(self):
        self.assertEqual(deadline_from('2026년 공모전 2026-10-02 ~ 2026-11-02\\n공고 11월 발표'), '2026-11-02')
        x=assess('창업 사업화 바우처 모집 2026-10-02 ~ 2026-11-02', '예비창업자 지원금 100만원 신청', '충남', 'https://example.go.kr/view?id=1', dt.datetime(2026,11,3,12,tzinfo=KST))
        self.assertIsNone(x)
    def test_small_survey_gift_is_visible(self):
        x=assess('2026년 독자 설문조사 이벤트', '국민 누구나 참여 가능합니다. 2026년 설문기간 2026.11.02 ~ 2026.11.26 추첨 30명에게 모바일 상품권 1만원을 지급합니다.', '국세청', 'https://example.go.kr/notice/view?id=10', dt.datetime(2026,11,3,12,tzinfo=KST))
        self.assertIsNotNone(x)
        self.assertEqual(x['quickWinTier'], 'cash_candidate')
        self.assertEqual(x['competitionLevel'], 'unknown')
    def test_suspended_patent_goes_to_waiting(self):
        x=assess('2026 서울 IP 디딤돌 특허출원 지원 모집 공고', '서울 예비창업자 특허출원 비용지원 170만원. 신청 접수 일시 중지. 잔여 건수 발생 시 추가 접수 예정.', '서울', 'https://example.go.kr/notice/view?id=11', dt.datetime(2026,11,3,12,tzinfo=KST))
        self.assertTrue(x['suspendedHint'])
        self.assertEqual(x['quickWinTier'], 'waiting_reopen')
    def test_public_pharmacy_schedule_is_neither_opportunity_nor_kimse(self):
        row=assess('[보건의료] 무주읍 당번약국(문여는 약국) 일정 안내(2026.11.2.~2026.11.8.)',
                   '주민 누구나 확인, 당번 약국 목록 11월 8일까지 공지', '무주',
                   'https://www.muju.go.kr/planweb/board/view.9is?id=1', NOW)
        self.assertIsNone(row)

    def test_unrelated_public_survey_does_not_get_kimse_mark_from_boilerplate(self):
        row=assess('2026 국민참여 정책 아이디어 선호도 투표',
                   '국민 누구나 투표 참여. 상품권 경품 지급. 2026.11.01~2026.11.25. 게시판 공통 안내: 보건의료와 돌봄 정책도 지원합니다.',
                   '서울', 'https://example.go.kr/notice/25', NOW)
        self.assertIsNotNone(row)
        self.assertFalse(row['kimseRelevantHint'])

    def test_medical_startup_notice_remains_relevant(self):
        row=assess('보건의료빅데이터 창업 인큐베이팅 무료 이용 모집',
                   '예비창업자 누구나 신청. 2026.11.01~2026.11.25. 무료 데이터 분석 환경 제공',
                   '서울', 'https://example.go.kr/notice/26', NOW)
        self.assertIsNotNone(row)
        self.assertTrue(row['kimseRelevantHint'])

    def test_health_patient_benefit_not_startup(self):
        self.assertIsNone(assess('치매치료관리비 지원기준 확대', '치매 환자 치료비 지원 안내, 읍면동 신청 가능', '청양', 'https://example.go.kr/view?id=4', NOW))
    def test_reannouncement_is_not_low_competition_proof(self):
        x=assess('2026년 추가 모집 예비창업자 상금 공모전', '전 국민 누구나 신청, 상금 10만원 지원', '경기도', 'https://example.go.kr/notice/view?id=13', NOW)
        self.assertEqual(x['competitionEvidence'], '확인 불가')
        self.assertTrue(COMPETITION_EVIDENCE.search('접수 미달로 추가모집'))
    def test_skip_generic_navigation(self):
        self.assertFalse(strong_notice_title('지원사업'))
        self.assertTrue(strong_notice_title('2026 독자 설문조사 이벤트'))
    def test_municipality_fallback_on_timeout(self):
        primary = 'https://m.yd21.go.kr/kr/html/sub02/020103.html?mode=L'
        official_mirror = OFFICIAL_SOURCE_FALLBACKS['영동군 고시공고'][0]
        calls=[]
        def fake_fetch(session, url):
            calls.append(url)
            if url == primary:
                raise requests.exceptions.ConnectTimeout('primary blocked by remote network')
            return BeautifulSoup('<html><body><a href="/kr/html/sub02/020103.html?mode=V&no=123">2026년도 창업지원금 모집 공고</a></body></html>', 'html.parser')
        with patch('worklinks_local_budget.fetch_soup', side_effect=fake_fetch):
            rows,state=scan_source(('영동군 고시공고',primary,'영동군','local'),object(),NOW)
        self.assertTrue(state['officialMirrorUsed'])
        self.assertEqual(state['sourceUrlUsed'], official_mirror)
        self.assertEqual(state['connectionAttempts'][0]['cause'], 'timeout')
        self.assertIn(primary,calls)
        self.assertIn(official_mirror,calls)
    def test_municipality_all_hosts_fail_stays_error(self):
        primary = 'https://www.uiryeong.go.kr/board/list.uiryeong?boardId=BBS_0000070'
        with patch('worklinks_local_budget.fetch_soup', side_effect=requests.exceptions.ConnectTimeout('connect timeout')):
            rows,state=scan_source(('의령군 고시공고',primary,'의령군','local'),object(),NOW)
        self.assertEqual(state['status'], 'error')
        self.assertEqual(len(rows),0)
        self.assertEqual(len(state['connectionAttempts']), 1+len(OFFICIAL_SOURCE_FALLBACKS['의령군 고시공고']))
    def test_mois_survey_watched(self):
        self.assertIn('행안부 2만원 국민 아이디어 설문', WATCH_DETAILS)
        x=assess('2027년 비영리민간단체 국민 설문조사', '시행기관 행정안전부. 대상 일반국민, 설문조사 참여자 20명 추첨하여 상품권 2만원 지급. 설문기간 2026.10.21 ~ 2026.11.11.', '행정안전부', 'https://daejeon.go.kr/drh/minwonFormView.do?x=1', NOW)
        self.assertIsNotNone(x)
        self.assertEqual(x['quickWinTier'], 'cash_candidate')
    def test_verified_watchlist_exists(self):
        self.assertIn('서울 IP디딤돌 재개 확인', WATCH_DETAILS)
        self.assertTrue(any(spec[3]=='participation' for spec in SOURCES))
        self.assertTrue(any(spec[3]=='watch_detail' for spec in SOURCES))


if __name__ == '__main__':
    unittest.main()
