"""Offline KHIS official-board monitor regression tests."""
import datetime as dt
import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "scripts"))
from worklinks_health_sources import (
    candidate_links, application_deadline, scan_health_sources, scan_source, SOURCES, KST,
)

NOW=dt.datetime(2026,11,7,15,31,tzinfo=KST)
LIST_URL=SOURCES[0][1]
CURRENT_URL="https://www.khis.kr/board.es?act=view&bid=0001&list_no=2778&mid=a10301000000"
OLD_URL="https://www.khis.kr/board.es?act=view&bid=0001&list_no=2448&mid=a10301000000"
FUTURE_URL="https://www.khis.kr/board.es?act=view&bid=0001&list_no=2900&mid=a10301000000"

class OfficialHealthSourceTest(unittest.TestCase):
    def test_observed_detail_only_matching_board(self):
        soup=BeautifulSoup("""<main>
          <a href="/board.es?act=view&bid=0001&list_no=2778&mid=a10301000000">의료데이터 중심병원 AI기업 매칭 상담 모집</a>
          <a href="/board.es?act=view&bid=0009&list_no=2778&mid=a10304000000">의료데이터 중심병원 모집</a>
          <a href="https://evil.example/board.es?act=view&bid=0001&list_no=9999">의료 AI 사업 공고</a>
          <a href="/board.es?bid=0001&nPage=2">보건의료 지원사업</a>
          <a href="javascript:void(0)">의료 AI 바우처 모집</a>
          <a href="/board.es?act=view&bid=0001&list_no=2777">직원 채용 모집</a>
        </main>""","html.parser")
        found=candidate_links(soup,LIST_URL,"0001")
        self.assertEqual(list(found),[CURRENT_URL])

    def test_closing_deadline_is_not_program_end(self):
        body="""사업기간: 협약일~2026.12.31
        신청 기간: 2026년 5월 27일(수) ~ 6월 16일(화) 17:00 까지
        의료 AI 데이터 이용권 지원사업"""
        self.assertEqual(application_deadline("의료 AI 바우처",body),"2026-06-16T17:00:00+09:00")

    def test_both_full_dates_uses_last(self):
        body="접수기간: 2026.11.02 10:00 ~ 2026.11.25 18:00"
        self.assertEqual(application_deadline("보건의료 AI","",None),None)
        self.assertEqual(application_deadline("보건의료 AI",body),"2026-11-25T18:00:00+09:00")

    def test_missing_deadline_never_assumed_from_event(self):
        body="행사일: 2026.11.28 15:00\n사업기간: 2026.11.01 ~ 2026.12.31"
        self.assertIsNone(application_deadline("의료 AI 매칭 행사",body))

    def test_ended_and_future_notice_with_proof(self):
        listing=BeautifulSoup(f"""<table>
          <tr><td><a href="{OLD_URL}">(수정) 2026년 의료 AI 바우처 수요기관 모집</a></td></tr>
          <tr><td><a href="{FUTURE_URL}">2026년 디지털헬스 창업 실증 지원기업 모집</a></td></tr>
        </table>""","html.parser")
        pages={
            LIST_URL:listing,
            OLD_URL:BeautifulSoup("""<article><h1>(수정) 2026년 의료 AI 바우처 수요기관 모집</h1>
                접수기간 2026.05.20 ~ 2026.06.16 17:00 까지</article>""","html.parser"),
            FUTURE_URL:BeautifulSoup("""<article><h1>2026년 디지털헬스 창업 실증 지원기업 모집</h1>
                신청기간 2026.11.02 ~ 2026.11.23 18:00 까지
                개인·예비창업자 자격은 첨부 확인</article>""","html.parser"),
        }
        seen=[]
        def fake(url):
            seen.append(url)
            return pages[url]
        rows,state=scan_source(SOURCES[0],fake,NOW)
        self.assertEqual(state["status"],"ok")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["deadline"],"2026-11-23T18:00:00+09:00")
        self.assertIn(FUTURE_URL,seen)
        self.assertEqual(rows[0]["eligibility"],"자격 확인 필요")

    def test_blank_static_listing_must_be_partial(self):
        rows,state=scan_source(SOURCES[0],lambda _:BeautifulSoup("<p>JS shell</p>","html.parser"),NOW)
        self.assertEqual(rows,[])
        self.assertEqual(state["status"],"partial")
        self.assertIn("0건",state["note"])

    def test_failed_source_stays_error(self):
        import requests
        def fail(_):
            raise requests.exceptions.ConnectTimeout("blocked")
        rows,state=scan_source(SOURCES[0],fail,NOW)
        self.assertEqual(rows,[])
        self.assertEqual(state["status"],"error")

if __name__=="__main__":
    unittest.main()
