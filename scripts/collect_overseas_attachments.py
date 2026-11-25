#!/usr/bin/env python3
"""Inspect public procurement attachment links without credentials."""
import argparse, concurrent.futures, datetime as dt, hashlib, io, json, pathlib, re, time, zipfile, subprocess, tempfile, shutil
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit,unquote
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from xml.etree import ElementTree as ET

MAX=20*1024*1024
PORTALS=("gov.uk","the-chest.org.uk","due-north.com","sell2wales.gov.wales","publiccontractsscotland.gov.uk","etendersni.gov.uk","europa.eu","canada.ca","gc.ca","etenders.gov.ie","publicprocurement.be","marches-publics.gouv.fr","mercell.com","eu-supply.com","in-tendhost.co.uk","delta-esourcing.com")
EXT=re.compile(r"\.(pdf|docx|doc|xlsx|xls|zip|odt|rtf|txt)(?:$|[?#])",re.I)
TERMS={"현지 법인":r"registered office|established in|local entity|incorporated in","현지 수행":r"on[- ]site|onsite|based in the uk|based in canada|local presence","수행실적":r"references|track record|previous experience|similar contracts","보안·인증":r"iso 27001|cyber essentials|security clearance|accreditation|certification|data residency|data sovereignty","보험":r"insurance|professional indemnity|public liability","참가 제한":r"eligibility|mandatory requirement|exclusion grounds|minimum turnover|must be registered","기술 요구":r"must support|shall support|must provide|technical requirements|specification"}
def allowed(u):
    try:
        p=urlsplit(u); h=p.hostname or ""
        return p.scheme=="https" and not p.username and not p.password and p.port in (None,443) and any(h==d or h.endswith("."+d) for d in PORTALS)
    except ValueError:return False
class Redirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl):raise ValueError("redirect outside supported public portals")
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def get(url):
    if not allowed(url):raise ValueError("unsupported portal")
    with build_opener(Redirect()).open(Request(url,headers={"User-Agent":"WorkLinks public procurement document index/1.0","Accept":"*/*"}),timeout=12) as r:
        if not allowed(r.geturl()):raise ValueError("unsupported redirect")
        if int(r.headers.get("Content-Length","0") or 0)>MAX:raise ValueError("file exceeds 20 MiB")
        data=r.read(MAX+1)
        if len(data)>MAX:raise ValueError("file exceeds 20 MiB")
        return r.geturl(),r.headers.get("Content-Type",""),r.headers.get("Content-Disposition",""),data
class Links(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.links=[];self.href=None;self.parts=[]
    def handle_starttag(self,t,attrs):
        if t=="a":self.href=dict(attrs).get("href");self.parts=[]
    def handle_data(self,d):
        if self.href:self.parts.append(d)
    def handle_endtag(self,t):
        if t=="a" and self.href:
            self.links.append((self.href," ".join(" ".join(self.parts).split())));self.href=None
def file_kind(data):
    if data[:5]==b"%PDF-":return "pdf"
    if data[:4]==b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names=z.namelist()
                if "word/document.xml" in names:return "docx"
                if "xl/workbook.xml" in names:return "xlsx"
                return "zip"
        except zipfile.BadZipFile:return ""
    if data[:8]==b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":return "office"
    return ""
def extract(data,kind):
    if kind=="pdf":
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data));parts=[];missing=0
        ocr_count=0
        for index,p in enumerate(reader.pages[:150]):
            try:t=p.extract_text() or ""
            except Exception:t=""
            if not t.strip() and ocr_count<5 and shutil.which("pdftoppm") and shutil.which("tesseract"):
                ocr_count+=1
                try:
                    with tempfile.TemporaryDirectory() as folder:
                        src=pathlib.Path(folder)/"page.pdf";src.write_bytes(data)
                        target=str(pathlib.Path(folder)/"page")
                        subprocess.run(["pdftoppm","-f",str(index+1),"-l",str(index+1),"-r","180","-png","-singlefile",str(src),target],check=True,timeout=12,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                        t=subprocess.run(["tesseract",target+".png","stdout","-l","eng","--psm","3"],check=True,timeout=12,capture_output=True).stdout.decode("utf-8",errors="replace")
                except Exception:t=""
            if not t.strip():missing+=1
            parts.append(t)
        return "\n".join(parts),"partial" if missing or len(reader.pages)>150 else "complete"
    if kind=="docx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info=z.getinfo("word/document.xml")
            if info.file_size>MAX:raise ValueError("expanded XML exceeds cap")
            root=ET.fromstring(z.read(info));ns="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            return "\n".join("".join(t.text or "" for t in p.iter(ns+"t")) for p in root.iter(ns+"p")),"body_only"
    return "","unsupported"
def hints(text):
    result=[]
    for label,pattern in TERMS.items():
        for line in re.split(r"\n|(?<=[.!?])\s+",text):
            if re.search(pattern,line,re.I):
                result.append({"label":label,"excerpt":" ".join(line.split())[:160]});break
    return result
def candidate_links(row):
    detail=row.get("detail") or {};seen=set();out=[]
    def add(title,url):
        if isinstance(url,str) and url.startswith("https://") and url not in seen:
            seen.add(url);out.append((title or url,url))
    for d in detail.get("documents",[]):add(d.get("title"),d.get("url"))
    for s in detail.get("sections",[]):
        for u in re.findall(r'https://[^\s<>"\]\)]+',s.get("text","")):add("공고 본문 내 링크",u.rstrip(".,;"))
    if "108918-2026" in str(row.get("id","")):
        add("CHEST 공식 조달 포털","https://procontract.due-north.com/Procurer/Advert/View?advertId=7ffb4fed-74e2-f111-8142-6045bdf14b1f&fromAdvertEvent=True")
    add("공식 원문 공고",row.get("url"))
    return out
def inspect(row,cache):
    result={"checkedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"documents":[],"portals":[],"hints":[]}
    queue=[(t,u,0) for t,u in candidate_links(row)];seen=set()
    while queue and len(seen)<7 and len(result["documents"])<4:
        title,url,depth=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        if not allowed(url):
            result["portals"].append({"title":title,"url":url,"status":"unsupported_portal"});continue
        try:
            final,ctype,disposition,data=get(url)
            kind=file_kind(data)
            if kind:
                sha=hashlib.sha256(data).hexdigest()
                dest=cache/(sha+"."+kind)
                with tempfile.NamedTemporaryFile(dir=cache,delete=False) as tmp:
                    tmp.write(data);temp=pathlib.Path(tmp.name)
                temp.replace(dest)
                state="unsupported";found=[]
                try:
                    content,state=extract(data,kind)
                    if content:
                        (cache/(sha+".txt")).write_text(content,encoding="utf-8")
                        found=hints(content)
                except Exception:state="extract_failed"
                name=unquote(urlsplit(final).path.rsplit("/",1)[-1])
                m=re.search(r'filename\*?=(?:UTF-8\'\')?["]?([^";]+)',disposition,re.I)
                if m:name=unquote(m.group(1).strip())
                result["documents"].append({"title":name if EXT.search(name) else title,"url":url,"status":"public_file","bytes":len(data),"sha256":sha,"format":kind,"extraction":state})
                for h in found:result["hints"].append(dict(h,document=name or title))
                continue
            html=data[:2_000_000].decode("utf-8",errors="replace")
            login=bool(re.search(r'<input[^>]+type\s*=\s*["\']?password|(?:register|log\s*in|sign\s*in)\s+to\s+(?:access|download|view)',html if "html" in ctype else final,re.I))
            if re.search(r"/(?:login|signin)(?:[/?]|$)",urlsplit(final).path,re.I):login=True
            result["portals"].append({"title":title,"url":url,"status":"registration_required" if login else "page_no_file"})
            if depth<1 and "html" in ctype:
                parser=Links();parser.feed(html)
                for href,label in parser.links:
                    u=urljoin(final,href)
                    if not allowed(u) or u in seen:continue
                    if EXT.search(u) or EXT.search(label) or re.search(r"(download|attachment|document|advert/view)",u,re.I) and re.search(r"(download|attachment|document|tender|advert)",label,re.I):
                        queue.append((label or "첨부 후보",u,depth+1))
        except HTTPError as e:
            result["portals"].append({"title":title,"url":url,"status":"access_restricted" if e.code in (401,403) else "http_error","http":e.code})
        except Exception as e:
            result["portals"].append({"title":title,"url":url,"status":"unverified","reason":str(e)[:120]})
    result["status"]="public_files_found" if result["documents"] else "registration_required" if any(p["status"]=="registration_required" for p in result["portals"]) else "no_public_file_verified"
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument("--notices",type=pathlib.Path,required=True);p.add_argument("--output",type=pathlib.Path,required=True);p.add_argument("--cache",type=pathlib.Path,required=True);p.add_argument("--limit",type=int,default=80);a=p.parse_args()
    rows=json.loads(a.notices.read_text())["notices"];a.cache.mkdir(parents=True,exist_ok=True)
    old=json.loads(a.output.read_text()) if a.output.exists() else {};records=old.get("records",{})
    key=lambda r:r["source"]+":"+r["id"]
    now=dt.datetime.now(dt.timezone.utc)
    def age(r):
        try:return (now-dt.datetime.fromisoformat(records[key(r)]["checkedAt"])).total_seconds()
        except Exception:return 10**12
    candidates=[r for r in rows if age(r)>86400 or "108918-2026" in r["id"]]
    candidates.sort(key=lambda r:("108918-2026" not in r["id"],key(r) in records,-age(r),r.get("noticeType") not in ("UK2","pmc")))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        tasks={pool.submit(inspect,r,a.cache):r for r in candidates[:a.limit]}
        for f in concurrent.futures.as_completed(tasks):
            r=tasks[f]
            try:records[key(r)]=f.result()
            except Exception as e:records[key(r)]={"status":"unverified","checkedAt":now.isoformat(),"reason":str(e)[:120]}
            if "108918-2026" in r["id"]:print("MANCHESTER",json.dumps(records[key(r)],ensure_ascii=False),flush=True)
    records={key(r):records[key(r)] for r in rows if key(r) in records}
    out={"generatedAt":now.isoformat(),"totalNotices":len(rows),"records":records}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False),encoding="utf-8")
    print("ATTACHMENTS",len(records),"/",len(rows),"verified files",sum(len(r.get("documents",[])) for r in records.values()),"registration",sum(r.get("status")=="registration_required" for r in records.values()),flush=True)
if __name__=="__main__":main()
