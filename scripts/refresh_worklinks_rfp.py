#!/usr/bin/env python3
"""Incrementally extract LIMITED qualification excerpts from public G2B RFPs.
Never classify final bid eligibility from a keyword or omit review of attachments.
"""
import argparse
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import zipfile

BASE='https://api-suaveforge.suaveforge.com:18458/api/g2b/'
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'startup-support/rfp-clauses.json'
MAX_FILE=12_000_000
SIGNALS={
 '입찰참가자격':r'입찰\s*참가\s*자격|참가\s*자격',
 '직접생산':r'직접\s*생산|세부품명번호',
 '중소기업':r'중소기업\s*확인|소기업|소상공인',
 '수행실적':r'수행\s*실적|유사\s*용역\s*실적|실적\s*증명',
 '기술인력':r'투입\s*인력|기술\s*인력|상주\s*인력|자격증',
 '지역제한':r'지역\s*제한|본점\s*소재|소재지',
 '공동수급':r'공동\s*수급|분담\s*이행|하도급'
}
AGENTS={'User-Agent':'WorkLinks-RFP-ReadOnly/1.0','Accept':'application/json'}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        raise ValueError('redirect_forbidden')

OPENER=urllib.request.build_opener(NoRedirect)
def fetch_json(url):
    with OPENER.open(urllib.request.Request(url,headers=AGENTS),timeout=24) as r:
        data=r.read(2_000_000)
        if len(data)>=2_000_000:raise ValueError('oversize_json')
        return json.loads(data.decode('utf-8'))
def datestr(raw):
    m=re.search(r'(20\d{2})[-./]?(\d{2})[-./]?(\d{2})',str(raw or ''))
    return m.group(1)+m.group(2)+m.group(3) if m else ''
def discover(limit,prior=None):
    """Page through all live SW candidates; prioritize unreviewed, matching, urgent.

    Only notice metadata is queried here. Never claim an individual notice fully
    reviewed because the saved API or an attachment API happens to return zero.
    """
    prior=prior or {}
    seen={}
    tz=dt.timezone(dt.timedelta(hours=9))
    today=dt.datetime.now(tz).date()
    now=dt.datetime.now(dt.timezone.utc)
    try:
        total=None
        for offset in range(0,20000,500):
            data=fetch_json(BASE+'saved?sw=1&limit=500&offset='+str(offset))
            if not data.get('ok'):
                print('RFP_DISCOVER_SERVER_ERROR',data.get('error','unknown'))
                break
            total=int(data.get('totalCount') or 0)
            rows=data.get('items') or []
            for item in rows:
                no=str(item.get('bidNo') or '')
                if not re.fullmatch(r'(?:R\d{2}BK\d{8}|\d{11})',no):continue
                order=str(item.get('order') or '0').zfill(3)
                end=datestr(item.get('closes'))
                if not end:continue
                date=dt.datetime.strptime(end,'%Y%m%d').date()
                if date<today or date>today+dt.timedelta(days=18):continue
                key=no+':'+order
                cached=prior.get(key) or {}
                if cached.get('reviewComplete') is True:continue
                if cached.get('classificationVersion')==3:
                    try:
                        checked=dt.datetime.fromisoformat(cached.get('checkedAt','').replace('Z','+00:00'))
                        if checked.tzinfo and (now-checked).total_seconds()<36*3600:
                            continue
                    except (ValueError,TypeError):pass
                # Observed industry restriction is a useful scheduling signal,
                # never an official statement of eligibility.
                qual=item.get('bidEligibility') or {}
                matching=any('1468' in [str(v) for v in (r.get('codes') or [])]
                             for r in (qual.get('requirements') or [])
                             if isinstance(r,dict))
                service=str(item.get('kind') or '')=='servc'
                priority=(0 if matching else 1,0 if service else 1,date)
                seen[key]=(priority,no,order,date.isoformat())
            if len(rows)<500 or offset+len(rows)>=total:break
    except Exception as e:
        print('SAVED_NOTICE_DISCOVERY_UNAVAILABLE',type(e).__name__,str(e)[:140])
    fixture=('R26BK01756420','000','2000-01-01')
    seen.pop('R26BK01756420:000',None)
    candidates=[(no,order,date) for _,no,order,date in sorted(seen.values(),key=lambda x:x[0])]
    return [fixture]+candidates[:max(0,limit-1)]

def legal_file(item):
    url=str(item.get('url') or '')
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.hostname!='www.g2b.go.kr' or u.port not in (None,443):
        return None
    if not u.path.startswith('/pn/pnp/pnpe/UntyAtchFile/'):
        return None
    name=str(item.get('name') or '')[:160]
    lower=name.lower()
    if not lower.endswith(('.hwp','.hwpx','.pdf')):return None
    return name,url
def classify_failure(error):
    if isinstance(error,urllib.error.HTTPError):
        return 'file_download_http_'+str(error.code)
    if isinstance(error,(TimeoutError,ConnectionError,urllib.error.URLError)):
        return 'file_download_connection_error'
    detail=str(error)
    known=('large_file','invalid_hwp','hwp5txt_failed','archive_many_xml_files',
           'pdf_over_100_pages','no_searchable_text','unsupported_format',
           'redirect_forbidden','oversize_json')
    return next((v for v in known if v in detail),'file_extract_failure')


def invalid_file_reason(item):
    url=str(item.get('url') or '')
    if not url:return 'download_url_missing'
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.hostname!='www.g2b.go.kr' or u.port not in (None,443):
        return 'not_approved_official_host'
    if not u.path.startswith('/pn/pnp/pnpe/UntyAtchFile/'):
        return 'unsupported_download_path'
    name=str(item.get('name') or '')
    if not name.lower().endswith(('.hwp','.hwpx','.pdf')):
        return 'unsupported_attachment_format'
    return 'unrecognized_file_error'


def download(url):
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.g2b.go.kr/'})
    with OPENER.open(request,timeout=35) as r:
        size=int(r.headers.get('Content-Length') or '0')
        if size>MAX_FILE:raise ValueError('large_file')
        raw=r.read(MAX_FILE+1)
        if len(raw)>MAX_FILE:raise ValueError('large_file')
        return raw
def extract(name,raw):
    n=name.lower()
    if n.endswith('.hwp'):
        if not raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):raise ValueError('invalid_hwp')
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'source.hwp'
            p.write_bytes(raw)
            r=subprocess.run(['hwp5txt',str(p)],capture_output=True,timeout=38)
            if r.returncode:raise ValueError('hwp5txt_failed')
            return r.stdout.decode('utf-8','replace')
    if n.endswith('.hwpx'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            data=[]
            members=[x for x in archive.namelist() if x.startswith('Contents/') and x.endswith('.xml')]
            if len(members)>200:raise ValueError('archive_many_xml_files')
            for member in members[:80]:
                info=archive.getinfo(member)
                if info.file_size>3_000_000:continue
                tree=ET.fromstring(archive.read(member))
                data.append(' '.join(x.text or '' for x in tree.iter() if x.tag.endswith('}t')))
            return '\n'.join(data)
    if n.endswith('.pdf'):
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(raw))
        if len(pdf.pages)>100:raise ValueError('pdf_over_100_pages')
        return '\n'.join(page.extract_text() or '' for page in pdf.pages[:100])
    raise ValueError('unsupported_format')
def parse_clauses(text):
    text=re.sub(r'[\u200b\ufeff\x00]','',text)
    text=text[:350_000]
    triggers={name:len(re.findall(rx,text,re.I)) for name,rx in SIGNALS.items()}
    snippets=[]
    lines=re.split(r'\n+',text)
    seen=set()
    for raw in lines:
        line=' '.join(raw.split())
        if not 14<=len(line)<=1800:continue
        match=next((k for k,rx in SIGNALS.items() if re.search(rx,line,re.I)),None)
        if not match:continue
        clean=line[:190]
        if clean in seen:continue
        seen.add(clean)
        snippets.append({'topic':match,'text':clean})
        if len(snippets)>=16:break
    return triggers,snippets
def process(no,ordn):
    data=fetch_json(BASE+'bid-evidence?'+urllib.parse.urlencode({'bidNo':no,'order':ordn}))
    docs=data.get('attachments') or {}
    if not docs.get('ok') or not docs.get('complete'):
        return {'status':'metadata_not_confirmed','reasonCode':'metadata_api_error' if not docs.get('ok') else 'metadata_page_incomplete',
                'sourceError':str(docs.get('error') or '')[:120],
                'count':docs.get('count'),'source':'나라장터 e발주 첨부파일 API'}
    if not docs.get('items'):
        notice=data.get('noticeDocuments') or {}
        ecount=docs.get('eorderCount')
        detail_status='notice_detail_'+('api_error' if not notice.get('ok') else
           'zero_files' if notice.get('complete') else 'partial_response')
        return {'status':'no_official_attachment_metadata',
                'reasonCode':'eorder_api_zero__'+detail_status,
                'source':'나라장터 e발주 + 공식 입찰공고 상세',
                'count':0,'eorderCount':ecount,'noticeDetailDocumentCount':0,
                'noticeDetailError':notice.get('error') or '',
                'files':[],'reviewComplete':False,
                'contractPerformanceVerified':False}
    saved=[]
    for item in docs.get('items',[])[:8]:
        public=legal_file(item)
        if not public:
            saved.append({'name':str(item.get('name') or '')[:160],'readable':False,
                          'errorCategory':invalid_file_reason(item)})
            continue
        name,url=public
        record={'name':name,'sourceUrl':url,'readable':False}
        try:
            content=extract(name,download(url))
            if len(content.strip())<100:raise ValueError('no_searchable_text')
            triggers,snippets=parse_clauses(content)
            record.update({'readable':True,'textChars':len(content),'topics':triggers,'snippets':snippets})
        except Exception as ex:
            record['errorCategory']=classify_failure(ex)
            record['error']=type(ex).__name__+': '+str(ex)[:90]
        saved.append(record)
    readable=any(x.get('readable') for x in saved)
    notice=data.get('noticeDocuments') or {}
    return {'status':'text_extracted_requires_review' if readable else 'text_unavailable',
            'reasonCode':'readable_text_requires_full_review' if readable else
                         'download_or_format_failure',
            'source':'나라장터 e발주 + 입찰공고 상세',
            'count':docs.get('count'),'eorderCount':docs.get('eorderCount'),
            'noticeDetailDocumentCount':docs.get('noticeDetailDocumentCount'),
            'noticeDetailError':notice.get('error') or '',
            'files':saved,
            'reviewComplete':False,'contractPerformanceVerified':False}
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=14)
    args=parser.parse_args()
    limit=max(1,min(args.limit,60))
    now=dt.datetime.now(dt.timezone.utc)
    old={}
    if DEST.exists():
        try:old=json.loads(DEST.read_text()).get('byNotice',{})
        except (ValueError,OSError):pass
    selected=discover(limit,old)
    results=dict(old)
    # Preserve historical evidence while normalizing old ambiguous "unavailable"
    # entries with explicit zero-row API evidence. This is NOT proof that no RFP exists.
    for key,prior in results.items():
        if (prior.get('status')=='text_unavailable' and prior.get('count')==0
                and not prior.get('files')):
            prior['status']='no_eorder_files'
            prior['reasonCode']='eorder_api_returned_zero'
            prior['classificationVersion']=2
    success=0
    for no,ordn,_ in selected:
        key=no+':'+ordn
        cached=old.get(key)
        if cached:
            try:
                checked=dt.datetime.fromisoformat(cached.get('checkedAt','').replace('Z','+00:00'))
                if cached.get('classificationVersion')==3 and checked.tzinfo and (now-checked).total_seconds()<36*3600:
                    print('RFP_CACHE_HIT',key);continue
            except ValueError:pass
        try:
            data=process(no,ordn)
            data['checkedAt']=now.isoformat()
            data['classificationVersion']=3
            results[key]=data
            print('RFP_SCAN',key,data['status'],'FILES',len(data.get('files',[])))
            success+=int(data['status']=='text_extracted_requires_review')
        except Exception as e:
            reason=classify_failure(e)
            results[key]={'status':'metadata_fetch_failed','reasonCode':reason,
                          'source':'나라장터 e발주 첨부파일 API',
                          'sourceError':type(e).__name__+': '+str(e)[:100],
                          'files':[],'reviewComplete':False,
                          'contractPerformanceVerified':False,
                          'checkedAt':now.isoformat(),'classificationVersion':2}
            print('RFP_SCAN_ERROR',key,reason)
    if not results:raise SystemExit('NO_RFP_RESULT')
    output={'ok':True,'generatedAt':now.isoformat(),'scope':'공식 공고첨부 텍스트 발췌·키워드 근거(비최종판정)',
            'reviewComplete':False,'byNotice':dict(list(results.items())[-150:])}
    DEST.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('RFP_SNAPSHOT_READY','NOTICES',len(output['byNotice']),'NEW_READABLE',success)
if __name__=='__main__':main()
