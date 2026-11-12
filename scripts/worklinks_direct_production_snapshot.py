#!/usr/bin/env python3
"""Official data.go.kr direct-production certificate public CSV, server123 owned."""
import csv
import datetime as dt
import html
import io
import json
import os
import hashlib
from pathlib import Path
import re
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
PAGE='https://www.data.go.kr/data/3061008/fileData.do'
OUTPUT=ROOT/'startup-support/direct-production-snapshot.json'

def read(url):
    ledger=None
    request_key=None
    if os.environ.get('WORKLINKS_RFP_LEDGER_DB'):
        from rfp_call_ledger import CallLedger,cache_key
        ledger=CallLedger(os.environ['WORKLINKS_RFP_LEDGER_DB'])
        request_key=cache_key('direct_production_public_file',url)
        if url==PAGE:
            cached=ledger.get_bytes(request_key,max_age_seconds=6*3600)
            if cached is not None:
                ledger.record('direct_production',request_key,'verified_page_reused')
                return cached
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 (WorkLinks/123)',
                             'Referer':PAGE})
    try:
        with urlopen(req,timeout=65) as f:
            status=getattr(f,'status',200)
            raw=f.read(150000000)
        if status!=200:raise RuntimeError('DIRECT_PRODUCTION_HTTP_'+str(status))
        if ledger is not None:
            ledger.record('direct_production_http',request_key,'http_received',
                          http_status=status,
                          response_sha256=hashlib.sha256(raw).hexdigest(),
                          detail='bytes='+str(len(raw)))
            if url==PAGE:
                ledger.save_bytes(request_key,raw)
        return raw
    except Exception as exc:
        if ledger is not None:
            ledger.record('direct_production_http',request_key,'http_failed',
                          http_status=getattr(exc,'code',None),
                          error_class=type(exc).__name__)
        raise

def collect():
    webpage=read(PAGE).decode('utf-8')
    links=re.findall(r'https://www.data.go.kr/cmm/cmm/fileDownload.do[^"<> ]+',webpage)
    if not links:raise RuntimeError('CSV_URL_NOT_FOUND')
    raw=read(html.unescape(links[0]))
    for codec in ('utf-8-sig','cp949','euc-kr'):
        try:
            content=raw.decode(codec)
            break
        except UnicodeDecodeError:continue
    else:raise RuntimeError('CSV_ENCODING_FAILED')
    reader=csv.DictReader(io.StringIO(content))
    cols=set(reader.fieldnames or [])
    if not {'사업자번호','세부품명'}.issubset(cols):
        raise RuntimeError('INVALID_CSV_COLUMNS')
    source=(ROOT/'startup-support/index.html').read_text(encoding='utf-8')
    biznos=set(re.sub(r'\D','',n) for n in
               re.findall(r'businessNo:"([0-9-]{10,15})"',source))
    if not biznos:raise RuntimeError('PARTNER_LIST_EMPTY')
    rows={key:[] for key in sorted(biznos)}
    total=0
    for item in reader:
        total+=1
        num=re.sub(r'\D','',item.get('사업자번호') or '')
        if num not in rows:continue
        rows[num].append({'product':item.get('세부품명') or '',
                          'validFrom':item.get('유효기간 시작일') or '',
                          'validTo':item.get('유효기간 종료일') or ''})
    if total<20000:raise RuntimeError('INCOMPLETE_CSV_'+str(total))
    match=re.search(r'직접생산확인증명서발급현황_(\d{8})',webpage)
    if not match:raise RuntimeError('SOURCE_DATE_NOT_FOUND')
    stamp=match.group(1)
    return {'ok':True,'complete':True,'source':'중소벤처기업부 직접생산확인증명서발급현황',
            'sourceUrl':PAGE,'snapshotDate':stamp[:4]+'-'+stamp[4:6]+'-'+stamp[6:],
            'recordCount':total,'recordsByBizno':rows,
            'collectedAt':dt.datetime.now(dt.timezone.utc).isoformat()}

def main():
    result=collect()
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('WORKLINKS_SERVER123_DIRECT_PRODUCTION',result['recordCount'],flush=True)

if __name__=='__main__':main()
