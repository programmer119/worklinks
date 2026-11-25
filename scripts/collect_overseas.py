#!/usr/bin/env python3
"""Independent overseas procurement preview. No domestic database or routes touched."""
import argparse, csv, datetime as dt, io, json, pathlib, re, sqlite3, time, subprocess
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from urllib.parse import urlencode, urljoin, urlsplit, quote
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
    headers={"User-Agent":"WorkLinks-Overseas/0.1","Accept":"application/json,text/csv"}
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
def row(source,id,country,title,buyer,published,deadline,stage,url,raw,amount=None,currency=""):
    if not id or not title: raise ValueError("missing notice id or title")
    return dict(source=source,id=id,country=country,title=title,buyer=buyer,published=published,deadline=deadline,stage=stage,url=https(url),raw=raw,amount=amount,currency=currency)
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
def eu(days):
    start=(utc()-dt.timedelta(days=days)).strftime("%Y%m%d")
    body={"query":"buyer-country IN ("+" ".join(EU)+") AND (classification-cpv=72* OR classification-cpv=48*) AND publication-date>="+start,
          "fields":["publication-number","notice-title","buyer-name","buyer-country","publication-date","notice-type","deadline-receipt-tender-date-lot"],
          "limit":250,"scope":"ALL","paginationMode":"ITERATION"}
    seen=set(); result=[]
    for _ in range(100):
        d=js(TED,body)
        for n in d["notices"]:
            id=scalar(n.get("publication-number")); country=scalar(n.get("buyer-country"))
            result.append(row("eu",id,country,scalar(n.get("notice-title")),scalar(n.get("buyer-name")),scalar(n.get("publication-date")),scalar(n.get("deadline-receipt-tender-date-lot")),scalar(n.get("notice-type")),"https://ted.europa.eu/en/notice/-/detail/"+quote(id,safe=""),n))
        token=d.get("iterationNextToken")
        if not token:return result
        if token in seen:raise ValueError("repeated TED token")
        seen.add(token); body["iterationNextToken"]=token; time.sleep(3)
    raise ValueError("TED page cap reached; source not complete")
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
    pending={"uk","eu","ca"}
    events=Queue()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={}
        for key,fetch in [("uk",uk),("eu",eu),("ca",ca)]:
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
