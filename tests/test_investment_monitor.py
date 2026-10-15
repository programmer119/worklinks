import importlib.util
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

path=Path(__file__).resolve().parents[1]/"scripts/refresh_worklinks_investment.py"
spec=importlib.util.spec_from_file_location("monitor",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class InvestmentMonitorTest(unittest.TestCase):
    def test_known_notice_only(self):
        sample='<a href="/announcement/1234567">엔젤투자 피칭룸 참가자 모집</a><a href="/announcement/2000">일반 교육</a><a href="https://evil.test/announcement/456">VC 투자상담</a>'
        got=m.venture_links(BeautifulSoup(sample,"html.parser"))
        self.assertEqual(len(got),1)
        self.assertIn("https://www.venturesquare.net/announcement/1234567",got)
    def test_deadline_cannot_be_event_date(self):
        self.assertIsNone(m.deadline("행사일자 2026.10.25 13:00"))
        self.assertEqual(m.deadline("신청기간 2026.10.01(목) 09:00 ~ 2026.10.25(일) 18:00 신청대상"),"2026-10-25T18:00+09:00")
    def test_eligibility_uncertainty(self):
        self.assertEqual(m.eligibility("2026년 VC 행사"),"자격 확인 필요")
        self.assertEqual(m.eligibility("신청대상 예비창업자 (지역조건 별도) 제출서류"),"예비 언급·조건 확인")
        self.assertEqual(m.eligibility("신청대상 스타트업 제외대상 예비창업자 신청 불가 제출서류"),"예비 제외")
    def test_types(self):
        self.assertEqual(m.category("제3회 엔젤투자 피칭룸"),"엔젤")
        self.assertEqual(m.category("AI 오픈이노베이션"),"CVC·OI")
        self.assertEqual(m.category("VC 투자 상담"),"VC·투자")
        self.assertEqual(m.category("스타트업 IR 데모데이"),"IR·매칭")
    def test_no_fabricated_deadlines(self):
        self.assertIsNone(m.deadline("모집기간: 추후 발표"))
        self.assertIsNone(m.deadline("신청대상 예비창업자"))
    def test_old_deadline(self):
        self.assertLess(m.deadline_dt("2026-01-01"),m.now())

if __name__=="__main__":unittest.main()
