#!/usr/bin/env python3
"""Official SMPP public SME certificate lookup, previously embedded in GitHub Actions."""
import datetime as dt
import html
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
PAGE='https://smpp.go.kr/cst/smppInf/selectMiddlSslentrSchtwrListVw.do'
OUTPUT=ROOT/'startup-support/sme-cert-snapshot.json'

def business_numbers(source):
    return sorted(set(re.sub(r'\D','',x) for x in
                      re.findall(r'businessNo:"([0-9-]{10,15})"',source)))

def official_lookup(bizno):
    ledger=None
    request_key=None
    if __import__('os').environ.get('WORKLINKS_RFP_LEDGER_DB'):
        from rfp_call_ledger import CallLedger,cache_key
        ledger=CallLedger(__import__('os').environ['WORKLINKS_RFP_LEDGER_DB'])
        request_key=cache_key('official_smpp_business',bizno)
        cached=ledger.get_json(request_key,max_age_seconds=12*3600)
        if isinstance(cached,dict) and cached.get('verified') is True:
            ledger.record('smpp',request_key,'verified_snapshot_reused')
            return cached.get('record')
    data=urlencode({'searchBsnmNo':bizno,'pageIndex':'1','menuId':'1050506','vCheck':'Y'}).encode()
    req=Request(PAGE,data=data,headers={
        'User-Agent':'Mozilla/5.0 (compatible; WorkLinks-Server123-SME/1.0)',
        'Content-Type':'application/x-www-form-urlencoded','Referer':PAGE})
    status=None
    try:
        with urlopen(req,timeout=35) as response:
            status=getattr(response,'status',200)
            if status!=200:raise RuntimeError('SMPP_HTTP_'+str(status))
            body=response.read(5000000).decode('utf-8')
        start=body.find('<div class="board list pc_tbl">')
        if start<0:raise RuntimeError('SMPP_DESKTOP_RESULTS_MISSING')
        table=body[start:body.find('</table>',start)]
        tb=re.search(r'<tbody[^>]*>(.*?)</tbody>',table,re.S|re.I)
        if not tb:raise RuntimeError('SMPP_TABLE_BODY_MISSING')
        found=[]
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>',tb.group(1),re.S|re.I):
            cells=[' '.join(html.unescape(re.sub(r'<[^>]*>',' ',c)).split())
                   for c in re.findall(r'<td[^>]*>(.*?)</td>',row,re.S|re.I)]
            if len(cells)>=5 and cells[3]:
                found.append({'company':cells[3],'agency':cells[1],
                              'issuedAt':cells[2],'size':cells[4]})
        if len(found)>1:raise RuntimeError('SMPP_AMBIGUOUS_RESULTS_'+bizno)
        record=found[0] if found else None
        if record and (record['agency']!='중소벤처기업부' or
                       record['size'] not in ('중기업','소기업','소상공인') or
                       not re.fullmatch(r'\d{4}-\d{2}-\d{2}',record['issuedAt'])):
            raise RuntimeError('SMPP_UNRECOGNIZED_RECORD_'+bizno)
        if record:record['validState']='valid'
    except Exception as exc:
        if ledger is not None:
            ledger.record('smpp_http',request_key,'http_or_parse_failed',
                          http_status=getattr(exc,'code',status),
                          error_class=type(exc).__name__)
        raise
    if ledger is not None:
        ledger.record('smpp_http',request_key,'http_verified',http_status=status)
        ledger.save_json(request_key,{'verified':True,'record':record})
    return record

def main():
    src=(ROOT/'startup-support/index.html').read_text(encoding='utf-8')
    biznos=business_numbers(src)
    if not biznos:raise RuntimeError('PARTNER_BUSINESS_NUMBERS_MISSING')
    records={}
    for bizno in biznos:
        records[bizno]=official_lookup(bizno)
        print('SMPP_OFFICIAL_LOOKUP',bizno,'found',bool(records[bizno]),flush=True)
        time.sleep(0.2)
    report={'ok':True,'checkedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
        'sourceUrl':PAGE,'scope':'공공입찰용 중소기업확인서 공개 조회',
        'validity':'SMPP 유효여부=Y 필터; 정확한 종료일은 공개 목록에 없음',
        'recordsByBizno':records}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('WORKLINKS_SERVER123_SME_CERT',len(records),flush=True)

if __name__=='__main__':main()
