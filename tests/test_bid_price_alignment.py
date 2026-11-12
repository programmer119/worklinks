#!/usr/bin/env python3
"""Offline Chromium check: prices must not move when a bid title wraps."""
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

source = (Path(__file__).resolve().parents[1] / "startup-support" / "index.html").read_text(encoding="utf-8")
css = re.findall(r"<style[^>]*>(.*?)</style>", source, re.S)
assert css, "missing site stylesheet"
render = source.split('return \'<article class="card job-mini"', 1)[1].split("}).join(''):", 1)[0]
assert 'job-headline-side' in render and 'job-headline-badge' in render
assert render.index('job-headline-side') < render.index('job-amount')
assert 'job-meta-row' not in render, "price must not follow the title as a separate row"

titles = [
    "2027년~2029년 계룡시 디지털플랫폼 유지관리 용역",
    "2027년 수원시 상수도사업소 홈페이지 및 요금관리시스템 통합유지관리",
]
amounts = ["2억 3,327만원", "2억 8,268만원"]
cards = []
for index, (title, amount) in enumerate(zip(titles, amounts)):
    cards.append(f'''
      <article class="card job-mini">
        <div class="job-day"><strong>D-14</strong><span class="job-date">11.26 10:00</span></div>
        <div class="job-core">
          <div class="job-headline">
            <h3><button class="job-card-title" style="max-width:{220 if index else 900}px" type="button">{title}</button></h3>
            <div class="job-headline-side">
              <div class="job-headline-badge"><span class="job-business-area">SW사업</span></div>
              <span class="job-amount">{amount}</span>
            </div>
          </div>
          <div class="job-footer"></div>
        </div>
      </article>
    ''')
html = '<!doctype html><html lang="ko"><meta charset="utf-8"><style>' + css[0] + (
    '</style><body><div id="jobCards" class="cards" style="width:1380px">'
    + ''.join(cards) + '</div></body></html>'
)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1480, "height": 600})
    page.set_content(html, wait_until="load")
    rows = page.evaluate("""() => [...document.querySelectorAll('#jobCards .job-mini')].map(card => {
      const a = card.querySelector('.job-amount');
      const t = card.querySelector('.job-card-title');
      const r = card.getBoundingClientRect();
      const ar = a.getBoundingClientRect();
      return {titleHeight: t.getBoundingClientRect().height,
        amountY: ar.top-r.top, amountRight: r.right-ar.right,
        amountText: a.textContent};
    })""")
    browser.close()
assert len(rows) == 2, rows
assert rows[1]["titleHeight"] > rows[0]["titleHeight"], rows
assert abs(rows[0]["amountY"] - rows[1]["amountY"]) <= 1, rows
assert abs(rows[0]["amountRight"] - rows[1]["amountRight"]) <= 1, rows
print("BID_PRICE_ALIGNMENT_BROWSER_PASS", rows)


# The production markup, not just a mock, must put priority beside conditions,
# and expose the G2B original as a modest text link instead of a large button.
assert "job-eligibility-content" in render and "job-priority-slot" in render
assert render.index("job-priority-slot") < render.index("job-highlights")
assert "공고 원문 ↗</a>" in render and ">원문 ↗</a>" not in render
assert "has-priority-slot" in render

def layout_card(title, priority, details):
    pills = ''.join('<i class="advantage-pill is-filled"></i>' for _ in range(3))
    return f"""
    <article class="card job-mini">
      <div class="job-day"><strong>D-13</strong><span class="job-date">11.26 10:00</span></div>
      <div class="job-core">
        <div class="job-headline"><h3><button class="job-card-title">{title}</button></h3>
          <div class="job-headline-side"><div class="job-headline-badge"><span class="job-business-area">SW사업</span></div>
          <span class="job-amount">3억 1,102만원</span></div>
        </div>
        <div class="job-eligibility-row has-priority-slot">
          <div class="job-eligibility-content"><span class="job-basic-signal adv-medium">등록업종 일치</span>
            <div class="job-req-strip">{details}</div>
          </div>
          <div class="job-priority-slot">
            <div class="job-advantage adv-high"><span class="advantage-pills">{pills}</span><strong class="advantage-label">{priority}</strong></div>
          </div>
        </div>
        <div class="job-highlights">
          <div class="job-highlight-tags"><span class="tag">4년 연속</span><span class="tag">2025년 입찰참가 2개사</span></div>
          <a class="job-source-link" href="https://www.g2b.go.kr/" target="_blank" rel="noopener noreferrer">공고 원문 ↗</a>
        </div>
      </div>
    </article>
    """
badges = '<button class="job-req-trigger">4대보험 ✓</button><button class="job-req-trigger">비상주 ✓</button>'
long_badges = badges + '<button class="job-req-trigger">인원 미검증 ?</button>'
layout_html = (
    '<!doctype html><html lang="ko"><meta charset="utf-8"><style>' + css[0] +
    '</style><body><div id="jobCards" class="cards" style="max-width:1380px">' +
    layout_card("용인시 홈페이지 유지관리", "우선 검토", badges) +
    layout_card("수원시 상수도 홈페이지 및 요금관리시스템 통합유지관리", "관심 검토", long_badges) +
    '</div></body></html>'
)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for width in (1480, 390):
        page = browser.new_page(viewport={"width":width,"height":860})
        page.set_content(layout_html, wait_until="load")
        aligned = page.evaluate("""() => [...document.querySelectorAll('#jobCards .job-mini')].map(c => {
          const slot=c.querySelector('.job-priority-slot');
          const a=c.querySelector('.job-source-link');
          const r=c.getBoundingClientRect(), s=slot.getBoundingClientRect();
          const k=getComputedStyle(a);
          return {priorityRight:r.right-s.right, priorityWidth:s.width,
            linkBorder:k.borderTopWidth, linkBackground:k.backgroundColor,
            linkHeight:a.getBoundingClientRect().height,
            linkText:a.textContent.trim(), external:a.target==='_blank',
            overflow:c.scrollWidth>c.clientWidth+1};
        })""")
        assert len(aligned) == 2, aligned
        assert all(v["priorityWidth"]>=105 for v in aligned), aligned
        assert abs(aligned[0]["priorityRight"]-aligned[1]["priorityRight"]) <= 1, (width,aligned)
        assert all(v["linkBorder"]=="0px" and v["external"] and v["linkHeight"]>=36 and not v["overflow"] for v in aligned), (width,aligned)
        assert all(v["linkText"]=="공고 원문 ↗" for v in aligned), (width,aligned)
        page.close()
    browser.close()
print("BID_CARD_PRIORITY_AND_SOURCE_LINK_PASS")
