import datetime as dt
import importlib.util
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

path = Path(__file__).resolve().parents[1] / "scripts/worklinks_kised.py"
spec = importlib.util.spec_from_file_location("worklinks_kised", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NOW = dt.datetime(2026, 10, 24, 15, 0, tzinfo=m.KST)


class KisedTest(unittest.TestCase):
    def test_business_original_id_and_date_only(self):
        soup = BeautifulSoup("""
          <div class="item">
            <a href="https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=179572">2026 민관협력 오픈이노베이션 바이오 분야 2차 모집</a>
            <span>마감일자 2026.11.02 16:00</span>
          </div>
          <div class="item">
            <a href="https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=179408">2026 SVC Seoul 글로벌 멤버십 모집</a>
            <span>마감일자 2026.12.11</span>
          </div>""", "html.parser")
        rows, count, missing = m.business_rows(soup, NOW)
        self.assertEqual((len(rows), count, missing), (2, 2, 0))
        self.assertEqual(rows[0]["deadline"], "2026-11-02T16:00:00+09:00")
        self.assertEqual(rows[1]["deadline"], "2026-12-11")
        self.assertEqual(rows[0]["eligibility"], "자격 확인 필요")

    def test_no_fabricated_detail_or_date(self):
        soup = BeautifulSoup("""
        <a href="https://www.k-startup.go.kr/">사업공고 전체보기</a>
        <a href="https://evil.test/web/contents/bizpbanc-ongoing.do?pbancSn=123456">악성 테스트</a>
        <div><a href="https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=179123">2026 신규창업 자금지원 프로그램 모집</a><span>게시일자 2026.10.20</span></div>
        """, "html.parser")
        rows, listed, missing = m.business_rows(soup, NOW)
        self.assertEqual((listed, missing), (1, 1))
        self.assertIsNone(rows[0]["deadline"])

    def test_board_writeups_are_not_deadlines(self):
        soup = BeautifulSoup("""<table><tr><td>2026.10.23</td><td>
        <a href="/board.es?mid=a10301000000&bid=0004&act=view&list_no=4871">창업기업 신규 상담회 참가자 모집</a>
        </td></tr><tr><td>2026.10.21</td><td>
        <a href="/board.es?mid=a10301000000&bid=0004&act=view&list_no=4872">창업기업 선정 결과 발표</a>
        </td></tr></table>""", "html.parser")
        rows, listed, missing = m.notice_rows(soup, NOW)
        self.assertEqual((len(rows), listed, missing), (1, 2, 0))
        self.assertIsNone(rows[0]["deadline"])

    def test_access_failures_do_not_become_zero(self):
        def broken(_): raise RuntimeError("HTTP 500")
        rows, states = m.scan_kised(broken, NOW)
        self.assertEqual(rows, [])
        self.assertEqual(len(states), 3)
        self.assertTrue(all(x["status"] == "error" for x in states))

    def test_tender_is_not_personal_contract(self):
        soup = BeautifulSoup("""<table><tr>
         <td><a href="/board.es?mid=a10303000000&bid=0005&act=view&list_no=5555">AI 플랫폼 구축 사업자 선정 입찰</a></td>
         <td>접수기간 2026.10.24 ~ 2026.10.31</td>
         </tr></table>""", "html.parser")
        rows, listed, missing = m.tender_rows(soup, NOW)
        self.assertEqual((len(rows), listed, missing), (1, 1, 0))
        self.assertEqual(rows[0]["deadline"], "2026-10-31")
        self.assertIn("자격", rows[0]["review"])


if __name__ == "__main__":
    unittest.main()
