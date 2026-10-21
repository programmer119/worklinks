import datetime as dt
import importlib.util
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

path=Path(__file__).resolve().parents[1]/"scripts/worklinks_sefund.py"
spec=importlib.util.spec_from_file_location("band",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=dt.datetime(2026,10,21,21,30,tzinfo=dt.timezone(dt.timedelta(hours=9)))
ROAD='https://sefund.or.kr/portal/news/67fb65c9-978f-4bfd-b3de-2e8e1ec9e650'
MEMBER='https://sefund.or.kr/portal/news/e92224dc-6de5-4a3a-95dc-918216bc0d96'
NEXT='https://sefund.or.kr/portal/news/fa22818a-a746-4d34-a8a4-ba9c9563a7e6'
LOAN='https://sefund.or.kr/portal/news/9480879a-cced-494e-a469-f39f1f048ae9'
LIST='''<main><div class="sf-post-grid">
<a class="sf-post-card" href="/portal/news/67fb65c9-978f-4bfd-b3de-2e8e1ec9e650"><span class="sf-post-badge">공고</span><span class="sf-dl soon">마감 D-7</span><h3 class="sf-post-ctitle">2026년 한국도로공사 상생형 창업, 벤처기업 지원사업 (~10/28)</h3><div class="sf-post-cmeta"><span class="portal-tabnum">2026-10-06</span></div></a>
<a class="sf-post-card" href="/portal/news/e92224dc-6de5-4a3a-95dc-918216bc0d96"><span class="sf-post-badge">공고</span><span class="sf-dl open">접수 중</span><h3 class="sf-post-ctitle">2026년 사회적기업 성장지원센터(서울) 멤버십 회원기업 상시 모집 공고</h3></a>
<a class="sf-post-card is-closed" href="/portal/news/fa22818a-a746-4d34-a8a4-ba9c9563a7e6"><span class="sf-dl closed">접수 마감</span><h3 class="sf-post-ctitle">2026 넥스트밸류 그라운드 투자·PoC 참여기업 모집(~10/16, 기간연장)</h3></a>
<a class="sf-post-card" href="/portal/news/9480879a-cced-494e-a469-f39f1f048ae9"><span class="sf-post-badge">대출안내</span><h3 class="sf-post-ctitle">공제회원기업 임직원 소액대출 지원사업</h3></a>
<a class="sf-post-card" href="https://evil.example/portal/news/11111111-1111-1111-1111-111111111111"><h3 class="sf-post-ctitle">가짜 투자사업</h3></a>
</div></main>'''
ROAD_DETAIL='''<main class="sf-post-detail"><article><header><h2>한국도로공사</h2><p>접수 마감 2026. 10. 28.(수) 18시</p></header><div class="sf-post-body"><p>한국도로공사 상생형 창업 지원사업</p><p>신청자격: 예비창업자도 지원 가능. 그러나 접수 마감 전 사업자등록 완료 필수.</p></div></article></main>'''
MEMBER_DETAIL='''<main class="sf-post-detail"><article><header><p>접수 마감 2026. 12. 31.(목) 14시</p></header><div class="sf-post-body">사회적기업 멤버십 신청을 받습니다.</div></article></main>'''

def soup(s):return BeautifulSoup(s,'html.parser')

class BandTests(unittest.TestCase):
 def test_cards_and_loan_filter(self):
  rows=m.notice_links(soup(LIST));self.assertEqual(len(rows),3)
  self.assertEqual(rows[0]['url'],ROAD);self.assertTrue(rows[2]['closed'])
 def test_explicit_deadline_and_no_fabricated_time(self):
  self.assertEqual(m.deadline_from_header(soup(ROAD_DETAIL)),'2026-10-28T18:00+09:00')
  self.assertEqual(m.deadline_from_header(soup(MEMBER_DETAIL)),'2026-12-31T14:00+09:00')
  raw=ROAD_DETAIL.replace(' 18시','');self.assertEqual(m.deadline_from_header(soup(raw)),'2026-10-28')
  self.assertIsNone(m.deadline_from_header(soup('<main class="sf-post-detail"><article><header><p>교육일 2026.11.23 14시</p></header></article></main>')))
 def test_no_eligible_assumption(self):
  self.assertEqual(m.eligibility_for('예비창업자 가능, 접수 마감 전 사업자등록 완료 필수.'),'사업자 필수')
  self.assertEqual(m.eligibility_for('신청대상 예비창업자와 초기기업'),'예비 언급·조건 확인')
  self.assertEqual(m.eligibility_for('예비창업자 신청 불가'),'예비 제외')
 def test_source_closed_kept_and_ids_stable(self):
  cards=m.notice_links(soup(LIST));a=m.record(cards[0],soup(ROAD_DETAIL),NOW)
  self.assertEqual(a['eligibility'],'사업자 필수');self.assertEqual(a['category'],'창업지원·공모')
  self.assertEqual(a['sourceStatus'],'listed_open')
  changed={**cards[0], 'title':'연장: 새로운 제목'}
  self.assertEqual(a['id'],m.record(changed,soup(ROAD_DETAIL),NOW)['id'])
  self.assertEqual(m.record(cards[2],None,NOW)['sourceStatus'],'closed')
 def test_source_scan_and_not_found(self):
  data={m.NOTICE_URL:LIST,m.NOTICE_URL+'?page=2':'<main><div class="sf-post-grid"></div></main>',ROAD:ROAD_DETAIL,MEMBER:MEMBER_DETAIL}
  def fetch(url):return soup(data[url])
  rows,status=m.scan_band(fetch,NOW)
  self.assertEqual(status['status'],'ok');self.assertEqual(len(rows),3)
  self.assertEqual(status['detailErrors'],0)
  self.assertEqual(len({x['id'] for x in rows}),3)
  self.assertEqual(next(x for x in rows if x['url']==MEMBER)['deadline'],'2026-12-31T14:00+09:00')
 def test_list_failure_is_not_zero_notices(self):
  def broken(url):raise RuntimeError('403 auth')
  with self.assertRaises(RuntimeError):m.scan_band(broken,NOW)

if __name__=='__main__':unittest.main()
