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
for title, amount in zip(titles, amounts):
    cards.append(f'''
      <article class="card job-mini">
        <div class="job-day"><strong>D-14</strong><span class="job-date">11.26 10:00</span></div>
        <div class="job-core">
          <div class="job-headline">
            <h3><button class="job-card-title" type="button">{title}</button></h3>
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
