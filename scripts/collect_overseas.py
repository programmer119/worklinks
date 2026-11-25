#!/usr/bin/env python3
"""Independent overseas procurement preview. No domestic database or routes touched."""
import argparse, csv, datetime as dt, io, json, pathlib, re, sqlite3, time, subprocess
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from urllib.parse import urlencode, urljoin, urlsplit, quote
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from email.utils import parsedate_to_datetime

UK="https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
TED="https://api.ted.europa.eu/v3/notices/search"
CA="https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
EU="AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU SVK SVN ESP SWE".split()
WORDS=re.compile(r"\b(software|application development|web development|website|digital platform|information system|information technology|data platform|artificial intelligence|cybersecurity|IT services|SaaS|cloud services|systems integration|logiciel|informatique)\b",re.I)
def utc():
    return dt.datetime.now(dt.timezone.utc)
def request(url, body=None):
    headers={"User-Agent":"WorkLinks-Overseas/0.1","Accept":"*/*" if "/packages/" in url else "application/json,text/csv"}
    if body is not None: headers["Content-Type"]="application/json"
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=45) as r:
                data=r.read(80_000_001)
            if len(data)>80_000_000: raise ValueError("response exceeds byte cap")
            return data
        except HTTPError as e:
            if e.code not in (429,503) or attempt==2: raise
            header=e.headers.get("Retry-After","") if e.headers else ""
            delay=60*(attempt+1)
            if header:
                try: delay=max(delay,int(header))
                except ValueError:
                    try: delay=max(delay,(parsedate_to_datetime(header)-utc()).total_seconds())
                    except (ValueError,TypeError): pass
            if delay>240: raise
            print("Upstream",urlsplit(url).netloc,e.code,"retry in",round(delay),"s",flush=True)
            time.sleep(delay)
def js(url,body=None):
    return json.loads(request(url,body))
def scalar(x):
    if isinstance(x,dict):
        return scalar(x.get("eng") or next(iter(x.values()),""))
    if isinstance(x,list): return " | ".join(filter(None,(scalar(a) for a in x)))
    return str(x) if x is not None else ""
def https(url):
    return url if isinstance(url,str) and urlsplit(url).scheme=="https" and urlsplit(url).netloc else ""
class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data):self.parts.append(data)
    def handle_starttag(self,tag,attrs):
        if tag in ("p","div","br","li","tr","h1","h2","h3"):self.parts.append("\n")
    def handle_endtag(self,tag):
        if tag in ("p","div","li","tr"):self.parts.append("\n")
def clean(value):
    text=scalar(value).strip()
    if not text:return ""
    if re.search(r"</?[a-zA-Z][^>]*>",text):
        p=TextHTML();p.feed(text);text="".join(p.parts)
    return re.sub(r"\n{3,}","\n\n",text).strip()
def detail(raw,source):
    if not isinstance(raw,dict):return {}
    sections=[];docs=[];lang=""
    def add(label,value):
        t=clean(value)
        if t and t not in [s["text"] for s in sections]:sections.append({"label":label,"text":t})
    def doc(title,url):
        if https(url) and url not in [d["url"] for d in docs]:docs.append({"title":clean(title) or "공식 문서", "url":url})
    if source=="uk":
        t=raw.get("tender") or {};lang="en"
        add("사업 내용",t.get("description"))
        add("사업 계획",(raw.get("planning") or {}).get("rationale"))
        for i in t.get("items",[]):add("세부 품목",i.get("description"))
        add("참가 조건",(t.get("eligibilityCriteria") or ""))
        add("조달 방식",t.get("procurementMethodDetails"))
        add("낙찰 기준",t.get("awardCriteriaDetails"))
        for item in t.get("documents",[]):
            doc(item.get("title"),item.get("url"))
        for item in (raw.get("planning") or {}).get("documents",[]):doc(item.get("title"),item.get("url"))
    elif source=="eu":
        for key,label in [("description-proc","사업 내용"),("description-lot","세부 사업 내용"),("description-part","사전 사업 내용"),("selection-criterion-description-lot","참가·선정 기준"),("contract-conditions-description-lot","계약 조건"),("tenderer-legal-form-description-lot","입찰자 법적 형태")]:add(label,raw.get(key))
        primary=raw.get("description-proc") or raw.get("description-lot") or raw.get("notice-title")
        if isinstance(primary,dict):lang={"eng":"en","deu":"de","fra":"fr","pol":"pl","spa":"es","ita":"it","nld":"nl","por":"pt","swe":"sv","ces":"cs","dan":"da","fin":"fi","ron":"ro","hun":"hu","ell":"el","bul":"bg","hrv":"hr","est":"et","lav":"lv","lit":"lt","slk":"sk","slv":"sl","mlt":"mt","gle":"ga"}.get("eng" if primary.get("eng") else next(iter(primary),""),"")
        for key,label in [("document-url-lot","조달 문서"),("document-url-part","사전 조달 문서"),("submission-url-lot","입찰 제출")]:
            value=raw.get(key);items=value if isinstance(value,list) else [value]
            for url in items:
                if isinstance(url,str):doc(label,url)
    elif source=="ca":
        lang="en" if raw.get("tenderDescription-descriptionAppelOffres-eng") or raw.get("title-titre-eng") else "fr"
        add("사업 내용",raw.get("tenderDescription-descriptionAppelOffres-eng") or raw.get("tenderDescription-descriptionAppelOffres-fra"))
        for key,label in [("procurementMethod-methodeApprovisionnement-eng","조달 방식"),("selectionCriteria-criteresSelection-eng","선정 기준"),("tradeAgreements-accordsCommerciaux-eng","적용 무역협정"),("regionsOfDelivery-regionsLivraison-eng","수행 지역")]:add(label,raw.get(key))
        for key in ["attachment-piecesJointes-eng","attachment-piecesJointes-fra"]:
            for url in re.findall(r'https://[^\s<>"|;]+',str(raw.get(key) or "")):doc("첨부 문서",url)
    return {"language":lang,"sections":sections,"documents":docs} if sections or docs else {}
def row(source,id,country,title,buyer,published,deadline,stage,url,raw,amount=None,currency=""):
    if not id or not title: raise ValueError("missing notice id or title")
    return dict(source=source,id=id,country=country,title=title,buyer=buyer,published=published,deadline=deadline,stage=stage,url=https(url),raw=raw,amount=amount,currency=currency,detail=detail(raw,source))
def uk(days, progress=None):
    end=utc(); start=end-dt.timedelta(days=days)
    fmt=lambda d:d.strftime("%Y-%m-%dT%H:%M:%S")
    url=UK+"?"+urlencode(dict(updatedFrom=fmt(start),updatedTo=fmt(end),limit=100))
    seen=set(); result=[]
    for page in range(100):
        if not url: return result
        if url in seen or urlsplit(url).netloc!=urlsplit(UK).netloc: raise ValueError("invalid UK cursor")
        seen.add(url)
        d=js(url)
        for r in d["releases"]:
            t=r.get("tender") or {}; title=t.get("title") or (r.get("planning") or {}).get("rationale") or ""
            codes=[str((i.get("classification") or {}).get("id","")) for i in t.get("items",[])] + [str(c.get("id","")) for i in t.get("items",[]) for c in i.get("additionalClassifications",[])]
            if not (any(c.startswith(("48","72")) for c in codes) or WORDS.search(title+" "+str(t.get("description","")))): continue
            id=str(r.get("id","")); notice=re.search(r"\b\d{6}-\d{4}\b",id)
            url_notice="https://www.find-tender.service.gov.uk/Notice/"+notice.group() if notice else "https://www.find-tender.service.gov.uk/Search"
            result.append(row("uk",r.get("ocid","")+":"+id,"GBR",title,scalar((r.get("buyer") or {}).get("name")),scalar(r.get("date")),scalar((t.get("tenderPeriod") or {}).get("endDate")),scalar(r.get("tag")),url_notice,r,(t.get("value") or {}).get("amount"),scalar((t.get("value") or {}).get("currency"))))
        print("UK page",page+1,"candidates",len(result),flush=True)
        if progress and (page==0 or (page+1)%5==0): progress(list(result))
        nxt=(d.get("links") or {}).get("next")
        if not nxt:return result
        url=urljoin(UK,nxt); time.sleep(11)
    raise ValueError("UK page cap reached; source not complete")
def parse_amount(value):
    try:return float(scalar(value))
    except (ValueError,TypeError):return None
def eu_search(days):
    start=(utc()-dt.timedelta(days=days)).strftime("%Y%m%d")
    body={"query":"buyer-country IN ("+" ".join(EU)+") AND (classification-cpv=72* OR classification-cpv=48*) AND publication-date>="+start,
          "fields":["publication-number","notice-title","buyer-name","buyer-country","publication-date","notice-type","deadline-receipt-tender-date-lot","description-proc","description-lot","description-part","selection-criterion-description-lot","contract-conditions-description-lot","tenderer-legal-form-description-lot","document-url-lot","document-url-part","submission-url-lot","estimated-value-proc","estimated-value-cur-proc"],
          "limit":250,"scope":"ALL","paginationMode":"ITERATION"}
    seen=set(); result=[]
    for page in range(100):
        d=js(TED,body)
        notices=d["notices"]
        print("TED page",page+1,"returned",len(notices),"total",d.get("totalNoticeCount"),flush=True)
        if not notices:return result
        for n in notices:
            id=scalar(n.get("publication-number")); country=scalar(n.get("buyer-country"))
            result.append(row("eu",id,country,scalar(n.get("notice-title")),scalar(n.get("buyer-name")),scalar(n.get("publication-date")),scalar(n.get("deadline-receipt-tender-date-lot")),scalar(n.get("notice-type")),"https://ted.europa.eu/en/notice/-/detail/"+quote(id,safe=""),n,parse_amount(n.get("estimated-value-proc")),scalar(n.get("estimated-value-cur-proc"))))
        token=d.get("iterationNextToken")
        if not token:return result
        if token in seen:raise ValueError("repeated TED token")
        seen.add(token); body["iterationNextToken"]=token; time.sleep(3)
    raise ValueError("TED page cap reached; source not complete")
def eu(days):
    try:
        return eu_search(days)
    except HTTPError as e:
        if e.code not in (429,503):raise
        print("TED Search unavailable; using documented daily package service",flush=True)
        # Import in normal script and importlib fixture contexts.
        import sys
        directory=str(pathlib.Path(__file__).resolve().parent)
        if directory not in sys.path:sys.path.insert(0,directory)
        import overseas_ted_bulk
        return overseas_ted_bulk.collect(days,request,utc,EU,row)
def ca(days):
    csv.field_size_limit(20_000_000)
    reader=csv.DictReader(io.StringIO(request(CA).decode("utf-8-sig")))
    required={"referenceNumber-numeroReference","title-titre-eng","publicationDate-datePublication"}
    if not required.issubset(reader.fieldnames or []):raise ValueError("Canada CSV schema changed")
    result=[]
    for r in reader:
        title=r.get("title-titre-eng") or r.get("title-titre-fra") or ""
        text=" ".join(str(r.get(k) or "") for k in ["title-titre-eng","title-titre-fra","gsinDescription-nibsDescription-eng","unspscDescription-eng","tenderDescription-descriptionAppelOffres-eng"])
        if not WORDS.search(text):continue
        id=r["referenceNumber-numeroReference"]
        result.append(row("ca",id,"CAN",title,r.get("contractingEntityName-nomEntitContractante-eng",""),r["publicationDate-datePublication"],r.get("tenderClosingDate-appelOffresDateCloture",""),r.get("noticeType-avisType-eng",""),r.get("noticeURL-URLavis-eng") or "https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/"+quote(id,safe=""),r))
    return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True,type=pathlib.Path)
    p.add_argument("--output",required=True,type=pathlib.Path)
    p.add_argument("--days",type=int,default=7)
    p.add_argument("--seed",type=pathlib.Path)
    p.add_argument("--publish-script",type=pathlib.Path)
    p.add_argument("--sources",default="uk,eu,ca")
    a=p.parse_args()
    if not 1<=a.days<=30:p.error("--days must be 1..30")
    a.db.parent.mkdir(parents=True,exist_ok=True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(a.db)
    db.executescript("CREATE TABLE IF NOT EXISTS notices(source TEXT,id TEXT,record TEXT,PRIMARY KEY(source,id));CREATE TABLE IF NOT EXISTS status(source TEXT PRIMARY KEY,checked TEXT,success TEXT,error TEXT);")
    if a.seed and a.seed.exists() and not db.execute("SELECT 1 FROM status LIMIT 1").fetchone():
        seed=json.loads(a.seed.read_text(encoding="utf-8"))
        with db:
            db.executemany("INSERT OR REPLACE INTO notices VALUES(?,?,?)",[(r["source"],r["id"],json.dumps(r,ensure_ascii=False)) for r in seed.get("notices",[])])
            db.executemany("INSERT OR REPLACE INTO status VALUES(?,?,?,?)",[(k,v.get("checked"),v.get("success"),v.get("error")) for k,v in seed.get("sources",{}).items()])
    def snapshot(pending):
        sources={s:dict(checked=c,success=t,error=e,pending=s in pending) for s,c,t,e in db.execute("SELECT source,checked,success,error FROM status")}
        for k in pending:
            sources.setdefault(k,dict(checked=None,success=None,error=None,pending=True))
        rows=[]
        for (record,) in db.execute("SELECT record FROM notices"):
            r=json.loads(record);r.pop("raw",None);rows.append(r)
        rows.sort(key=lambda r:r["published"],reverse=True)
        temp=a.output.with_suffix(".tmp")
        temp.write_text(json.dumps(dict(generatedAt=utc().isoformat(),days=a.days,sources=sources,notices=rows),ensure_ascii=False),encoding="utf-8")
        temp.replace(a.output)
        if a.publish_script:
            subprocess.run(["bash",str(a.publish_script.resolve())],check=True)
    pending=set(a.sources.split(","))
    if not pending or not pending <= {"uk","eu","ca"}:p.error("invalid sources")
    events=Queue()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={}
        for key,fetch in [("uk",uk),("eu",eu),("ca",ca)]:
            if key not in pending:continue
            future=pool.submit(fetch,a.days,lambda records:events.put(("partial","uk",records))) if key=="uk" and a.publish_script else pool.submit(fetch,a.days)
            futures[future]=key
            future.add_done_callback(lambda done,k=key:events.put(("done",k,done)))
        if a.publish_script:
            snapshot(pending)
        while pending:
            kind,key,value=events.get()
            if kind=="partial":
                with db:
                    db.executemany("INSERT OR REPLACE INTO notices VALUES(?,?,?)",[(key,r["id"],json.dumps(r,ensure_ascii=False)) for r in value])
                snapshot(pending)
                continue
            future=value;now=utc().isoformat()
            try:
                records=future.result()
                with db:
                    db.execute("DELETE FROM notices WHERE source=?",(key,))
                    db.executemany("INSERT OR REPLACE INTO notices VALUES(?,?,?)",[(key,r["id"],json.dumps(r,ensure_ascii=False)) for r in records])
                    db.execute("INSERT OR REPLACE INTO status VALUES(?,?,?,NULL)",(key,now,now))
                print(key,len(records),flush=True)
            except Exception as e:
                with db:
                    db.execute("INSERT INTO status VALUES(?,?,NULL,?) ON CONFLICT(source) DO UPDATE SET checked=excluded.checked,error=excluded.error",(key,now,str(e)))
                print(key,"FAILED",str(e),flush=True)
            pending.remove(key)
            snapshot(pending)
    return int(any(e for (e,) in db.execute("SELECT error FROM status")))
if __name__=="__main__":
    raise SystemExit(main())
