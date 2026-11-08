"""Offline regression tests for the independently persisted KIMSE deep audit."""
import datetime as dt
import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from worklinks_priority_health import KST,SOURCES
from worklinks_kimse_deep_audit import (
    crawl_source,examine,likely_historical,signed_date_from_title,run,
)

NOW=dt.datetime(2026,11,8,21,5,tzinfo=KST)

class KimseDeepAuditTests(unittest.TestCase):
    def test_crawls_actual_official_pages_beyond_previous_four_page_cap(self):
        source=SOURCES[0]
        base=source[1]
        data={}
        for n in range(1,7):
            links="".join(
                '<a href="/board?menuId=MENU01108&pageNum='+str(k)+'">'+str(k)+'</a>'
                for k in range(2,7))
            entry='<a href="/board/view?menuId=MENU01108&linkId='+str(48952440+n)+'">의료 데이터 AI 실증 지원사업 모집 '+str(n)+'</a>'
            key=base if n==1 else base+"&pageNum="+str(n)
            data[key]=BeautifulSoup("<div>"+links+entry+"</div>","html.parser")
        rows=crawl_source(source,fetch=lambda url:data[url],page_cap=20)
        self.assertEqual(rows["visited"],6)
        self.assertEqual(len(rows["candidates"]),6)
        self.assertEqual(rows["pendingPages"],[])
        self.assertEqual(rows["failedPages"],[])
        self.assertEqual(len(rows["observedPages"]),6)

    def test_failed_page_and_unvisited_page_do_not_become_success(self):
        source=SOURCES[0]
        base=source[1]
        one=BeautifulSoup(
            '<a href="/board?menuId=MENU01108&pageNum=2">2</a>'
            '<a href="/board?menuId=MENU01108&pageNum=3">3</a>'
            '<a href="/board?menuId=MENU01108&pageNum=4">4</a>',"html.parser")
        def get(url):
            if url==base:return one
            raise TimeoutError("down")
        data=crawl_source(source,get,page_cap=2)
        self.assertEqual(data["visited"],2)
        self.assertEqual(len(data["failedPages"]),1)
        self.assertGreaterEqual(len(data["pendingPages"]),1)

    def test_unambiguous_deadline_only_never_event_year(self):
        self.assertEqual(
            signed_date_from_title("2026 데이터 AI 실증 신청마감: 2026.12.12"),
            "2026-12-12")
        self.assertIsNone(signed_date_from_title(
            "2027 의료 AI 글로벌 박람회 개최 2026.12.12"))
        self.assertIsNone(signed_date_from_title(
            "의료 데이터 창업 상담회 행사일 2026.12.12"))

    def test_historic_not_automatically_called_closed(self):
        self.assertTrue(likely_historical("2025 데이터 AI 실증사업",NOW))
        self.assertFalse(likely_historical("2027 의료 AI 지원 사업",NOW))
        self.assertFalse(likely_historical("의료 AI 지원 사업",NOW))

    def test_eligibility_and_access_failure_are_preserved(self):
        source=SOURCES[0]
        entry={"title":"의료 AI 실증 지원사업 모집","url":
          "https://www.khidi.or.kr/board/view?menuId=MENU01108&linkId=48952446",
          "context":"","listingEvidence":source[1]}
        def article(url):
            return BeautifulSoup("<article><h1>의료 AI 실증 지원사업 모집</h1>"+
               "<p>신청기간: 2026.11.07 ~ 2026.11.29 17:00</p>"+
               "<p>지원대상: 의료기관과 공동연구 가능한 기업</p></article>","html.parser")
        row=examine(entry,source,NOW,article)
        self.assertEqual(row["status"],"deadline_verified_eligibility_pending")
        self.assertEqual(row["applicationDeadline"],"2026-11-29T17:00:00+09:00")
        self.assertEqual(row["eligibility"],"자격 확인 필요")
        fail=examine(entry,source,NOW,lambda url: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(fail["status"],"access_failed")
        invalid={**entry,"url":"https://evil.example/board/view?menuId=MENU01108&linkId=48952446"}
        self.assertEqual(examine(invalid,source,NOW,article)["status"],"invalid_official_link")

    def test_all_official_ages_remain_distinct_and_reviewed(self):
        source=SOURCES[0]
        link="https://www.khidi.or.kr/board/view?menuId=MENU01108&linkId=48952446"
        def fake_crawl(spec):
            return {"source":spec[0],"board":spec[1],"visited":1,
                    "observedPages":[{"url":spec[1],"articleLinks":1,
                     "matchingNotices":1}],
                    "pendingPages":[],"failedPages":[],
                    "candidates":[{"title":"의료 데이터 지원기업 모집",
                        "url":link,"source":spec[0],"kind":spec[2],
                        "listingEvidence":spec[1]}] if spec==source else []}
        def fake_exam(row,spec,now):
            return {"url":row["url"],"source":spec[0],
                    "status":"unknown_deadline"}
        out=run({"generatedAt":"2026-11-08T19:00:00+09:00",
                 "opportunities":[]},now=NOW,
                crawl=fake_crawl,examine_one=fake_exam)
        self.assertEqual(out["summary"]["sources"],len(SOURCES))
        self.assertEqual(out["summary"]["pagesActuallyRead"],len(SOURCES))
        self.assertEqual(out["summary"]["uniqueOfficialCandidateUrls"],1)
        self.assertEqual(out["summary"]["outcomes"]["unknown_deadline"],1)
        self.assertFalse(out["summary"]["fullyVerified"])

if __name__=="__main__":
    unittest.main()
