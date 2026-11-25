#!/usr/bin/env python3
"""Isolated development-country procurement collection; no domestic/UK/EU/Canada writes."""
import argparse, datetime as dt, json, pathlib, re, time, hashlib
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
import pycountry

SOURCES={
"wb":"https://search.worldbank.org/api/v2/procnotices",
"ungm":"https://www.ungm.org/Public/Notice",
"adb":"https://www.adb.org/business/project-procurement/business-opportunities",
"afdb":"https://www.afdb.org/en/documents/project-related-procurement/procurement-notices/specific-procurement-notices",
"ebrd":"https://ecepp.ebrd.com/",
"idb":"https://www.iadb.org/en/how-we-can-work-together/procurement/procurement-projects/procurement-notices",
"aiib":"https://www.aiib.org/en/opportunities/business/project-procurement/list.html",
"edcf":"https://www.edcfkorea.go.kr/fe/HPHFFE066M01"}
TERMS=["software","information system","digital platform","application development","case management","management information","web development","digitalization","information technology","cybersecurity","data platform","IT services","système d'information","logiciel","sistema de información","정보시스템","소프트웨어"]
WORDS=re.compile(r"software|information systems?|digital (?:platform|system|transformation|i[sz]ation)|application development|case management|management information|web development|information technology|cybersecurity|data platform|IT services|système d.information|logiciel|sistema de información|sistema informático|정보시스템|소프트웨어|전산|시스템 구축",re.I)
EXCLUDE=set("KOR GBR CAN USA AUS NZL JPN AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU SVK SVN ESP SWE CHE NOR ISL LIE".split())
ALIASES={"Moldova":"MDA","Republic of Moldova":"MDA","Moldova, Republic of":"MDA","Viet Nam":"VNM","Vietnam":"VNM","Kyrgyz Republic":"KGZ","Laos":"LAO","Lao PDR":"LAO","Côte d'Ivoire":"CIV","Cote d'Ivoire":"CIV","Tanzania":"TZA","Bolivia":"BOL","Venezuela":"VEN","Palestine":"PSE","West Bank and Gaza":"PSE","Türkiye":"TUR","Turkey":"TUR","Kosovo":"XKX","Democratic Republic of the Congo":"COD","Republic of the Congo":"COG","Syria":"SYR","Iran":"IRN","South Korea":"KOR","United Kingdom":"GBR","United States":"USA"}
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def get(url):
    with urlopen(Request(url,headers={"User-Agent":"WorkLinks development procurement collector (contact@suaveforge.com)","Accept":"application/json"}),timeout=45) as r:return json.load(r)
def countries():
    d=get("https://api.worldbank.org/v2/country?format=json&per_page=400")
    rows=d[1]; allowed={r["id"] for r in rows if r.get("region",{}).get("id")!="NA" and r.get("incomeLevel",{}).get("id") in ("LIC","LMC","UMC")}-EXCLUDE
    if len(allowed)<100:raise ValueError("World Bank country classification incomplete")
    names={r["name"]:r["id"] for r in rows if r["id"] in allowed}
    for c in pycountry.countries:
        if c.alpha_3 in allowed:
            names[c.name]=c.alpha_3
            if hasattr(c,"official_name"):names[c.official_name]=c.alpha_3
    names.update({k:v for k,v in ALIASES.items() if v in allowed})
    return allowed,names
def country_codes(text,names):
    # Match longest known name first; avoid matching Niger inside Nigeria.
    return sorted({code for name,code in names.items() if re.search(r"(?<![\w])"+re.escape(name)+r"(?![\w])",text,re.I)})
def scalar(x):
    if isinstance(x,list):return " | ".join(map(scalar,x))
    if isinstance(x,dict):return " | ".join(map(scalar,x.values()))
    return str(x or "")
def make(source,id,title,codes,url,**fields):
    if not id or not title or not codes or urlsplit(url).scheme!="https":return None
    return dict(source=source,id=id,title=title,countries=codes,url=url,**fields)
def wb(allowed,names,days):
    start=(dt.date.today()-dt.timedelta(days=days)).isoformat()
    out={};count=0;offset=0
    while True:
        d=get(SOURCES["wb"]+"?"+urlencode({"format":"json","rows":100,"os":offset,"submission_strdate":start,"apilang":"en"}))
        raw=d.get("procnotices")
        if not isinstance(raw,(dict,list)):raise ValueError("WB API schema not recognized")
        batch=list(raw.values()) if isinstance(raw,dict) else raw
        if not batch:break
        count+=len(batch)
        for x in batch:
            if not isinstance(x,dict):continue
            title=scalar(x.get("bid_description") or x.get("title") or x.get("notice_title") or x.get("project_name"))
            body=scalar(x.get("notice_text") or x.get("description"))
            if not WORDS.search(title+" "+body):continue
            codes=country_codes(scalar(x.get("project_ctry_name") or x.get("countryname") or x.get("country_name")),names)
            for c in re.findall(r"\b[A-Z]{3}\b",scalar(x.get("project_ctry_code") or x.get("country_code"))):
                if c in allowed:codes.append(c)
            ident=scalar(x.get("id") or x.get("notice_id") or x.get("noticeid"))
            url=scalar(x.get("url") or x.get("notice_url"))
            if not url.startswith("https://"):url="https://projects.worldbank.org/en/projects-operations/procurement-detail/"+ident
            r=make("wb",ident,title,sorted(set(codes)),url,buyer=scalar(x.get("buyer_name") or x.get("contact_organization")),published=scalar(x.get("submission_date") or x.get("publication_date")),deadline=scalar(x.get("deadline_date") or x.get("deadline")),stage=scalar(x.get("notice_type") or x.get("notice_type_exact")),reference=scalar(x.get("bid_reference_no") or x.get("borrower_reference")),description=body[:12000])
            if r:out[ident]=r
        offset+=len(batch)
        total=d.get("total")
        if len(batch)<100 or (str(total).isdigit() and offset>=int(total)):break
        if offset>=10000:raise ValueError("WB page cap; collection incomplete")
        time.sleep(.25)
    if count==0:raise ValueError("WB returned no notices; verify date/filter")
    return list(out.values()),"ok",count
def page_rows(page, pattern):
    return page.evaluate("""pattern=>{let re=new RegExp(pattern,'i');return [...document.querySelectorAll('a[href]')].filter(a=>re.test(a.href)).map(a=>{let p=a;for(let i=0;i<6&&p.parentElement;i++){if(p.matches('tr,article,li,.notice,.notice-row,.views-row'))break;if(p.innerText.length>120&&/reference|deadline|country|published/i.test(p.innerText))break;p=p.parentElement;if(p.innerText.length>2500){p=a;break}}return {url:a.href,title:a.innerText.trim(),text:p.innerText.trim()}}).filter(r=>r.text&&r.title)}""",pattern)
def next_page(page):
    for loc in [page.get_by_role("button",name=re.compile(r"^next(?: page)?$",re.I)),page.get_by_role("link",name=re.compile(r"^next(?: page)?$",re.I)),page.locator("a[rel=next],button[aria-label='Next page']")]:
        if loc.count():
            b=loc.first
            if b.is_visible() and b.is_enabled() and b.get_attribute("aria-disabled")!="true":
                b.click(timeout=8000);page.wait_for_timeout(1700);return True
    return False
def inspect_page(page,source):
    # Public controls and result structure only. No cookies, tokens or private account data.
    print("DOM",source,page.url,"title",page.title(),flush=True)
    print("CONTROLS",source,json.dumps(page.locator("input,select,button").evaluate_all("""els=>els.slice(0,100).map(e=>({tag:e.tagName,id:e.id,name:e.name,placeholder:e.getAttribute('placeholder'),label:e.getAttribute('aria-label'),type:e.type,bind:e.getAttribute('data-bind'),text:(e.innerText||'').slice(0,100)}))"""),ensure_ascii=False)[:16000],flush=True)
    print("LINKS",source,json.dumps(page.locator("a[href]").evaluate_all("""els=>els.filter(e=>e.innerText.trim()).slice(0,160).map(e=>({text:e.innerText.trim().slice(0,150),href:e.getAttribute('href')}))"""),ensure_ascii=False)[:22000],flush=True)
    print("BODY",source,page.locator("body").inner_text()[:4500],flush=True)

def ungm_field(page):
    # Use actual visible controls; label may be an unassociated text node.
    for selector in ["input[name='Title' i]","input[id='Title' i]","input[id*='title' i]","input[name*='title' i]","input[data-bind*='title' i]","input[placeholder*='title' i]","input[aria-label*='title' i]"]:
        loc=page.locator(selector)
        for item in loc.all():
            if item.is_visible():return item
    loc=page.get_by_label("Title",exact=True)
    for item in loc.all():
        if item.is_visible():return item
    # Locate label by visible caption, then inspect the nearest containing element
    # with exactly one visible text input. Never guess nth input.
    for label in page.get_by_text("Title",exact=True).all():
        if not label.is_visible():continue
        for depth in range(1,5):
            parent=label.locator("xpath="+".."+"/.."*(depth-1))
            fields=[x for x in parent.locator("input:not([type=hidden]):not([type=checkbox]):not([type=radio])").all() if x.is_visible()]
            if len(fields)==1:return fields[0]
            if len(fields)>1:break
    return None

def ungm_rows(page):
    return page.evaluate("""()=>{const re=/\\/public\\/notice\\/(\\d+)(?:[/?#]|$)/i;const rows=new Map();for(const a of document.querySelectorAll('a[href]')){const m=a.href.match(re);if(!m)continue;let p=a;for(let j=0;j<7&&p.parentElement;j++){let q=p.parentElement;if(q.querySelectorAll('a[href*="/Notice/"],a[href*="/notice/"]').length>3||q.innerText.length>3000)break;p=q;if(p.matches('tr,article,.ungm-list-item,.notice-row'))break}let title=a.innerText.trim();if(!title||/^(view|view document|details|open|→|›)$/i.test(title)){let h=p.querySelector('h2,h3,h4,.title,[class*="title" i]');title=h?.innerText?.trim()||p.innerText.trim().split('\\n').find(x=>x.length>12)||''}if(title)rows.set(m[1],{id:m[1],url:a.href,title,text:p.innerText.trim()})}return [...rows.values()]}""")

def ungm(allowed,names,days):
    out={};scanned=0
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(locale="en-US")
        page.on("response",lambda r: print("UNGM request",r.request.method,r.status,r.url.split("?")[0],flush=True) if r.request.resource_type in ("xhr","fetch") and urlsplit(r.url).netloc.endswith("ungm.org") else None)
        page.goto(SOURCES["ungm"],wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(2500)
        inspect_page(page,"ungm")
        field=ungm_field(page)
        if field is None:
            # Some releases collapse advanced filters until the user opens them.
            for label in ["Advanced search","Filters","Show filters","More filters","Search filters"]:
                button=page.get_by_text(label,exact=True)
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=5000);page.wait_for_timeout(500);field=ungm_field(page)
                    if field is not None:break
        if field is None:raise ValueError("UNGM public title control not identified; see actual DOM log")
        print("UNGM title field",field.evaluate("e=>e.outerHTML"),flush=True)
        for term in TERMS[:12]:
            field.fill(term)
            button=page.get_by_role("button",name=re.compile(r"^search\\s*$",re.I))
            if not button.count():raise ValueError("UNGM search button not identified")
            button.first.click()
            page.wait_for_timeout(2500)
            seen=set()
            for i in range(40):
                rows=ungm_rows(page)
                key=tuple(sorted(x["id"] for x in rows))
                if key in seen:raise ValueError("UNGM pagination repeated")
                seen.add(key);scanned+=len(rows)
                print("UNGM term",term,"page",i+1,"rows",len(rows),flush=True)
                if not rows:
                    if page.get_by_text("No procurement opportunity was found",exact=False).count() and page.get_by_text("No procurement opportunity was found",exact=False).first.is_visible():break
                    inspect_page(page,"ungm-results")
                    raise ValueError("UNGM listing result structure not identified")
                for x in rows:
                    ident=x["id"]
                    if ident in out:continue
                    # The detail page explicitly identifies beneficiary country. A buyer's address
                    # or countries mentioned in the title are not a substitute.
                    detail=browser.new_page()
                    try:
                        detail.goto(x["url"],wait_until="domcontentloaded",timeout=25000)
                        text=detail.locator("body").inner_text(timeout=10000)
                        match=re.search(r"(?:Beneficiary country or territory|Beneficiary country|Countries or territories|Country or territory)\s*:?\s*([^\n]+(?:\n[^\n]+)?)",text,re.I)
                        codes=country_codes(match.group(1),names) if match else []
                        if not codes:
                            # Use country from listing's explicit column, if present.
                            m=re.search(r"Beneficiary country or territory\s*:?\s*([^\n]+)",x["text"],re.I)
                            codes=country_codes(m.group(1),names) if m else []
                        if not codes:continue
                        title=x["title"]
                        if not WORDS.search(title+" "+text):continue
                        def val(label):
                            m=re.search(r"(?im)^\s*"+label+r"\s*:?\s*([^\n]+)",text)
                            return m.group(1).strip() if m else ""
                        r=make("ungm",ident,title,codes,x["url"],buyer=val("Organization"),published=val("Published"),deadline=val("Deadline"),stage=val("Type of opportunity") or "notice",reference=val("Reference"),description=text[:12000],scope="public keyword listing and detail")
                        if r:out[ident]=r
                    except Exception as e:print("UNGM detail failure",ident,str(e)[:200],flush=True)
                    finally:detail.close()
                if not next_page(page):break
            else:raise ValueError("UNGM pagination cap")
        browser.close()
    if not scanned:raise ValueError("UNGM zero listing rows across all terms")
    return list(out.values()),"partial: public title-keyword listings; coverage not established",scanned
PATTERNS={"adb":r"/(?:projects/tenders|node/)\S+","afdb":r"/(?:documents|projects-and-operations/procurement)/[^?#]+","ebrd":r"(?:notice|opportunity|project).*(?:id=|/\d+)","idb":r"(?:procurement|tender|notice).*(?:id=|/\d+)","aiib":r"/(?:project-procurement|projects)/.+","edcf":r"boardid=\d+"}
def public_preview(source,allowed,names,days):
    # First public listing pages only: never label as full collection.
    out={};scanned=0
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        page.goto(SOURCES[source],wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(1800)
        inspect_page(page,source)
        seen=set()
        for i in range(5):
            rows=page_rows(page,PATTERNS[source])
            sig=tuple(sorted(x["url"] for x in rows))
            if sig in seen:break
            seen.add(sig);scanned+=len(rows)
            for x in rows:
                if not WORDS.search(x["title"]):continue
                codes=country_codes(x["text"],names)
                if not codes:continue
                ident=hashlib.sha256(x["url"].encode()).hexdigest()[:24]
                r=make(source,ident,x["title"],codes,x["url"],buyer="",published="",deadline="",stage="unverified",reference="",description=x["text"],scope="public listing preview")
                if r:out[ident]=r
            if not next_page(page):break
        browser.close()
    if not scanned:raise ValueError("No structured public notice links recognized; see source-specific actual DOM log")
    return list(out.values()),"partial: public listing preview, pagination and fields not fully verified",scanned
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=pathlib.Path,required=True)
    ap.add_argument("--days",type=int,default=60)
    a=ap.parse_args()
    old=json.loads(a.output.read_text()) if a.output.exists() else {}
    saved={k:{r["id"]:r for r in old.get("notices",[]) if r["source"]==k} for k in SOURCES}
    status={}
    try:allowed,names=countries()
    except Exception as e:
        for k in SOURCES:status[k]={"state":"error","error":"Country classification: "+str(e),"checked":now(),"count":len(saved[k])}
    else:
        for k in SOURCES:
            try:
                fn=wb if k=="wb" else ungm if k=="ungm" else lambda x,y,z:public_preview(k,x,y,z)
                rows,state,scanned=fn(allowed,names,a.days)
                if state=="ok":saved[k]={}
                saved[k].update({r["id"]:r for r in rows})
                status[k]={"state":state,"checked":now(),"count":len(saved[k]),"scanned":scanned,"freshIds":[r["id"] for r in rows]}
                print(k,state,scanned,len(rows),flush=True)
            except Exception as e:
                status[k]={"state":"error","checked":now(),"count":len(saved[k]),"error":str(e)[:600]}
                print(k,"ERROR",str(e),flush=True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    temp=a.output.with_suffix(".tmp")
    temp.write_text(json.dumps({"generatedAt":now(),"sources":status,"notices":[r for rows in saved.values() for r in rows.values()]},ensure_ascii=False),encoding="utf8")
    temp.replace(a.output)
if __name__=="__main__":main()
