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


# Production invariant: review priority is on the deadline band,
# qualifications keep full width, original link remains a modest action.
assert "job-priority-band" in render
assert render.index("job-priority-band") < render.index("job-eligibility-row")
assert "job-eligibility-content" in render
assert "job-priority-slot" not in render, "right-side score must not squeeze requirements"
assert "공고 원문 ↗</a>" in render and ">원문 ↗</a>" not in render

def card(title, priority, badges, history):
    pills = ''.join('<i class="advantage-pill is-filled"></i>' for _ in range(3 if priority=="우선 검토" else 2))
    return f"""
    <article class="card job-mini">
      <div class="job-day"><strong>D-13</strong><span class="job-date">11.26 10:00</span>
        <div class="job-priority-band"><div class="job-advantage adv-high">
        <span class="advantage-pills">{pills}</span>
        <strong class="advantage-label">{priority}</strong></div></div>
        <span class="job-institution-badges">
          <span class="job-institution-badge">나</span>
          <span class="job-institution-badge notice">조</span>
          <span class="job-institution-badge demand">경</span>
        </span>
      </div>
      <div class="job-core">
        <div class="job-headline"><h3><button class="job-card-title">{title}</button></h3>
          <div class="job-headline-side"><div class="job-headline-badge">
            <span class="job-business-area">SW사업</span></div>
            <span class="job-amount">3억 1,102만원</span>
          </div>
        </div>
        <div class="job-bid-methods">
          <div class="job-bid-method-cell"><span class="job-bid-label">계약방법</span>
            <span class="job-bid-value">제한경쟁</span></div>
          <div class="job-bid-method-cell"><span class="job-bid-label">낙찰방식</span>
            <span class="job-bid-value">협상계약</span></div>
          <div class="job-bid-method-cell"><span class="job-bid-label">하한율</span>
            <span class="job-bid-value">비적용</span></div>
        </div>
        <div class="job-eligibility-row">
          <div class="job-eligibility-content">
            <span class="job-basic-signal adv-medium">등록업종 일치</span>
            <div class="job-req-strip">{badges}</div>
          </div>
        </div>
        <div class="job-highlights">
          <div class="job-highlight-tags"><span class="tag">4년 연속</span>
          <span class="tag">2025년 입찰참가 2개사</span>{history}</div>
          <a class="job-source-link" href="https://www.g2b.go.kr/" target="_blank"
             rel="noopener noreferrer">공고 원문 ↗</a>
        </div>
      </div>
    </article>
    """

good='<button class="job-req-trigger">4대보험 ✓</button><button class="job-req-trigger">비상주 ✓</button><button class="job-req-trigger">인원 미검증 ?</button>'
bad='<button class="job-req-trigger">4대보험 확인실패 ?</button><button class="job-req-trigger">상주 확인실패 ?</button><button class="job-req-trigger">인원 확인실패 ?</button>'
cards_html=(
    card("(긴급)2027년 용인시 홈페이지 기능개선 및 유지관리 용역","우선 검토",good,"")+
    card("2027년 노후계획도시정비플랫폼 운영 및 유지관리","관심 검토",good,"")+
    card("2027년 지휘훈련시스템 유지보수 용역","관심 검토",good,"")+
    card("2027년 서울시 에너지정보 통합시스템 운영 및 유지관리 용역","관심 검토",bad,'<span class="tag">유사공고 3</span>')
)
html_layout=(
 '<!doctype html><html lang="ko"><meta charset="utf-8">'
 '<meta name="viewport" content="width=device-width,initial-scale=1">'
 '<style>'+css[0]+'</style><body>'
 '<div id="jobCards" class="cards" style="max-width:1320px;margin:auto">'
 +cards_html+'</div></body></html>'
)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    for width in (1366, 390):
        page=browser.new_page(viewport={"width":width,"height":940})
        page.set_content(html_layout, wait_until="load")
        data=page.evaluate("""() => [...document.querySelectorAll('#jobCards .job-mini')].map(card=>{
          const bounds=card.getBoundingClientRect(),head=card.querySelector('.job-day');
          const priority=head.querySelector('.job-priority-band').getBoundingClientRect();
          const initials=head.querySelector('.job-institution-badges').getBoundingClientRect();
          const req=card.querySelector('.job-eligibility-content').getBoundingClientRect();
          const items=[...card.querySelectorAll('.job-eligibility-content > *, .job-req-strip .job-req-trigger')];
          const badgeY=items.map(v=>Math.round(v.getBoundingClientRect().top));
          const link=card.querySelector('.job-source-link'),lr=link.getBoundingClientRect();
          const headline=card.querySelector('.job-card-title');
          const methods=card.querySelector('.job-bid-methods');
          const txt=getComputedStyle(headline);
          return {height:Math.round(bounds.height),left:bounds.left,right:bounds.right,
            priorityRight:Math.round(bounds.right-priority.right),
            priorityTop:Math.round(priority.top-head.getBoundingClientRect().top),
            priorityInitialsOverlap:priority.right>initials.left+1 &&
              priority.left<initials.right-1 && priority.bottom>initials.top+1 &&
              priority.top<initials.bottom-1,
            requirements:badgeY,requirementRowHeight:Math.round(req.height),
            titleFont:parseFloat(txt.fontSize),titleHeight:headline.getBoundingClientRect().height,
            linkWidth:Math.round(lr.width),linkHeight:Math.round(lr.height),
            linkBorder:getComputedStyle(link).borderTopWidth,
            linkText:link.textContent.trim(), 
            contractBackground:getComputedStyle(methods).backgroundColor,
            overflow:card.scrollWidth>card.clientWidth+1,
            pageOverflow:document.documentElement.scrollWidth>innerWidth+1};
        })""")
        assert len(data)==4,data
        assert all(not d["overflow"] and not d["pageOverflow"] for d in data),(width,data)
        assert all(not d["priorityInitialsOverlap"] for d in data),(width,data)
        assert all(d["titleFont"]>=17 for d in data),(width,data)
        assert all(d["linkBorder"]=="0px" and d["linkHeight"]>=32 and
                   d["linkText"]=="공고 원문 ↗" for d in data),(width,data)
        assert all(d["contractBackground"] in ("rgba(0, 0, 0, 0)","transparent") for d in data),(width,data)
        if width==1366:
            assert len(set(d["priorityRight"] for d in data))==1,data
            assert data[3]["requirementRowHeight"]<=42,data
            assert max(d["height"] for d in data)-min(d["height"] for d in data)<=48,data
        print("BID_CARD_BROWSER",width,data,flush=True)
        if width == 1366:
            import base64
            image_bytes=page.screenshot(type="jpeg",quality=64,full_page=False)
            print("BID_GRID_SCREENSHOT_B64="+base64.b64encode(image_bytes).decode("ascii"),flush=True)
        page.close()
    browser.close()
print("BID_CARD_LAYOUT_PASS")


# Regression: exercise the ACTUAL Changcom mode, not just generic job cards.
# A 640px partner card must keep the amount on the right BESIDE the title,
# while a genuinely narrow phone card may stack it, still right-aligned.
def changcom_card(title, amount):
    return f'''<article class="card job-mini">
      <div class="job-day"><strong>D-7</strong><span class="job-date">11.20 10:00</span></div>
      <div class="job-core">
        <div class="job-headline">
          <h3><button class="job-card-title" type="button">{title}</button></h3>
          <div class="job-headline-side">
            <div class="job-headline-badge">SW사업</div>
            <span class="job-amount">{amount}</span>
          </div>
        </div>
      </div>
    </article>'''

partner_html = (
    '<!doctype html><html lang="ko"><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<style>' + '\n'.join(css) + '</style><body>'
    '<div id="jobsView" class="workspace-view on" data-job-mode="partner"'
    ' style="display:block">'
    '<div id="jobCards" class="cards"'
    ' style="width:640px;max-width:calc(100vw - 24px)">'
    + changcom_card(
        '2027년 노후계획도시정비플랫폼 운영 및 유지관리',
        '1억 8,000만원')
    + '</div></div></body></html>'
)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for width, expected_stack in ((700, False), (390, True)):
        page = browser.new_page(viewport={"width":width,"height":600})
        page.set_content(partner_html, wait_until="load")
        rect = page.evaluate("""() => {
            const t = document.querySelector('#jobsView .job-card-title').getBoundingClientRect();
            const a = document.querySelector('#jobsView .job-amount').getBoundingClientRect();
            const h = document.querySelector('#jobsView .job-headline').getBoundingClientRect();
            return {
                titleLeft:t.left,titleRight:t.right,titleTop:t.top,titleBottom:t.bottom,
                titleHeight:t.height,titleFont:parseFloat(getComputedStyle(document.querySelector('#jobsView .job-headline h3')).fontSize),
                titleLineHeight:parseFloat(getComputedStyle(document.querySelector('#jobsView .job-headline h3')).lineHeight),
                priceLeft:a.left,priceRight:a.right,priceTop:a.top,priceBottom:a.bottom,
                priceHeight:a.height,priceFont:parseFloat(getComputedStyle(document.querySelector('#jobsView .job-amount')).fontSize),
                headlineRight:h.right,
                overflow:document.documentElement.scrollWidth>innerWidth+1
            };
        }""")
        assert not rect["overflow"],(width,rect)
        assert abs(rect["priceRight"]-rect["headlineRight"])<=2,(width,rect)
        if expected_stack:
            assert rect["priceTop"]>=rect["titleBottom"]-1,(width,rect)
        else:
            assert rect["priceLeft"]>=rect["titleRight"]-1,(width,rect)
            assert rect["priceTop"]<rect["titleBottom"],(width,rect)
            assert 1.8<=rect["titleHeight"]/rect["titleLineHeight"]<=2.1,(width,rect)
            assert rect["priceFont"]>rect["titleFont"]*2,(width,rect)
            assert abs(rect["titleTop"]-rect["priceTop"])<=4,(width,rect)
            assert abs(rect["titleBottom"]-rect["priceBottom"])<=4,(width,rect)
        print("CHANGCOM_COMPACT_PRICE_LAYOUT_PASS",width,rect,flush=True)
        page.close()
    browser.close()


# Regression: general job pay must not appear in a tiny line below an
# empty reserved business-area slot. Preserve the estimated-pay caveat.
general_html = (
 '<!doctype html><html lang="ko"><meta charset="utf-8">'
 '<meta name="viewport" content="width=device-width,initial-scale=1">'
 '<style>' + '\n'.join(css) + '</style><body>'
 '<div id="jobsView" class="workspace-view on" data-job-mode="general" style="display:block">'
 '<div id="jobCards" class="cards" style="width:640px;max-width:calc(100vw - 24px)">'
 '<article class="card job-mini"><div class="job-day"><strong>D-DAY</strong><span class="job-date">11.14 23:59</span></div>'
 '<div class="job-core"><div class="job-headline">'
 '<h3><button class="job-card-title">급식 통합결제 POS·키오스크 개발 리더</button></h3>'
 '<div class="job-headline-side"><div class="job-headline-badge"></div>'
 '<span class="job-amount" title="예상 월 6,700,000원/계약조건 확인">'
 '<span class="job-amount-main"><span class="job-amount-prefix">예상 월</span>'
 '<strong class="job-amount-value">6,700,000원</strong></span>'
 '<span class="job-amount-note">계약조건 확인</span></span></div></div>'
 '<div class="job-eligibility-row"><div class="job-eligibility-content"></div></div>'
 '<div class="job-highlights"><div class="job-highlight-tags"></div>'
 '<a class="job-source-link">공고 원문 ↗</a></div></div></article>'
 '</div></div></body></html>'
)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for width in (700, 390):
        page = browser.new_page(viewport={"width":width,"height":600})
        page.set_content(general_html, wait_until="load")
        result = page.evaluate("""() => {
            const r = sel => document.querySelector(sel).getBoundingClientRect();
            const title = r('.job-card-title');
            const amount = r('.job-amount');
            const value = r('.job-amount-value');
            const head = r('.job-headline');
            const card = r('#jobCards .job-mini');
            return {
                titleTop:title.top,titleBottom:title.bottom,titleRight:title.right,
                amountTop:amount.top,amountBottom:amount.bottom,
                amountRight:amount.right,headRight:head.right,
                priceSize:parseFloat(getComputedStyle(document.querySelector('.job-amount-value')).fontSize),
                badgeDisplay:getComputedStyle(document.querySelector('.job-headline-badge')).display,
                emptyEligibilityDisplay:getComputedStyle(document.querySelector('.job-eligibility-row')).display,
                priceVisible:document.querySelector('.job-amount-note').textContent.trim()==='계약조건 확인',
                cardHeight:card.height,overlap:amount.left<title.right-1 && amount.top<title.bottom-1,
                overflow:document.documentElement.scrollWidth>innerWidth+1
            };
        }""")
        assert not result["overflow"],(width,result)
        assert result["badgeDisplay"]=="none",(width,result)
        assert result["emptyEligibilityDisplay"]=="none",(width,result)
        assert result["priceVisible"],(width,result)
        assert result["priceSize"]>=20,(width,result)
        assert abs(result["amountRight"]-result["headRight"])<=2,(width,result)
        if width==700:
            assert not result["overlap"],(width,result)
            assert abs(result["amountTop"]-result["titleTop"])<=20,(width,result)
            assert result["cardHeight"]<=170,(width,result)
        else:
            assert result["amountTop"]>=result["titleBottom"]-1,(width,result)
        print("GENERAL_JOB_PRICE_LAYOUT_PASS",width,result,flush=True)
        page.close()
    browser.close()
