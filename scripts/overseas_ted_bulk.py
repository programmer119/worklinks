"""Official TED daily XML packages fallback; no web-page scraping."""
import csv, datetime as dt, io, re, tarfile, zipfile
from xml.etree import ElementTree as ET

# Verified against the official November 2026 issue calendar; only a bootstrap
# if the live annual CSV cannot be read. No extrapolation of issue numbers.
BOOTSTRAP={dt.date(2026,11,d):n for d,n in [(18,224),(19,225),(20,226),(23,227),(24,228)]}
BASE="https://ted.europa.eu"
def calendar(raw,year):
    result={}
    text=raw.decode("utf-8-sig")
    for line in text.splitlines():
        dates=re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{4})\b",line)
        if not dates: continue
        date=None
        for fmt in ("%Y-%m-%d","%d/%m/%Y","%d.%m.%Y"):
            try: date=dt.datetime.strptime(dates[0],fmt).date();break
            except ValueError: pass
        if not date or date.year!=year:continue
        rest=line.replace(dates[0],"")
        m=re.search(r"(?:\bS\s*)?(\d{1,3})\s*/\s*"+str(year)+r"\b",rest)
        if not m:m=re.search(r"\b"+str(year)+r"0*(\d{1,3})\b",rest)
        if not m:m=re.search(r"(?<!\d)(\d{1,3})(?!\d)",rest)
        if m and 1<=int(m.group(1))<=366:result[date]=int(m.group(1))
    if not result:raise ValueError("unrecognized TED release calendar")
    return result
def documents(blob):
    if zipfile.is_zipfile(io.BytesIO(blob)):
        with zipfile.ZipFile(io.BytesIO(blob)) as a:
            for item in a.infolist():
                if item.filename.lower().endswith(".xml") and item.file_size<=8_000_000:
                    yield item.filename,a.read(item)
    else:
        with tarfile.open(fileobj=io.BytesIO(blob),mode="r:*") as a:
            for item in a:
                if item.isfile() and item.name.lower().endswith(".xml") and item.size<=8_000_000:
                    yield item.name,a.extractfile(item).read()
def val(root,path):
    node=root.find(path)
    return (node.text or "").strip() if node is not None else ""
def preferred(nodes):
    return next((x.text.strip() for x in nodes if x.text and x.get("languageID","").upper()=="ENG"),next((x.text.strip() for x in nodes if x.text),""))
def parse(name,data,published,eu,row):
    x=ET.fromstring(data)
    if not any((n.text or "").strip().startswith(("48","72")) for n in x.findall(".//{*}ItemClassificationCode")):return None
    buyerids={n.text for n in x.findall("./{*}ContractingParty/{*}Party/{*}PartyIdentification/{*}ID") if n.text}
    countries=set();buyers=[]
    for org in x.findall(".//{*}Organization/{*}Company"):
        oid=val(org,"./{*}PartyIdentification/{*}ID")
        if oid not in buyerids:continue
        country=val(org,"./{*}PostalAddress/{*}Country/{*}IdentificationCode")
        if country in eu:countries.add(country)
        buyer=preferred(org.findall("./{*}PartyName/{*}Name"))
        if buyer:buyers.append(buyer)
    if not countries:return None
    title=preferred(x.findall("./{*}ProcurementProject/{*}Name"))
    if not title:title=preferred(x.findall("./{*}ProcurementProjectLot/{*}ProcurementProject/{*}Name"))
    ident=val(x,".//{*}Publication/{*}NoticePublicationID")
    if not ident:
        m=re.search(r"(\d{6,8})[_-](\d{4})\.xml$",name,re.I)
        if m:ident=m.group(1)+"-"+m.group(2)
    if not title or not ident:return None
    date=val(x,".//{*}Publication/{*}PublicationDate") or published.isoformat()
    date=date[:10]
    deadlines=sorted({n.text.strip()[:10] for n in x.findall(".//{*}TenderSubmissionDeadlinePeriod/{*}EndDate") if n.text})
    stage=val(x,"./{*}NoticeTypeCode")
    value=x.find("./{*}ProcurementProject/{*}RequestedTenderTotal/{*}EstimatedOverallContractAmount")
    amount=None;currency=""
    if value is not None:
        try:amount=float(value.text);currency=value.get("currencyID","")
        except (ValueError,TypeError):pass
    return row("eu",ident," | ".join(sorted(countries)),title," | ".join(dict.fromkeys(buyers)),date," | ".join(deadlines),stage,BASE+"/en/notice/-/detail/"+ident,{"format":"TED daily eForms XML"},amount,currency)
def collect(days,request,utc,eu,row):
    end=utc().date();start=end-dt.timedelta(days=days)
    issues={};fallback=False
    for year in range(start.year,end.year+1):
        try:issues.update(calendar(request(BASE+"/en/release-calendar/-/download/file/CSV/"+str(year)),year))
        except Exception as e:
            print("TED calendar unavailable:",str(e),flush=True);fallback=True
            issues.update({d:n for d,n in BOOTSTRAP.items() if d.year==year})
    selected=[(d,n) for d,n in sorted(issues.items()) if start<=d<end]
    if not selected:raise ValueError("no verified TED issue dates in window")
    if fallback and (start<min(BOOTSTRAP) or end>max(BOOTSTRAP)+dt.timedelta(days=1)):
        raise ValueError("calendar unavailable and bootstrap does not cover requested window")
    result={}
    for date,issue in selected:
        url=BASE+"/packages/daily/"+str(date.year)+str(issue).zfill(5)
        docs=0
        for name,data in documents(request(url)):
            docs+=1
            r=parse(name,data,date,eu,row)
            if r:result[r["id"]]=r
        if not docs:raise ValueError("empty TED daily XML package "+str(issue))
        print("TED issue",issue,"documents",docs,"IT candidates cumulative",len(result),flush=True)
    return list(result.values())
