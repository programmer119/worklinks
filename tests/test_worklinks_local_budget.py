import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from worklinks_local_budget import assess, deadline_from, amount_info, KST

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

if __name__ == '__main__':
    unittest.main()
