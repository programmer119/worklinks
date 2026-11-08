"""Offline backtests using titles and link shapes from real 2026 official notices."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from worklinks_priority_health import (
    KST,SOURCES,match_notice,valid_official_link,observed_links,
    explicit_deadline,scan_one,scan_priority_sources,coverage_summary
)

NOW=dt.datetime(2026,11,7,18,37,tzinfo=KST)
NIA_SOURCE=next(x for x in SOURCES if x[2]=='nia')
KDATA_SOURCE=next(x for x in SOURCES if x[2]=='kdata')

class PriorityDiscoveryBacktest(unittest.TestCase):
    def test_kimse_fit_does_not_inherit_unrelated_page_navigation(self):
        from worklinks_priority_health import kimse_fit
        nav="홈 데이터안심구역 치매 의료데이터 병원 임상시험 전체 사이트 메뉴"
        self.assertEqual(kimse_fit("2026 데이터 표준계약서 활용 교육",nav),"검토")
        self.assertEqual(kimse_fit("치매 조기변화 실증 지원사업",nav),"높음")
        self.assertEqual(kimse_fit("연구 행정 운영 교육",nav),"검토")
        self.assertEqual(kimse_fit("시설 안전 점검 안내",nav),"기타")
        self.assertEqual(kimse_fit("2026년 데이터안심구역 지정 신청 공고"),"기타")
        self.assertEqual(kimse_fit("2026년 의료데이터 중심병원 감리용역 공모"),"기타")
        self.assertEqual(kimse_fit("2026 보건의료데이터 DRB AI활용 심화교육"),"검토")
        self.assertEqual(kimse_fit("방송영상 AI 학습데이터 안심존 개방 안내"),"검토")
        self.assertEqual(kimse_fit("고령자 치매 조기변화 실증 지원사업"),"높음")

    def test_known_must_detect_official_2026_opportunities(self):
        # Official source titles, not keyword-only imaginary cases.
        observed=[
            "심평원 2026년 보건의료빅데이터 창업 인큐베이팅 랩 운영",
            "2026년도 의료기기 사용적합성 인프라 구축 지원사업 신규사업자 모집 공고",
            "2026년도 바이오헬스산업 기술평가-사업화 연계 지원사업 참여기관 모집 공고",
            "2026 데이터+AI 혁신 챌린지 통합 공고 안내",
            "2026년 AI·데이터 문제해결은행 상황별 맞춤 지원 공고",
            "2026년 의료 AI 데이터 활용 바우처 지원사업 수요기관 모집",
            "2026년 디지털헬스 의료기기 병원 실증 지원사업 모집",
            "2026년도 보건산업혁신창업센터 혁신창업멤버스 기업 모집공고",
            "2026년 바이오헬스 특허 및 인허가 컨설팅 지원사업 창업기업 모집",
            "2027년 제1차 용역연구개발과제 주관연구기관 공모 공고",
            "어려울 땐, 전문가에게! 의료기기 전문가 자문위원회 연계 분야별 상담회 신청 안내",
            "방송영상 AI 학습데이터 안심존 정식 개방 안내",
            "AI 허브 민간기업 지원 안내"
        ]
        missed=[title for title in observed if not match_notice(title)]
        self.assertFalse(missed, f"Critical 2026 opportunities missed: {missed}")

    def test_reject_news_not_eligible_recruitment_and_pharmacy(self):
        for title in (
          "[보건의료] 무주읍 당번약국(문여는 약국) 일정 안내",
          "의료기기 사업 선정 결과 안내",
          "2026년 데이터 바우처 운영 용역 입찰공고",
          "의료 AI 사업 우선협상대상자 낙찰 결과",
          "의료분야 신입 직원 채용",
          "치매 치료 관리비 지원 대상 안내"
        ):
            self.assertFalse(match_notice(title),title)

    def test_actual_official_links_not_broad_hostnames(self):
        positives=[
          ("/board/view?linkId=48939696&menuId=MENU01108", SOURCES[0][1], "khidi"),
          ("/mdtis/bizPbanc/bizPbancView?biz_pbanc_id=rhId2pj&biz_pbanc_no=91&menuId=MENU03471",SOURCES[1][1],"device"),
          ("/site/nia_kor/ex/bbs/View.do?bcIdx=29936&cbIdx=99835",NIA_SOURCE[1],"nia"),
        ]
        for href,base,kind in positives:
            self.assertIsNotNone(valid_official_link(href,base,kind),href)
        for href,base,kind in (
          ("javascript:fnDetail('48939696')",SOURCES[0][1],"khidi"),
          ("https://evil.example/board/view?linkId=48939696&menuId=MENU01108",SOURCES[0][1],"khidi"),
          ("/board/view?menuId=MENU01108",SOURCES[0][1],"khidi"),
          ("/site/nia_kor/ex/bbs/View.do?bcIdx=29936&cbIdx=78336",NIA_SOURCE[1],"nia"),
          ("/mdtis/bizPbanc/bizPbancView?biz_pbanc_id=oops",SOURCES[1][1],"device")
        ):
            self.assertIsNone(valid_official_link(href,base,kind),href)

    def test_aihub_detail_url_must_be_official_and_observed(self):
        base=next(x[1] for x in SOURCES if x[2]=="aihub")
        self.assertIsNotNone(valid_official_link(
          "/aihubnews/notice/view.do?pageIndex=1&nttSn=10397&currMenu=132&topMenu=103",base,"aihub"))
        self.assertIsNone(valid_official_link(
          "https://other.example/aihubnews/notice/view.do?nttSn=10397",base,"aihub"))

    def test_official_hira_rss_requires_observed_notice_urls(self):
        from worklinks_priority_health import verified_hira_rss
        xml=b"""<rss><channel>
          <item><title>2026 medical AI data experiment support application</title>
          <link>https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020002000100&amp;brdScnBltNo=4&amp;brdBltNo=12199</link></item>
          <item><title>Fake foreign source</title>
          <link>https://evil.example/bbsDummy.do?pgmid=HIRAA020002000100&amp;brdScnBltNo=4&amp;brdBltNo=12199</link></item>
        </channel></rss>"""
        soup=verified_hira_rss(xml)
        links,count=observed_links(soup,next(s[1] for s in SOURCES if s[2]=="hira"),"hira")
        self.assertEqual(count,1)
        self.assertEqual(links,[]) # The sample is non-Korean generic; relevance still enforced
        with self.assertRaises(ValueError):
            verified_hira_rss(b'<rss><channel><item><title>fake</title><link>https://evil.example/</link></item></channel></rss>')

    def test_untrusted_tls_failure_is_not_bypassed_for_other_hosts(self):
        import requests
        from unittest.mock import patch
        from worklinks_priority_health import verified_public_get
        with patch("worklinks_priority_health.requests.get",
                   side_effect=requests.exceptions.SSLError("untrusted")) as get:
            with self.assertRaises(requests.exceptions.SSLError):
                verified_public_get("https://www.hira.or.kr/bbsDummy.do")
            self.assertEqual(get.call_count,1)

    def test_kdata_aia_uses_ca_bundle_not_unverified_tls(self):
        import certifi
        import requests
        from unittest.mock import patch
        from pathlib import Path
        from worklinks_priority_health import verified_public_get, KDATA_CA_ISSUER
        bundle=Path(certifi.where()).read_bytes()
        end=b"-----END CERTIFICATE-----"
        sample=bundle[:bundle.index(end)+len(end)]+b"\n"
        class Issuer:
            content=sample
            def raise_for_status(self): pass
        class Result:
            status_code=200
        calls=[]
        def fake(url,**kwargs):
            calls.append((url,kwargs))
            if len(calls)==1: raise requests.exceptions.SSLError("missing intermediate")
            if len(calls)==2: return Issuer()
            self.assertIsNot(kwargs.get("verify"),False)
            chain_path=kwargs.get("verify")
            self.assertTrue(chain_path)
            chain=Path(chain_path).read_bytes()
            self.assertIn(sample.strip(),chain)
            self.assertIn(bundle[:40],chain)
            return Result()
        with patch("worklinks_priority_health.requests.get",side_effect=fake):
            result=verified_public_get("https://www.kdata.or.kr/kr/board/notice_01/boardList.do")
        self.assertEqual(result.status_code,200)
        self.assertEqual(calls[1][0],KDATA_CA_ISSUER)
        self.assertEqual(len(calls),3)

    def test_kdata_real_onclick_notice_rows_and_canonical_url(self):
        source=next(x for x in SOURCES if x[2]=="kdata")
        listing=BeautifulSoup("""<ul class="bbs_list">
          <li class="cate"><p class="tit">제목</p></li>
          <li onclick="fnLinkView('39049');"><p class="tit"><a href="javascript:;">[입찰공고] 유지관리 용역</a></p></li>
          <li onclick="fnLinkView('39030');"><p class="tit"><a href="javascript:;">데이터 표준계약서 활용 우수사례 공모 안내</a></p></li>
          <li onclick="fnLinkView('39031');alert('oops')"><p class="tit"><a href="javascript:;">데이터 지원사업 모집</a></p></li>
        </ul>""","html.parser")
        found,count=observed_links(listing,source[1],"kdata")
        self.assertEqual(count,2)
        self.assertEqual(len(found),1)
        expected="https://www.kdata.or.kr/kr/board/notice_01/boardView.do?bbsIdx=39030"
        self.assertEqual(found[0]["url"],expected)
        self.assertEqual(valid_official_link(expected,source[1],"kdata"),expected)
        self.assertIsNone(valid_official_link(
            "/kr/board/notice_01/boardView.do?other=39030",source[1],"kdata"))

    def test_hira_official_notice_board_not_press_releases(self):
        source=next(x for x in SOURCES if x[2]=="hira")
        self.assertIn("pgmid=HIRAA020002000100",source[1])
        official="/bbsDummy.do?pgmid=HIRAA020002000100&brdScnBltNo=4&brdBltNo=12199"
        expected="https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020002000100&brdScnBltNo=4&brdBltNo=12199"
        self.assertEqual(valid_official_link(official,source[1],"hira"),expected)
        self.assertIsNone(valid_official_link(
            "/bbsDummy.do?pgmid=HIRAA020041000100&brdScnBltNo=4&brdBltNo=11144",
            source[1],"hira"))
        listing=BeautifulSoup(
            '<table><tr><td><a href="'+official+'">2026년 의료 AI 데이터 실증 참여기업 모집 공고</a></td></tr></table>',
            "html.parser")
        found,count=observed_links(listing,source[1],"hira")
        self.assertEqual(count,1)
        self.assertEqual(found[0]["url"],expected)

    def test_actual_nia_onclick_article_ids_are_observed_and_constrained(self):
        source=next(x for x in SOURCES if x[2]=="nia")
        html="""<table>
          <tr><td><a href="#view" onclick="doBbsFView('99835','30134','16010100','30134');return false;">
          2026년 재난안전 AI 데이터 활용 해커톤 모집</a></td></tr>
          <tr><td><a href="#view" onclick="doBbsFView('99835','30083','16010100','30083');return false;">
          2026년 NIA 탄소중립 혁신 아이디어 공모전 안내</a></td></tr>
          <tr><td><a href="#view" onclick="doBbsFView('99835','30151','16010100','30150');return false;">
          의료 AI 사업 공모</a></td></tr>
        </table>"""
        found,count=observed_links(BeautifulSoup(html,"html.parser"),source[1],"nia")
        self.assertEqual(count,2)
        # Carbon-neutral competition is not automatically KIMSE-relevant.
        self.assertEqual(len(found),1)
        self.assertTrue(found[0]["url"].endswith("bcIdx=30134"))

    def test_real_aihub_static_row_data_key_yields_article(self):
        source=next(x for x in SOURCES if x[2]=="aihub")
        soup=BeautifulSoup("""<table>
          <tr><td class="subject"><a class="btnView" data-key="10554" href="#">
          방송영상 AI 학습데이터 '안심존' 정식 개방 안내</a></td></tr>
          <tr><td class="subject"><a class="btnView" data-key="notanid" href="#">
          의료 AI 데이터 지원 사업 모집</a></td></tr>
          <tr><td class="subject"><a class="btnView" data-key="10397" href="#">
          의료 AI 데이터 사업 참여기업 모집 공고</a></td></tr>
        </table>""","html.parser")
        found,count=observed_links(soup,source[1],"aihub")
        self.assertEqual(count,2)
        self.assertEqual(len(found),2)
        self.assertIn("nttSn=10554",found[0]["url"])
        self.assertIn("nttSn=10397",found[1]["url"])

    def test_labelled_application_period_date_on_next_line(self):
        text="공모 및 접수기간:\n2026.11.6.(금) ~ 2026.12.7.(월) 11:00"
        self.assertEqual(explicit_deadline(text),"2026-12-07T11:00:00+09:00")
        self.assertIsNone(explicit_deadline("사업기간:\n2026.11.01 ~ 2027.10.31"))

    def test_2026_notice_application_date_not_event_start(self):
        self.assertEqual(
          explicit_deadline("신청기간: 2026.11.01 ~ 11.24 16:00"),
          "2026-11-24T16:00:00+09:00")
        self.assertEqual(
          explicit_deadline("접수기간: 2026.11.01 ~ 2026.11.19 18:00"),
          "2026-11-19T18:00:00+09:00")
        self.assertIsNone(explicit_deadline("신청기간: 2026.11.01 ~ 11월 중"))
        self.assertIsNone(explicit_deadline("행사일: 2026.11.19 10:00"))
        self.assertIsNone(explicit_deadline("사업기간: 2026.11.01 ~ 2027.12.31"))
        self.assertEqual(explicit_deadline("접수마감: 2026.11.22 17:00"),
                         "2026-11-22T17:00:00+09:00")

    def test_historic_khidi_used_to_backtest_scanner(self):
        url="https://www.khidi.or.kr/board/view?menuId=MENU01108&linkId=48939696"
        page=BeautifulSoup("""<table><tr><td>
            <a href="/board/view?linkId=48939696&menuId=MENU01108">
            2026년도 의료기기 사용적합성 인프라 구축 지원사업 신규사업자 모집 공고</a>
            </td><td>2026-01-21</td></tr></table>""","html.parser")
        detail=BeautifulSoup("""<article><h1>2026년도 의료기기 사용적합성 인프라 구축 지원사업</h1>
            공고기간 : 2026. 1. 20(화) ~ 2026. 2. 3(화) 18:00 마감
            </article>""","html.parser")
        def fetch(href):
            return page if href==SOURCES[0][1] else detail
        rows,status=scan_one(SOURCES[0],fetch,NOW)
        self.assertEqual(status["articleLinks"],1)
        self.assertEqual(status["relevantLinks"],1)
        self.assertEqual(rows,[])
        self.assertEqual(status["expiredCandidates"],1)

    def test_one_current_verified_official_notice_emerges_without_eligibility_claim(self):
        detail_url="https://www.khidi.or.kr/board/view?menuId=MENU01108&linkId=48939696"
        listing=BeautifulSoup("""<table><tr><td>
          <a href="/board/view?linkId=48939696&menuId=MENU01108">
          2026년도 의료기기 사용적합성 인프라 구축 지원사업 신규사업자 모집 공고</a>
          </td></tr></table>""","html.parser")
        detail=BeautifulSoup("""<article><p>
          신청기간: 2026.11.02 ~ 2026.11.24 17:00
          예비창업자 접수 요건은 첨부파일 참조
          </p></article>""","html.parser")
        result,state=scan_one(SOURCES[0],lambda u:listing if u==SOURCES[0][1] else detail,NOW)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["deadline"],"2026-11-24T17:00:00+09:00")
        self.assertEqual(result[0]["eligibility"],"자격 확인 필요")
        self.assertEqual(result[0]["url"],detail_url)

    def test_real_november_mfds_research_call_from_khidi_republication(self):
        source=next(x for x in SOURCES if x[2]=="khidi_external")
        detail="/board/view?menuId=MENU01484&linkId=48952358"
        listing=BeautifulSoup(f"""<table><tr><td>
          <a href="{detail}">2027년 제1차 용역연구개발과제 주관연구기관 공모 공고</a>
          </td><td>2026-11-06</td></tr></table>""","html.parser")
        article=BeautifulSoup("""<article><h1>2027년 제1차 용역연구개발과제 주관연구기관 공모 공고</h1>
          공모 및 접수기간: 2026.11.6.(금) ~ 2026.12.7.(월) 11:00
          </article>""","html.parser")
        rows,state=scan_one(source,lambda url:listing if url==source[1] else article,NOW)
        self.assertEqual(state["articleLinks"],1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["deadline"],"2026-12-07T11:00:00+09:00")
        self.assertEqual(rows[0]["eligibility"],"자격 확인 필요")

    def test_current_khidi_medical_device_consultation_stays_visible_in_audit(self):
        source=next(x for x in SOURCES if x[2]=="khidi_events")
        listing=BeautifulSoup("""<table><tr><td>
          <a href="/board/view?menuId=MENU01491&linkId=48952449">
          의료기기 전문가 자문위원회 연계 분야별 상담회 신청 안내(11월 3~4주, 상시접수)</a>
          </td><td>2026-11-06</td></tr></table>""","html.parser")
        article=BeautifulSoup("""<article>
          의료기기 전문가 자문위원회 사업화 분야 상담 신청 안내, 상시접수.
          </article>""","html.parser")
        rows,state=scan_one(source,lambda url:listing if url==source[1] else article,NOW)
        self.assertEqual(len(rows),1) # retained as unverified, not actionable
        self.assertIsNone(rows[0]["deadline"])
        self.assertIn("상시접수",rows[0]["reviewStatus"])
        self.assertEqual(state["undatedCandidates"],1)
        self.assertEqual(state["status"],"partial")

    def test_follow_observed_paginated_list_not_guessed_ids(self):
        from worklinks_priority_health import observed_listing_pages
        source=SOURCES[0]
        base=source[1]
        p2="/board?menuId=MENU01108&pageNum=2"
        p3="/board?menuId=MENU01108&pageNum=3"
        listing=BeautifulSoup('<div class="pagination"><a href="'+p2+'">2</a>'+
            '<a href="'+p3+'">3</a><a href="https://other.example/board?pageNum=2">bad</a></div>'+
            '<a href="/board/view?menuId=MENU01108&linkId=48952449">기사</a>',"html.parser")
        self.assertEqual(len(observed_listing_pages(listing,base)),2)
        n1="/board/view?menuId=MENU01108&linkId=48952446"
        n2="/board/view?menuId=MENU01108&linkId=48952447"
        n3="/board/view?menuId=MENU01108&linkId=48952448"
        def page(link,title):
            return BeautifulSoup('<table><tr><td><a href="'+link+'">'+title+'</a></td></tr></table>',"html.parser")
        first=BeautifulSoup(str(page(n1,"의료 데이터 실증 지원기업 모집"))+
             '<div class="pagination"><a href="'+p2+'">2</a><a href="'+p3+'">3</a></div>',"html.parser")
        pages={
            base:first,
            "https://www.khidi.or.kr"+p2:page(n2,"치매 조기진단 AI 실증 참여기업 모집"),
            "https://www.khidi.or.kr"+p3:page(n3,"보건의료데이터 연구 협력기업 모집"),
        }
        for u,title in [(n1,"의료 데이터 실증 지원기업 모집"),
                         (n2,"치매 조기진단 AI 실증 참여기업 모집"),
                         (n3,"보건의료데이터 연구 협력기업 모집")]:
            pages["https://www.khidi.or.kr"+u]=BeautifulSoup(
                "<article><h1>"+title+"</h1><p>신청마감: 2026.12.15 16:00</p></article>",
                "html.parser")
        visited=[]
        def fetch(u):
            visited.append(u)
            return pages[u]
        rows,state=scan_one(source,fetch,NOW)
        self.assertEqual(state["pagesScanned"],3)
        self.assertEqual(state["relevantLinks"],3)
        self.assertEqual(state["discovered"],3)
        self.assertEqual(len(rows),3)
        self.assertIn("https://www.khidi.or.kr"+p3,visited)
        self.assertEqual(len(set(x["id"] for x in rows)),3)

    def test_unscanned_official_pagination_is_reported_not_hidden(self):
        source=SOURCES[0]
        nav='<div class="pagination">'+''.join(
            f'<a href="/board?menuId=MENU01108&pageNum={n}">{n}</a>'
            for n in range(2,11))+'</div>'
        first=BeautifulSoup('<table><tr><td><a href="/board/view?menuId=MENU01108&linkId=48952446">'
            '의료 데이터 연구 모집 공고</a></td></tr></table>'+nav,"html.parser")
        other=BeautifulSoup('<table><tr><td><a href="/board/view?menuId=MENU01108&linkId=48952447">'
            '의료 데이터 실증 모집 공고</a></td></tr></table>'+nav,"html.parser")
        detail=BeautifulSoup('<article>의료 데이터 연구 모집 공고 신청마감 2026.12.15 16:00</article>',
                             "html.parser")
        def fetch(url):
            return first if url==source[1] else other if "/board?" in url else detail
        rows,state=scan_one(source,fetch,NOW)
        self.assertEqual(state["pagesScanned"],4)
        self.assertGreater(state["pagesPending"],0)
        self.assertEqual(state["status"],"partial")
        self.assertTrue(rows)

    def test_unverified_review_record_remains_visible_without_fake_deadline(self):
        source=SOURCES[0]
        title="의료 AI 데이터 안심구역 실증기업 모집"
        page=BeautifulSoup('<table><tr><td><a href="/board/view?menuId=MENU01108&linkId=48952446">'+
            title+'</a></td></tr></table>',"html.parser")
        detail=BeautifulSoup("<article><p>"+title+" — 상시접수 및 온라인 상담</p></article>","html.parser")
        rows,state=scan_one(source,lambda u: page if u==source[1] else detail,NOW)
        self.assertEqual(state["pendingReview"],1)
        self.assertEqual(len(rows),1)
        self.assertIsNone(rows[0]["deadline"])
        self.assertEqual(rows[0]["kimseFit"],"높음")
        self.assertIn("상시접수",rows[0]["reviewStatus"])
        self.assertNotEqual(rows[0]["eligibility"],"신청 가능")

    def test_source_health_does_not_hide_access_failures(self):
        summary=coverage_summary([
          {"name":"KHIDI","status":"ok","articleLinks":12,"discovered":3},
          {"name":"HIRA","status":"error","error":"timeout"},
        ],["KHIDI","HIRA","K-DATA"])
        self.assertEqual(summary["status"],"degraded")
        self.assertEqual(summary["expected"],3)
        self.assertEqual(summary["healthy"],1)
        self.assertEqual(summary["listingHealthy"],1)
        self.assertEqual(set(summary["listingDegraded"]),{"HIRA","K-DATA"})
        self.assertEqual(set(summary["degraded"]),{"HIRA","K-DATA"})

    def test_one_kdata_link_is_not_declared_full_coverage(self):
        name="K-DATA 데이터·안심구역 공지"
        summary=coverage_summary([
            {"name":name,"status":"partial","articleLinks":1,
             "relevantLinks":0,"discovered":0,"lowLinkCoverage":True}
        ],[name])
        self.assertEqual(summary["listingHealthy"],0)
        self.assertEqual(summary["listingDegraded"],[name])
        self.assertEqual(summary["status"],"degraded")

    def test_malformed_or_js_only_list_is_not_reported_as_no_opportunity(self):
        listing=BeautifulSoup("""<table><tr><td><a href="javascript:doView('123')">
         의료 AI 실증 지원사업 모집</a></td></tr></table>""","html.parser")
        rows,state=scan_one(KDATA_SOURCE,lambda _:listing,NOW)
        self.assertEqual(rows,[])
        self.assertEqual(state["status"],"partial")
        self.assertEqual(state["articleLinks"],0)
        self.assertIn("구조",state["note"])

    def test_one_failed_agency_does_not_block_other_official_agencies(self):
        good=BeautifulSoup("""<table><tr><td><a href="/board/view?linkId=48939696&menuId=MENU01108">
          의료기기 실증 지원사업 모집</a></td></tr></table>""","html.parser")
        bad=BeautifulSoup("<p>Unsupported notice format</p>","html.parser")
        def get(u):
            if "khidi.or.kr/board?" in u:return good
            if "khidi.or.kr/board/view?" in u:
                return BeautifulSoup("<article>신청마감 2026.11.24 17:00</article>","html.parser")
            if "nia.or.kr" in u:raise TimeoutError("official portal timeout")
            return bad
        rows,states=scan_priority_sources(get,NOW)
        self.assertEqual(len(states),len(SOURCES))
        self.assertEqual(next(x["status"] for x in states if "NIA" in x["name"]),"error")
        self.assertTrue(any(x["status"]=="partial" for x in states))
        self.assertEqual(len(rows),1)

if __name__=="__main__":
    unittest.main()
