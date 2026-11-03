import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from worklinks_local_budget import assess, deadline_from, amount_info, KST, SOURCES, trusted_notice_url, extract_notice_candidates
from bs4 import BeautifulSoup

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


if __name__ == '__main__':
    unittest.main()
