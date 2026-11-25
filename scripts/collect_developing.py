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
"adb":"https://www.adb.org/projects/tenders",
"afdb":"https://www.afdb.org/en/projects-and-operations/procurement",
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
def ungm(allowed,names,days):
    out={};scanned=0
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        page.goto(SOURCES["ungm"],wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(2500)
        field=page.locator("input[name='Title'],input[id='Title'],input[name*='Title' i],input[id*='Title' i]").first
        if not field.count():field=page.get_by_label("Title",exact=True).first
        if not field.count():raise ValueError("UNGM public title filter not found")
        for term in TERMS[:12]:
            field.fill(term)
            page.get_by_role("button",name="Search",exact=True).first.click()
            page.wait_for_timeout(2200)
            seen=set()
            for i in range(40):
                rows=page_rows(page,r"/Public/Notice/\d+(?:[/?#]|$)")
                key=tuple(sorted(x["url"] for x in rows))
                if key in seen:raise ValueError("UNGM pagination repeated")
                seen.add(key);scanned+=len(rows)
                if not rows and not page.get_by_text("No procurement opportunity was found",exact=False).count():raise ValueError("UNGM list parser returned no rows")
                for x in rows:
                    m=re.search(r"/Public/Notice/(\d+)",x["url"])
                    if not m:continue
                    ident=m.group(1)
                    if ident in out:continue
                    # On listing, country is its own field. Detail text retained for source evidence.
                    codes=country_codes(x["text"],names)
                    if not codes:continue
                    title=x["title"]
                    if not WORDS.search(title):continue
                    r=make("ungm",ident,title,codes,x["url"],buyer="",published="",deadline="",stage="notice",reference="",description=x["text"],scope="public listing")
                    if r:out[ident]=r
                if not next_page(page):break
            else:raise ValueError("UNGM pagination cap")
        browser.close()
    if not scanned:raise ValueError("UNGM zero listing rows across all terms")
    return list(out.values()),"partial: title-keyword public listings; detail fields not fully verified",scanned
PATTERNS={"adb":r"/(?:projects/tenders|node/)\S+","afdb":r"/(?:documents|projects-and-operations/procurement)/[^?#]+","ebrd":r"(?:notice|opportunity|project).*(?:id=|/\d+)","idb":r"(?:procurement|tender|notice).*(?:id=|/\d+)","aiib":r"/(?:project-procurement|projects)/.+","edcf":r"boardid=\d+"}
def public_preview(source,allowed,names,days):
    # First public listing pages only: never label as full collection.
    out={};scanned=0
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        page.goto(SOURCES[source],wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(1800)
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
    if not scanned:raise ValueError("No structured public notice links recognized; source adapter needs verification")
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
