#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""WorkLinks G2B API proxy. CentOS 7 / Python 2.7+ standard library only."""
from __future__ import print_function
import os, sys, re, json, time, datetime, threading, ssl, sqlite3, base64
try:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
    from SocketServer import ThreadingMixIn
    from urlparse import urlparse, parse_qs
    from urllib import urlencode
    from urllib2 import Request, urlopen, HTTPError, URLError
except ImportError:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from socketserver import ThreadingMixIn
    from urllib.parse import urlparse, parse_qs, urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

PORT = int(os.environ.get('PORT', '18191'))
QUAL_REPORT_PATH = os.environ.get('G2B_QUAL_REPORT', '/app/reports/qualification-year.json')
G2B_DB_PATH = os.environ.get('G2B_DB_PATH', '/home/worklinks/g2b/data/bids.sqlite3')
BIND_HOST = os.environ.get('BIND_HOST', '127.0.0.1')
TLS_CERT_FILE = os.environ.get('G2B_TLS_CERT_FILE', '').strip()
TLS_KEY_FILE = os.environ.get('G2B_TLS_KEY_FILE', '').strip()
SECRET_PATH = os.environ.get('G2B_SECRET_PATH', '/home/worklinks/g2b/secrets/g2b.env')
API_BASE = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService'
AWARD_BASE = 'https://apis.data.go.kr/1230000/as/ScsbidInfoService'
CONTRACT_BASE = 'https://apis.data.go.kr/1230000/ao/CntrctInfoService'
CONTRACT_PROCESS_BASE = 'https://apis.data.go.kr/1230000/ao/CntrctProcssIntgOpenService'
COMPANY_BASE = 'https://apis.data.go.kr/1230000/ao/UsrInfoService02'
BID_OPS = {
    'servc':'getBidPblancListInfoServcPPSSrch',
    'thng':'getBidPblancListInfoThngPPSSrch',
    'cnstwk':'getBidPblancListInfoCnstwkPPSSrch',
    'frgcpt':'getBidPblancListInfoFrgcptPPSSrch'
}
ORIGINS = ('https://worklinks.suaveforge.com', 'https://programmer119.github.io')
cache = {}
lock = threading.Lock()
award_fetch_lock = threading.Lock()  # serialize identical official award requests

def get_key():
    k = os.environ.get('G2B_SERVICE_KEY', '').strip()
    if k: return k
    try:
        with open(SECRET_PATH, 'r') as f:
            for line in f:
                if line.startswith('G2B_SERVICE_KEY='):
                    return line.split('=', 1)[1].strip()
    except (OSError, IOError): pass
    return ''

class ApiError(Exception):
    def __init__(self, msg, status=502):
        Exception.__init__(self, msg)
        self.msg, self.status = msg, status

def classify_upstream_http_error(e):
    """Return a safe status/error identifier; never expose raw gateway HTML, key or URL."""
    status=int(getattr(e,'code',502))
    try:
        response=e.read(3072)
        if not isinstance(response,str):response=response.decode('utf-8','ignore')
    except (OSError,IOError,UnicodeError):response=''
    known=('SERVICE_ACCESS_DENIED_ERROR','PERMISSION_DENIED',
           'SERVICE_KEY_IS_NOT_REGISTERED_ERROR','SERVICE_KEY_IS_NULL',
           'DEADLINE_HAS_EXPIRED_ERROR','LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR',
           'LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR',
           'INVALID_REQUEST_PARAMETER_ERROR','NO_OPENAPI_SERVICE_ERROR','HTTP_ERROR',
           'APPLICATION_ERROR','BLACKLIST_IP_ACCESS_ERROR')
    for value in known:
        if value in response.upper():
            return 'upstream_http_%s_%s'%(status,value)
    return 'upstream_http_%s'%status

def request_api(base, operation, params):
    token = get_key()
    if not token: raise ApiError('secret_not_configured', 503)
    args = {'serviceKey':token, 'type':'json'}
    args.update(params)
    url = base + '/' + operation + '?' + urlencode(args)
    # Share one circuit breaker among all requests for this upstream service.
    # During provider quota exhaustion do not multiply futile calls across notices.
    with lock:
        cooldown=cache.get(('upstream-rate-cooldown',base),0)
    if cooldown>time.time():raise ApiError('upstream_temporarily_rate_limited')
    try:
        response = urlopen(Request(url, headers={
            'Accept':'application/json', 'User-Agent':'WorkLinksG2B/1.0'
        }), timeout=14)
        raw = response.read()
    except HTTPError as e:
        error=classify_upstream_http_error(e)
        if (getattr(e,'code',0)==429 or
                'LIMITED_NUMBER_OF_SERVICE_REQUESTS' in error):
            with lock:
                cache[('upstream-rate-cooldown',base)]=time.time()+1800
        raise ApiError(error)
    except (URLError, IOError, ValueError): raise ApiError('upstream_unreachable')
    try: doc = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError): raise ApiError('upstream_not_json')
    # Bad request parameters may receive a valid HTTP 200 and a provider-specific
    # error envelope rather than the documented response/header structure.
    # Never interpret this response as an empty result or leak its free text.
    if not isinstance(doc,dict):raise ApiError('upstream_malformed_response')
    if 'nkoneps.com.response.ResponseError' in doc:
        raise ApiError('upstream_provider_response_error')
    envelope=doc.get('response')
    if not isinstance(envelope,dict):raise ApiError('upstream_malformed_response')
    hdr=envelope.get('header')
    if not isinstance(hdr,dict) or 'resultCode' not in hdr:
        raise ApiError('upstream_missing_result_code')
    rc = str(hdr['resultCode'])
    if rc not in ('00','0'): raise ApiError('upstream_result_' + re.sub(r'[^a-zA-Z0-9_]','',rc)[:20])
    body = envelope.get('body', {})
    items = body.get('items') or []
    if isinstance(items, dict): items = items.get('item') or []
    if not isinstance(items, list): items = [items]
    return {'items':items,'totalCount':int(body.get('totalCount') or len(items))}

def cached_awards_query(bid_no):
    """Cache a successful official historic award query by exact notice number."""
    key=('awards',bid_no)
    with lock: saved=cache.get(key)
    if saved and saved[0]>time.time():
        result=dict(saved[1]);result['cached']=True
        return result
    with award_fetch_lock:
        with lock: saved=cache.get(key)
        if saved and saved[0]>time.time():
            result=dict(saved[1]);result['cached']=True
            return result
        data=request_api(AWARD_BASE,'getScsbidListSttusServc',{
            'pageNo':1,'numOfRows':50,'inqryDiv':4,'bidNtceNo':bid_no})
        result={'ok':True,'totalCount':data['totalCount'],
                'items':data['items'],'cached':False}
        with lock: cache[key]=(time.time()+12*3600,result)
        return result


def format_bid(x, kind):
    def get(*keys):
        for k in keys:
            v = x.get(k)
            if v is not None and v != '': return v
        return ''
    link = get('bidNtceDtlUrl')
    return {'kind':kind,'bidNo':str(get('bidNtceNo')),'order':str(get('bidNtceOrd')),
            'title':get('bidNtceNm'),'org':get('ntceInsttNm','dminsttNm'),
            'agency':get('dminsttNm'),'posted':get('bidNtceDt'),
            'closes':get('bidClseDt'),'budget':get('asignBdgtAmt','presmptPrce'),
            'url':link if link and link.startswith('https://') else '',
            'state':get('bidNtceSttusNm'),'contract':get('cntrctCnclsMthdNm')}

def date(s):
    if not re.match(r'^\d{8}$', s): raise ApiError('invalid_date',400)
    try: return datetime.datetime.strptime(s,'%Y%m%d').date()
    except ValueError: raise ApiError('invalid_date',400)



def contract_capability_query():
    """Probe two documented services independently, without claiming completed work."""
    attempts=[]
    targets=[
        ('contract_info',CONTRACT_BASE,'getCntrctInfoListServc',{
            'pageNo':1,'numOfRows':1,'inqryDiv':1,
            'inqryBgnDt':'202610010000','inqryEndDt':'202610012359'}),
        ('contract_process',CONTRACT_PROCESS_BASE,'getCntrctProcssIntgOpenServc',{
            'pageNo':1,'numOfRows':1,'inqryDiv':1,'bidNtceNo':'R25BK00826083'})
    ]
    for name,base,operation,params in targets:
        try:
            data=request_api(base,operation,params)
            first=data['items'][0] if data['items'] else {}
            attempts.append({'service':name,'operation':operation,'ok':True,
                'schemaFields':sorted(first.keys()) if isinstance(first,dict) else [],
                'sampleCount':data['totalCount'],'error':''})
        except ApiError as e:
            attempts.append({'service':name,'operation':operation,'ok':False,
                             'error':e.msg,'schemaFields':[],'sampleCount':None})
    original,alternative=attempts
    denied=('ACCESS_DENIED' in original['error'] or 'PERMISSION_DENIED' in original['error'] or
            'upstream_http_403' in original['error'])
    return {'ok':original['ok'],'authorized':True if original['ok'] else
            (False if denied else None),
            'operation':original['operation'],'error':original['error'],
            'schemaFields':original['schemaFields'],'sampleCount':original['sampleCount'],
            'alternative':alternative,'probes':attempts,
            'officialContractInfoUrl':'https://www.data.go.kr/data/15129427/openapi.do',
            'officialContractProcessUrl':'https://www.data.go.kr/data/15129459/openapi.do',
            'companyHistoryVerified':False,'contractPerformanceVerified':False,
            'limitations':'인증·접근만 검사합니다. 낙찰, 계약, 검수, 수행완료, 실적증명은 서로 다릅니다.',
            'checkedAt':datetime.datetime.utcnow().isoformat()+'Z'}


def _contract_items(value):
    """Flatten response wrappers only; avoid interpreting bidder/winner as contractor."""
    if isinstance(value,str):
        try:value=json.loads(value)
        except (ValueError,TypeError):return []
    if isinstance(value,list):return [x for x in value if isinstance(x,dict)][:150]
    if isinstance(value,dict):
        for key in ('item','items','cntrctInfo','contract','contracts','corp','corps'):
            if key in value:return _contract_items(value[key])
        return [value]
    return []

def _contract_corp_records(value):
    """Parse only the official CntrctInfoService.corpList CONTRACTOR field.

    Official responses in October 2026 encode contractor rows as 10-column
    caret-separated text inside brackets: [...^<10-digit contractor bizno>].
    Never apply this decoder to a winning-bid / bidder / cntrctInfoList field.
    Unknown shapes remain unattributed rather than being guessed from names.
    """
    rows=_contract_items(value)
    if rows or not isinstance(value,str) or len(value)>65536:
        return rows
    result=[]
    for segment in re.findall(r'\[([^\[\]]{1,640})\]',value):
        fields=segment.split('^')
        if len(fields)!=10:continue
        registration=fields[9].strip()
        if re.fullmatch(r'\d{10}',registration):
            result.append({'corpBizno':registration})
        if len(result)>=150:break
    return result


def _contract_business_number(row):
    """Only explicitly named contractor/company registration fields are acceptable."""
    fields=('cntrctCorpBizno','cntrctCorpBizNo','cntrctEntrprsBizno',
            'cntrctEntrprsBizNo','cntrctCorpBrno','cntrctCorpBizrno',
            'cntrctEntrprsBrno','contractorBizno','bizno',
            'corpBizno','corpBizNo','corpBizrno','corpBrno',
            'corpBsnsRgstNo','bsnsRgstNo','entrprsBizno','entrprsBizNo')
    return [re.sub(r'\D','',str(row[k])) for k in fields
            if row.get(k) and len(re.sub(r'\D','',str(row[k])))==10]

def contract_evidence_query(bid_no,bizno):
    """Credit contracts ONLY after matching a contractor company registration ID.

    cntrctInfoList/corpList can be nested arrays or JSON strings.
    bidwinrInfoList proves a winning bid, not a contract, and is intentionally ignored.
    """
    params={'pageNo':1,'numOfRows':100,'inqryDiv':1,'bidNtceNo':bid_no}
    data=request_api(CONTRACT_PROCESS_BASE,'getCntrctProcssIntgOpenServc',params)
    complete=len(data['items'])>=data['totalCount']
    verified=[];unattributed=0;other=0;subrecords=0;subkeys=set()
    for row in data['items']:
        if not isinstance(row,dict):continue
        row_no=str(row.get('bidNtceNo') or row.get('bidPblancNo') or '')
        if row_no and row_no!=bid_no:continue
        raw=row.get('cntrctInfoList')
        entries=_contract_items(raw) if raw is not None else [row]
        # An empty contract list proves neither a contract nor nonperformance.
        if not entries:unattributed+=1;continue
        for entry in entries:
            subrecords+=1;subkeys.update(entry.keys())
            companyrows=[entry]
            for field in ('corpList','cntrctCorpList','cntrctEntrprsList'):
                companyrows.extend(_contract_items(entry.get(field)))
            ids=set(num for company in companyrows for num in _contract_business_number(company))
            if not ids:
                unattributed+=1
                continue
            if bizno not in ids:
                other+=1
                continue
            verified.append({
                'bidNo':bid_no,'companyBiznoMatched':True,
                'contractNo':_pick(entry,['cntrctNo','dcsnCntrctNo','cntrctRefNo']) or
                             _pick(row,['cntrctNo','dcsnCntrctNo','cntrctRefNo']),
                'title':_pick(entry,['cntrctNm','cntrctName','bidNtceNm']) or
                        _pick(row,['cntrctNm','cntrctName','bidNtceNm']),
                'date':_pick(entry,['cntrctCnclsDate','cntrctDate','cntrctDt']) or
                       _pick(row,['cntrctCnclsDate','cntrctDate','cntrctDt']),
                'amount':_pick(entry,['thtmCntrctAmt','cntrctAmt','totCntrctAmt']) or
                         _pick(row,['thtmCntrctAmt','cntrctAmt','totCntrctAmt']),
                'agency':_pick(entry,['cntrctInsttNm','dminsttNm','ntceInsttNm']) or
                         _pick(row,['cntrctInsttNm','dminsttNm','ntceInsttNm']),
                'performanceComplete':None,'inspectionComplete':None,'certificateAvailable':None
            })
    return {'ok':True,'bidNo':bid_no,'bizno':bizno,'totalCount':data['totalCount'],
            'complete':complete,'contracts':verified,'attributableCount':len(verified),
            'unattributedCount':unattributed,'otherCompanyCount':other,
            'nestedContractItems':subrecords,'nestedContractFields':sorted(subkeys),
            'schemaFields':sorted(data['items'][0].keys()) if data['items'] and isinstance(data['items'][0],dict) else [],
            'source':'나라장터 계약과정통합공개서비스',
            'contractPerformanceVerified':False,
            'limitations':'계약 기업정보의 명시된 사업자번호가 정확히 일치할 때만 귀속합니다. 낙찰정보만 일치하면 계약실적으로 귀속하지 않습니다. 이행완료·검수·실적증명은 별도 확인 필요.'}


def contract_notice_lookup(bid_no, bizno):
    """Public contracted work for an exact tender and exact company registration.

    Unlike winner listings, a contract is counted only when BOTH the notice
    reference and a named contractor registration number match. Missing fields
    or an empty result are unknown, not proof of no contract/performance.
    """
    # Verified against the actual official service 2026-10-17:
    # PPSSrch inqryDiv=4 uses "ntceNo", NOT bidNtceNo. The latter returned
    # {"nkoneps.com.response.ResponseError":...} with HTTP 200 for KADX.
    params={'pageNo':1,'numOfRows':100,'inqryDiv':4,'ntceNo':bid_no}
    try:
        data=request_api(CONTRACT_BASE,'getCntrctInfoListServcPPSSrch',params)
    except ApiError as e:
        return {'ok':False,'bidNo':bid_no,'contracts':[],'attributableCount':0,
                'complete':False,'error':e.msg,'source':'나라장터 계약정보서비스'}
    results=[]
    seen_contracts={}
    other=0;unattributed=0;duplicate_rows=0;conflicting_duplicates=0
    for row in data['items']:
        if not isinstance(row,dict):continue
        # ntceNo is the tender reference in the official contract list.
        no=_pick(row,['ntceNo','bidNtceNo','bidPblancNo'])
        if no!=bid_no:
            unattributed+=1
            continue
        entries=_contract_corp_records(row.get('corpList'))
        if not entries:
            unattributed+=1
            continue
        ids=set(num for ent in entries for num in _contract_business_number(ent))
        if not ids:
            unattributed+=1
            continue
        if bizno not in ids:
            other+=1
            continue
        number=_pick(row,['dcsnCntrctNo','cntrctNo','cntrctRefNo'])
        if not number:
            # An exact contractor identity without an identifiable contract
            # cannot be counted as a distinct signed contract.
            unattributed+=1
            continue
        record={
            'bidNo':bid_no,'companyBiznoMatched':True,'contractNo':number,
            'title':_pick(row,['cntrctNm','cntrctName']),
            'date':_pick(row,['cntrctCnclsDate','cntrctDate','cntrctDt']),
            'amount':_pick(row,['thtmCntrctAmt','totCntrctAmt','cntrctAmt']),
            'agency':_pick(row,['cntrctInsttNm','dminsttNm']),
            'contractPeriod':_pick(row,['cntrctPrd']),
            'performanceComplete':None,'inspectionComplete':None,
            'certificateAvailable':None}
        if number in seen_contracts:
            duplicate_rows+=1
            prior=seen_contracts[number]
            if prior['date']!=record['date'] or prior['amount']!=record['amount']:
                # The same contract number with divergent public values may
                # reflect an amendment. Do not choose a monetary figure blindly.
                conflicting_duplicates+=1
                prior['date']=''
                prior['amount']=''
                prior['dataConflict']=True
            continue
        seen_contracts[number]=record
        results.append(record)
    return {'ok':True,'bidNo':bid_no,'bizno':bizno,'contracts':results,
            'attributableCount':len(results),
            'uniqueContractNumbers':len(results),
            'duplicateContractRows':duplicate_rows,
            'conflictingDuplicateRows':conflicting_duplicates,
            'totalCount':data['totalCount'],
            'complete':len(data['items'])>=data['totalCount'],
            'unattributedCount':unattributed,'otherCompanyCount':other,
            'source':'나라장터 계약정보서비스 · 공고번호 및 계약업체번호 일치',
            'contractPerformanceVerified':False,
            'limitations':'중복 계약번호는 1건으로 집계. 동일 번호 상충 금액은 미확인. 계약 체결은 이행·검수·실적증명이 아님.'}


def _bid_evidence_fetch(operation, bid_no, order):
    """Public notice metadata. Missing API rows NEVER means unrestricted/qualified."""
    try:
        result=request_api(API_BASE,operation,{
            'pageNo':1,'numOfRows':100,'inqryDiv':2,
            'bidNtceNo':bid_no,'bidNtceOrd':order})
        if result['totalCount']>100:
            return {'ok':False,'complete':False,'error':'evidence_over_100_not_fetched',
                    'count':result['totalCount'],'items':[]}
        items=[]
        for row in result['items']:
            other=str(row.get('bidNtceNo') or '')
            if other and other!=bid_no:continue
            ordinal=str(row.get('bidNtceOrd') or '')
            if ordinal and ordinal.zfill(3)!=order:continue
            items.append(row)
        return {'ok':True,'complete':len(result['items'])>=result['totalCount'],
                'count':result['totalCount'],'items':items}
    except ApiError as e:
        return {'ok':False,'complete':False,'error':e.msg,'count':None,'items':[]}

def _notice_document_query(bid_no, order):
    """Second official path: notice detail's ntceSpecDocUrl1..10, not e-order files.

    This only fetches public metadata from a documented G2B notice-detail operation.
    Links are untrusted until download-time host, path and file-type validation.
    """
    result=_bid_evidence_fetch('getBidPblancListInfoServc',bid_no,order)
    items=[];seen=set();found_fields=set();pre_spec_no=''
    if result['ok'] and result['complete']:
        for row in result['items']:
            if not isinstance(row,dict):continue
            if not pre_spec_no:
                pre_spec_no=_pick(row,['bfSpecRgstNo'])
            for i in range(1,11):
                url=str(row.get('ntceSpecDocUrl'+str(i)) or '').strip()
                name=str(row.get('ntceSpecFileNm'+str(i)) or '').strip()
                if not url and not name:continue
                found_fields.add('ntceSpecDocUrl'+str(i))
                if not url or url in seen:continue
                seen.add(url)
                items.append({'name':name[:160] or ('입찰공고 첨부 '+str(i)),
                              'url':url,'source':'notice_detail',
                              'officialNoticeField':'ntceSpecDocUrl'+str(i)})
    return {'ok':result['ok'],'complete':result['complete'],
            'error':result.get('error',''),'noticeRows':result.get('count'),
            'items':items,'source':'나라장터 입찰공고 상세정보',
            'foundDocumentFields':sorted(found_fields),
            'preSpecificationNo':pre_spec_no[:40],
            'returnedRawFields':sorted(result['items'][0].keys())
               if result['items'] and isinstance(result['items'][0],dict) else []}


def _pick(row, names):
    for key in names:
        value=row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''

def _all_notice_changes(bid_no):
    """Read every version of this notice, not just the current bid ordinal."""
    try:
        data=request_api(API_BASE,'getBidPblancListInfoChgHstryServc',{
            'pageNo':1,'numOfRows':100,'inqryDiv':2,'bidNtceNo':bid_no})
        if data['totalCount']>100:
            return {'ok':False,'complete':False,'error':'change_history_over_100',
                    'count':data['totalCount'],'items':[]}
        exact=[x for x in data['items'] if isinstance(x,dict) and
               str(x.get('bidNtceNo') or '')==bid_no]
        return {'ok':True,'complete':len(data['items'])>=data['totalCount'],
                'error':'','count':data['totalCount'],'items':exact}
    except ApiError as e:
        return {'ok':False,'complete':False,'error':e.msg,
                'count':None,'items':[]}


def bid_change_and_price_query(bid_no,order):
    """Bounded official service-bid change history and base amount evidence.

    This endpoint does not interpret a returned numeric amount as an actual bid
    or create an 'unchanged' claim from empty/failed upstream responses.
    """
    changes=_all_notice_changes(bid_no)
    prices=_bid_evidence_fetch('getBidPblancListInfoServcBsisAmount',bid_no,order)
    history=[]
    for row in changes['items']:
        if not isinstance(row,dict):continue
        history.append({
            'order':_pick(row,['bidNtceOrd']),
            'changedAt':_pick(row,['chgDt','chgDate','bidNtceChgDt']),
            'reason':_pick(row,['chgRsn','chgRsnCn','chgRsnNm','chgResnCn'])[:220],
            'publicFields':sorted(row.keys())[:60]
        })
    amounts=[]
    for row in prices['items']:
        if not isinstance(row,dict):continue
        amount=_pick(row,['bssamt','bsisAmount','bssamtAmt','baseAmount'])
        if amount and not re.fullmatch(r'\d{1,17}(?:\.\d{1,2})?',amount.replace(',','')):
            amount=''
        amounts.append({
            'order':_pick(row,['bidNtceOrd']),'baseAmount':amount.replace(',',''),
            'publishedAt':_pick(row,['bssamtOpenDt','bssamtRgstrDt','rgstDt']),
            'publicFields':sorted(row.keys())[:60]
        })
    return {'ok':changes['ok'] or prices['ok'],'bidNo':bid_no,'order':order,
       'changeHistory':{'ok':changes['ok'],'complete':changes['complete'],
            'totalCount':changes['count'],'records':history,
            'error':changes.get('error','')},
       'baseAmount':{'ok':prices['ok'],'complete':prices['complete'],
            'totalCount':prices['count'],'records':amounts,
            'error':prices.get('error','')},
       'checkedAt':datetime.datetime.utcnow().isoformat()+'Z',
       'limitations':'변경내역 API 0건 또는 미조회는 변경 없음의 보증이 아님. 기초금액은 투찰금액·계약금액이 아님.'}


def bid_evidence_query(bid_no, order):
    regions=_bid_evidence_fetch('getBidPblancListInfoPrtcptPsblRgn',bid_no,order)
    attachments=_bid_evidence_fetch('getBidPblancListInfoEorderAtchFileInfo',bid_no,order)
    # Keep the two official origins distinct; a zero result from either is not
    # proof that the public notice has no RFP/statement of work.
    notice_docs=_notice_document_query(bid_no,order)
    normalized_regions=[]
    for row in regions['items']:
        name=_pick(row,['prtcptPsblRgnNm','prtcptPsblRgnCdNm','rgnNm','rgnName'])
        code=_pick(row,['prtcptPsblRgnCd','rgnCd','rgnCode'])
        if name or code:normalized_regions.append({'name':name,'code':code})
    normalized_attachments=[]
    for row in attachments['items']:
        name=_pick(row,['atchFileNm','atchFileName','fileNm','fileName','eorderAtchFileNm'])
        url=_pick(row,['atchFileUrl','atchFileInfoUrl','fileUrl','fileDownloadUrl','eorderAtchFileUrl'])
        # Links must remain official HTTPS URLs; never convert arbitrary API strings into a link.
        if url and not re.match(r'^https://',url,re.I):url=''
        if name or url:normalized_attachments.append({'name':name,'url':url})
    for item in notice_docs['items']:
        url=item.get('url') or ''
        if url and url not in set(x.get('url') or '' for x in normalized_attachments):
            normalized_attachments.append(item)
    return {
        'ok':regions['ok'] or attachments['ok'] or notice_docs['ok'],'bidNo':bid_no,'order':order,
        'region':{'ok':regions['ok'],'complete':regions['complete'],
                  'count':regions['count'],'items':normalized_regions,
                  'rawFields':sorted(regions['items'][0].keys()) if regions['items'] else [],
                  'error':regions.get('error','')},
        'attachments':{'ok':attachments['ok'] or notice_docs['ok'],
                       'complete':attachments['complete'] or notice_docs['complete'],
                       'count':len(normalized_attachments),'items':normalized_attachments,
                       'eorderCount':attachments['count'],
                       'noticeDetailDocumentCount':len(notice_docs['items']),
                       'rawFields':sorted(attachments['items'][0].keys()) if attachments['items'] else [],
                       'error':attachments.get('error','') if not notice_docs['ok'] else ''},
        'noticeDocuments':notice_docs,
        'checkedAt':datetime.datetime.utcnow().isoformat()+'Z',
        'limitations':'공고 원문 첨부 미열람. 지역조회 0건은 전국 허용 증명이 아님.'
    }

# Persistent storage for all returned G2B notices (not just SW-title hits).
# The UI applies SW-related relevance filtering, so persistence never discards
# notices that appeared on the user's screen.
# Discovery only: title/subject match is a candidate, not a verified bid qualification.
SW_TERMS=re.compile(u'(소프트웨어|정보.?시스템|통합.?시스템|시스템|인공지능|머신러닝|딥러닝|기계학습|LLM|RAG|AI|ICT|IT서비스|빅데이터|데이터|데이타|디비|DB|정보화|디지털|전자문서|전자세금계산서|플랫폼|웹사이트|홈페이지|웹서비스|웹페이지|클라우드|서버|네트워크|인터넷|앱개발|모바일앱|애플리케이션|어플리케이션|SW|S/W|CCTV|보안솔루션|정보보호|사이버보안|API|GIS|ERP|CRM|RPA|메타버스|VR|AR|블록체인|영상인식|OCR|디지털콘텐츠)',re.I)
SW_BOUNDARY=re.compile(r'\b(IT|AI|DB|SW|API|ICT|ERP|CRM|RPA|LLM|RAG|GIS|OCR)\b',re.I)
def sw_candidate(bid):
    text=bid.get('title') or ''
    subjects=bid.get('purchsObjPrdctList') or ''
    if isinstance(subjects,(list,dict)):
        subjects=json.dumps(subjects,ensure_ascii=False)
    title=u'%s %s'%(text,subjects)
    return bool(SW_TERMS.search(title) or SW_BOUNDARY.search(title))

def open_bid_db():
    parent = os.path.dirname(G2B_DB_PATH)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    con = sqlite3.connect(G2B_DB_PATH, timeout=15)
    con.execute('PRAGMA busy_timeout=15000')
    con.execute('CREATE TABLE IF NOT EXISTS bid_notices (kind TEXT NOT NULL, bid_no TEXT NOT NULL, bid_ord TEXT NOT NULL, payload TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, PRIMARY KEY (kind,bid_no,bid_ord))')
    con.execute('CREATE INDEX IF NOT EXISTS bid_notices_seen_idx ON bid_notices(last_seen DESC)')
    fields=[row[1] for row in con.execute('PRAGMA table_info(bid_notices)').fetchall()]
    if 'sw_candidate' not in fields:
        con.execute('ALTER TABLE bid_notices ADD COLUMN sw_candidate INTEGER NOT NULL DEFAULT 0')
        rows=con.execute('SELECT kind,bid_no,bid_ord,payload FROM bid_notices').fetchall()
        with con:
            for kind,no,order,payload in rows:
                try: found=sw_candidate(json.loads(payload))
                except (TypeError,ValueError): found=False
                con.execute('UPDATE bid_notices SET sw_candidate=? WHERE kind=? AND bid_no=? AND bid_ord=?',
                            (int(found),kind,no,order))
    con.execute('CREATE INDEX IF NOT EXISTS bid_notices_sw_seen_idx ON bid_notices(sw_candidate,last_seen DESC)')
    con.execute('CREATE TABLE IF NOT EXISTS bid_license_cache (bid_no TEXT NOT NULL,bid_ord TEXT NOT NULL,payload TEXT NOT NULL,checked_at TEXT NOT NULL,PRIMARY KEY(bid_no,bid_ord))')
    return con

def persist_bids(items):
    now = datetime.datetime.utcnow().isoformat()+'Z'
    changed=0
    con=open_bid_db()
    try:
        with con:
            for x in items:
                kind=str(x.get('kind') or '')[:12]
                no=str(x.get('bidNo') or '')[:60]
                order=str(x.get('order') or '0')[:12]
                if kind not in BID_OPS or not no:
                    continue
                payload=json.dumps(x, ensure_ascii=False, separators=(',',':'))
                con.execute('INSERT OR IGNORE INTO bid_notices (kind,bid_no,bid_ord,payload,first_seen,last_seen) VALUES (?,?,?,?,?,?)',(kind,no,order,payload,now,now))
                con.execute('UPDATE bid_notices SET payload=?,last_seen=?,sw_candidate=? WHERE kind=? AND bid_no=? AND bid_ord=?',(payload,now,int(sw_candidate(x)),kind,no,order))
                changed+=1
            total=con.execute('SELECT COUNT(*) FROM bid_notices').fetchone()[0]
        return {'received':changed,'storedTotal':total}
    finally:
        con.close()

def query_saved_bids(limit,offset,only_sw=False):
    con=open_bid_db()
    try:
        total=con.execute('SELECT COUNT(*) FROM bid_notices').fetchone()[0]
        matching=con.execute('SELECT COUNT(*) FROM bid_notices WHERE sw_candidate=1').fetchone()[0]
        history=bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recurring_projects'").fetchone())
        sel='b.payload'+(',r.history_json,r.repeat_years' if history else ',NULL,0')+',q.payload'
        from_sql=' FROM bid_notices b '
        if history:
            from_sql+='LEFT JOIN recurring_projects r ON b.kind=r.kind AND b.bid_no=r.bid_no '
        # Notice ordinal is sometimes stored as "0" while eligibility uses "000".
        # Join on the normalized ordinal without mutating existing DB primary keys.
        from_sql+="LEFT JOIN bid_license_cache q ON b.bid_no=q.bid_no AND q.bid_ord=printf('%03d',CAST(b.bid_ord AS INTEGER)) "
        where='WHERE b.sw_candidate=1 ' if only_sw else ''
        rows=con.execute('SELECT '+sel+from_sql+where+
            'ORDER BY b.last_seen DESC,b.kind,b.bid_no DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        items=[]
        for payload,series,years,qualification in rows:
            obj=json.loads(payload)
            if series and (years or 0)>=2:
                try:
                    obj['repeatHistory']=json.loads(series)
                    obj['repeatYears']=int(years)
                except (ValueError,TypeError): pass
            if qualification:
                try: obj['bidEligibility']=json.loads(qualification)
                except (ValueError,TypeError): pass
            items.append(obj)
        checked=con.execute('SELECT COUNT(*) FROM bid_license_cache').fetchone()[0]
        linked=con.execute("SELECT COUNT(*) FROM bid_notices b INNER JOIN bid_license_cache q "
            "ON b.bid_no=q.bid_no AND q.bid_ord=printf('%03d',CAST(b.bid_ord AS INTEGER)) "
            "WHERE b.sw_candidate=1").fetchone()[0]
        return {'ok':True,'items':items,'totalCount':matching if only_sw else total,
                'storedTotal':total,'candidateTotal':matching,'eligibilityChecked':checked,
                'eligibilityLinked':linked,
                'limit':limit,'offset':offset,'persisted':True}
    finally:con.close()


def cached_historic_awards(limit=200,offset=0):
    """Read-only public snapshot: the worker stores exact positive official awards."""
    db=open_bid_db()
    try:
        table=db.execute("SELECT 1 FROM sqlite_master WHERE name='bid_award_cache' AND type='table'").fetchone()
        now=datetime.datetime.utcnow().isoformat()+'Z'
        empty={'ok':True,'installed':False,'schemaVersion':1,
               'source':'나라장터 낙찰정보서비스','verifiedAt':now,'totalCount':0,
               'records':[],'persisted':True}
        if not table:return empty
        cutoff=(datetime.datetime.utcnow()-datetime.timedelta(days=45)).isoformat()+'Z'
        total=db.execute('SELECT COUNT(*) FROM bid_award_cache WHERE checked_at>=?',(cutoff,)).fetchone()[0]
        rows=db.execute('''SELECT bid_no,payload,checked_at FROM bid_award_cache
          WHERE checked_at>=? ORDER BY checked_at DESC,bid_no LIMIT ? OFFSET ?''',
          (cutoff,limit,offset)).fetchall()
        records=[]
        for no,payload,checked in rows:
            try:
                row=json.loads(payload)
                if row.get('bidNo')!=no or int(row.get('count') or 0)<=0:continue
                row['verifiedAt']=checked
                records.append(row)
            except (ValueError,TypeError,AttributeError):pass
        empty.update({'installed':True,'totalCount':total,
                      'records':records,'limit':limit,'offset':offset})
        return empty
    finally:db.close()


def award_enricher_status():
    """Aggregated worker telemetry; never return raw upstream response fields."""
    db=open_bid_db()
    try:
        table=db.execute("SELECT 1 FROM sqlite_master WHERE name='bid_award_worker_status' AND type='table'").fetchone()
        if not table:return {'ok':True,'installed':False,'state':'not_installed'}
        info=db.execute('''SELECT last_run,last_success,requests_last_run,
          stored_last_run,errors_last_run,cooldown_until,message
          FROM bid_award_worker_status WHERE id=1''').fetchone()
        total=db.execute('SELECT COUNT(*) FROM bid_award_cache').fetchone()[0]
        deferred=db.execute('SELECT COUNT(*) FROM bid_award_attempts WHERE retry_after>?',
          (datetime.datetime.utcnow().isoformat()+'Z',)).fetchone()[0]
        return {'ok':True,'installed':True,'state':info[6] if info else 'initialized',
          'lastRun':info[0] if info else None,'lastSuccess':info[1] if info else None,
          'requestsLastRun':info[2] if info else 0,'storedLastRun':info[3] if info else 0,
          'errorsLastRun':info[4] if info else 0,'cooldownUntil':info[5] if info else None,
          'verifiedAwards':total,'deferredUnknowns':deferred}
    finally:db.close()


def crawler_state():
    con=open_bid_db()
    try:
        rows=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crawl_status'").fetchall()
        if not rows:
            return {'ok':True,'installed':False,'state':'not_installed',
                    'storedTotal':con.execute('SELECT COUNT(*) FROM bid_notices').fetchone()[0]}
        meta=con.execute('SELECT state,run_started,run_finished,last_success,request_count,error_count,message FROM crawl_status WHERE id=1').fetchone()
        windows=con.execute('SELECT COUNT(*),SUM(received),MAX(checked_at) FROM crawl_windows').fetchone()
        count=con.execute('SELECT COUNT(*) FROM bid_notices').fetchone()[0]
        candidates=con.execute('SELECT COUNT(*) FROM bid_notices WHERE sw_candidate=1').fetchone()[0]
        return {'ok':True,'installed':True,'state':meta[0] if meta else 'unknown',
                'runStarted':meta[1] if meta else None,'runFinished':meta[2] if meta else None,
                'lastSuccess':meta[3] if meta else None,
                'requestsLastRun':meta[4] if meta else 0,'errorsLastRun':meta[5] if meta else 0,
                'message':meta[6] if meta else None,'windowsChecked':windows[0],
                'noticesReadAcrossWindows':windows[1] or 0,'lastWindowCheck':windows[2],
                'storedTotal':count,'candidateTotal':candidates}
    finally:con.close()


# Direct-production confirmation dataset snapshot (NOT current SMPP status).
PROD_API = 'https://api.odcloud.kr/api/3061008/v1/uddi:98e7ddf2-e720-43af-b2eb-b92f4f65b0b5'
PROD_SNAPSHOT = '2026-02-01'

def prod_field(row,*names):
    fields=dict((re.sub(r'\s+','',str(k)),v) for k,v in row.items())
    for name in names:
        value=fields.get(re.sub(r'\s+','',name))
        if value is not None and str(value).strip():return str(value).strip()
    return ''

def prod_date(value):
    value=str(value or '').strip()
    if not value:return ''
    numbers=re.sub(r'\D','',value)
    if len(numbers)!=8:return value
    try:return datetime.datetime.strptime(numbers,'%Y%m%d').strftime('%Y-%m-%d')
    except ValueError:return value

def prod_normalize(rows,bizno):
    result=[]
    for row in rows:
        if not isinstance(row,dict):raise ApiError('production_invalid_row',502)
        number=re.sub(r'\D','',prod_field(row,'사업자번호','사업자등록번호','사업자 등록번호'))
        if not number:raise ApiError('production_missing_business_number',502)
        if number!=bizno:raise ApiError('production_filter_mismatch',502)
        product=prod_field(row,'세부품목','세부품목명','세부품명')
        code=prod_field(row,'세부품명번호','세부품목번호','세부품명코드')
        if not code:
            m=re.search(r'(?<!\d)\d{10}(?!\d)',product)
            code=m.group(0) if m else ''
        result.append({
            'company':prod_field(row,'업체명','기업명'),
            'product':product,'productCode':code,
            'validFrom':prod_date(prod_field(row,'유효기간 시작일','유효기간시작일')),
            'validTo':prod_date(prod_field(row,'유효기간 종료일','유효기간종료일'))
        })
    return result

def prod_query(bizno):
    key=get_key()
    if not key:raise ApiError('secret_not_configured',503)
    rows=[]
    match_count=None
    for page in range(1,21):
        url=PROD_API+'?'+urlencode({'serviceKey':key,'page':page,'perPage':1000,
                                     'cond['+u'사업자번호'+'::EQ]':bizno})
        try:
            response=urlopen(Request(url,headers={'Accept':'application/json',
                                      'User-Agent':'WorkLinksProduction/1.0'}),timeout=18)
            doc=json.loads(response.read().decode('utf-8'))
        except HTTPError as e:raise ApiError('production_upstream_http_'+str(e.code),502)
        except (URLError,IOError,ValueError,UnicodeError):
            raise ApiError('production_upstream_unavailable_or_invalid',502)
        if not isinstance(doc,dict) or not isinstance(doc.get('data'),list):
            raise ApiError('production_upstream_unexpected_response',502)
        batch=doc['data']
        if match_count is None:
            try:match_count=int(doc.get('matchCount',len(batch)))
            except (TypeError,ValueError):raise ApiError('production_invalid_match_count',502)
            if match_count<0:raise ApiError('production_invalid_match_count',502)
        rows.extend(prod_normalize(batch,bizno))
        if len(rows)>=match_count:break
        if not batch:raise ApiError('production_incomplete_result',502)
    if len(rows)<match_count:raise ApiError('production_exceeded_page_limit',502)
    return {'ok':True,'bizno':bizno,'found':bool(rows),'recordCount':len(rows),
            'complete':True,'records':rows,'snapshotDate':PROD_SNAPSHOT,
            'checkedAt':datetime.datetime.utcnow().isoformat()+'Z',
            'source':'중소벤처기업부 직접생산확인증명서 발급현황',
            'limitations':'2026-02-01 스냅샷. 현재 인증 유효상태는 SMPP에서 확인 필요.'}


# WorkLinks account-scoped preferences. AuthHub verifies the JWT; G2B's
# public bid key must never grant access to personal account state.
WORKLINKS_STATE_DB = os.environ.get(
    'WORKLINKS_STATE_DB', os.path.join(os.path.dirname(G2B_DB_PATH), 'user-state.sqlite3'))
AUTHHUB_ORIGIN = 'https://api-authhub.suaveforge.com'
AUTH_STATE_KINDS = ('applied', 'hidden', 'business')

def worklinks_auth_project():
    """MONITOR pNN project ID must be registered before login is enabled."""
    project = os.environ.get('WORKLINKS_AUTHHUB_PROJECT', '').strip()
    if not project:
        try:
            with open(SECRET_PATH, 'r') as config_file:
                for line in config_file:
                    if line.startswith('WORKLINKS_AUTHHUB_PROJECT='):
                        project = line.split('=', 1)[1].strip()
                        break
        except (OSError, IOError):
            pass
    return project if re.match(r'^p[1-9][0-9]*$', project) else ''

def worklinks_verify_identity(authorization):
    project = worklinks_auth_project()
    if not project:
        raise ApiError('authhub_project_not_configured', 503)
    if not re.match(r'^Bearer [A-Za-z0-9._~-]+$', authorization or ''):
        raise ApiError('auth_required', 401)
    token = authorization.split(' ', 1)[1]
    # AuthHub /v1/me validates this exact token's RS256 signature and expiry.
    try:
        req = Request(AUTHHUB_ORIGIN+'/v1/me', headers={
            'Authorization': 'Bearer '+token, 'Accept': 'application/json'})
        r = urlopen(req, timeout=7)
        info = json.loads(r.read(16384).decode('utf-8'))
    except HTTPError as error:
        if error.code in (401, 403, 404):
            raise ApiError('invalid_authhub_session', 401)
        raise ApiError('authhub_unavailable', 503)
    except (URLError, ValueError, OSError, IOError):
        raise ApiError('authhub_unavailable', 503)
    try:
        payload = token.split('.')[1]
        payload += '=' * ((-len(payload)) % 4)
        claim = json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
        user = info.get('user') or {}
        membership = info.get('membership') or {}
        subject = str(user.get('id') or '')
        valid = (str(claim.get('sub')) == subject
                 and str(claim.get('project')) == project
                 and str(claim.get('exp', 0)).isdigit()
                 and int(claim['exp']) > time.time()
                 and str(membership.get('status') or '').lower() == 'active')
        if not valid or not re.match(r'^[a-zA-Z0-9_-]{8,128}$', subject):
            raise ValueError('mismatched identity')
    except (ValueError, IndexError, TypeError, KeyError):
        raise ApiError('invalid_authhub_membership', 403)
    return project, subject

def worklinks_db():
    con = sqlite3.connect(WORKLINKS_STATE_DB, timeout=8)
    con.execute('PRAGMA busy_timeout=8000')
    con.execute('''CREATE TABLE IF NOT EXISTS worklinks_preferences (
        project TEXT NOT NULL, user_id TEXT NOT NULL,
        item_id TEXT NOT NULL, kind TEXT NOT NULL, enabled INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(project, user_id, item_id, kind))''')
    return con

def worklinks_state_get(project, user_id):
    db = worklinks_db()
    try:
        rows = db.execute(
            'SELECT item_id,kind,enabled,title,url,updated_at FROM worklinks_preferences '
            'WHERE project=? AND user_id=? ORDER BY updated_at',
            (project, user_id)).fetchall()
        return {'ok': True, 'records': [
            {'id': r[0], 'kind': r[1], 'value': bool(r[2]),
             'title': r[3], 'url': r[4], 'updatedAt': r[5]} for r in rows]}
    finally:
        db.close()

def worklinks_state_put(project, user_id, data):
    item_id = data.get('id')
    kind = data.get('kind')
    value = data.get('value')
    if not isinstance(item_id, str) or not re.match(r'^[a-zA-Z0-9_.:-]{1,160}$', item_id):
        raise ApiError('invalid_item_id', 400)
    if kind not in AUTH_STATE_KINDS or not isinstance(value, bool):
        raise ApiError('invalid_state', 400)
    title = str(data.get('title') or '')[:180]
    url = str(data.get('url') or '')[:600]
    if url and not url.startswith(('https://', 'http://')):
        url = ''
    stamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    db = worklinks_db()
    try:
        with db:
            db.execute('''INSERT OR REPLACE INTO worklinks_preferences
                (project,user_id,item_id,kind,enabled,title,url,updated_at)
                VALUES(?,?,?,?,?,?,?,?)''',
                (project, user_id, item_id, kind, int(value), title, url, stamp))
        return {'ok': True, 'id': item_id, 'kind': kind, 'value': value, 'updatedAt': stamp}
    finally:
        db.close()

class ThreadedServer(ThreadingMixIn,HTTPServer):
    daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        origin = self.headers.get('Origin','')
        if origin in ORIGINS:
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type')
            self.send_header('Vary','Origin')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.reply(200,{'ok':True})

    def do_GET(self):
        u = urlparse(self.path)
        p = parse_qs(u.query)
        def get(name, default=''): return p.get(name,[default])[0]
        try:
            if u.path in ('/health','/api/g2b/status'):
                return self.reply(200,{'ok':True,'service':'worklinks-g2b-python',
                    'configured':bool(get_key()),'server_time':datetime.datetime.utcnow().isoformat()+'Z'})
            if u.path == '/api/g2b/worklinks-auth-config':
                project = worklinks_auth_project()
                return self.reply(200, {'ok':True,'project':project,'enabled':bool(project),
                    'authApi':AUTHHUB_ORIGIN,'hostedLogin':'https://authhub.suaveforge.com/login/'})
            if u.path == '/api/g2b/worklinks-state':
                project, user_id = worklinks_verify_identity(self.headers.get('Authorization', ''))
                return self.reply(200, worklinks_state_get(project, user_id))
            if not get_key(): raise ApiError('secret_not_configured',503)
            if u.path == '/api/g2b/crawl-status':
                return self.reply(200,crawler_state())
            if u.path == '/api/g2b/award-cache':
                try: limit,offset=int(get('limit','200')),int(get('offset','0'))
                except ValueError:raise ApiError('invalid_award_cache_pagination',400)
                if not (1<=limit<=200 and 0<=offset<=10000):
                    raise ApiError('invalid_award_cache_pagination',400)
                return self.reply(200,cached_historic_awards(limit,offset))
            if u.path == '/api/g2b/award-cache-status':
                return self.reply(200,award_enricher_status())
            if u.path == '/api/g2b/saved':
                try: limit,offset=int(get('limit','500')),int(get('offset','0'))
                except ValueError: raise ApiError('invalid_saved_pagination',400)
                if not (1<=limit<=500 and 0<=offset<=100000):
                    raise ApiError('invalid_saved_pagination',400)
                return self.reply(200,query_saved_bids(limit,offset,get('sw','0')=='1'))
            if u.path == '/api/g2b/qualifications':
                # Aggregated public counts, no keys or raw sensitive data in report.
                try:
                    with open(QUAL_REPORT_PATH, 'r') as f:
                        report = json.load(f)
                except (OSError, IOError, ValueError):
                    raise ApiError('annual_report_not_available', 503)
                if not isinstance(report, dict) or not isinstance(report.get('counts'), list):
                    raise ApiError('annual_report_invalid', 503)
                return self.reply(200, {'ok':True, 'report':report})
            if u.path == '/api/g2b/direct-production':
                bizno=re.sub(r'\D','',get('bizno'))
                if len(bizno)!=10:raise ApiError('invalid_bizno',400)
                ck=('direct-production',bizno)
                with lock:saved=cache.get(ck)
                if saved and saved[0]>time.time():return self.reply(200,saved[1])
                result=prod_query(bizno)
                with lock:cache[ck]=(time.time()+6*3600,result)
                return self.reply(200,result)
            if u.path == '/api/g2b/company':
                bizno = re.sub(r'[^0-9]', '', get('bizno'))
                if len(bizno) != 10:
                    raise ApiError('invalid_bizno', 400)
                ck = ('company', bizno)
                with lock: saved = cache.get(ck)
                if saved and saved[0] > time.time():
                    return self.reply(200, saved[1])
                basic = request_api(COMPANY_BASE, 'getPrcrmntCorpBasicInfo02', {
                    'pageNo':1, 'numOfRows':30, 'inqryDiv':3, 'bizno':bizno
                })
                industry = request_api(COMPANY_BASE, 'getPrcrmntCorpIndstrytyInfo02', {
                    'pageNo':1, 'numOfRows':100, 'inqryDiv':1, 'bizno':bizno
                })
                # Complete official industry registry, not only its first page.
                industry_rows=list(industry['items'])
                industry_total=industry['totalCount']
                for page in range(2,min((industry_total+99)//100,20)+1):
                    nxt=request_api(COMPANY_BASE, 'getPrcrmntCorpIndstrytyInfo02', {
                        'pageNo':page,'numOfRows':100,'inqryDiv':1,'bizno':bizno
                    })
                    industry_rows.extend(nxt['items'])
                # Company/industry API can omit bizno in response rows even when
                # request was filtered by bizno. Preserve explicitly mismatched rows
                # as exclusions, but do not silently discard filtered no-bizno rows.
                def from_requested_company(x):
                    returned=re.sub(r'[^0-9]','',str(x.get('bizno') or x.get('bsnsRgstNo') or ''))
                    return not returned or returned==bizno
                matching = [x for x in basic['items'] if from_requested_company(x) and x.get('corpNm')]
                codes = [
                    {'code':str(x.get('indstrytyCd') or ''),
                     'name':x.get('indstrytyNm') or '',
                     'status':x.get('indstrytyStatsNm') or x.get('indstrytySttusNm') or x.get('statusName') or '',
                     'registeredAt':x.get('rgstDt') or '',
                     'expiresAt':x.get('vldPrdExprtDt') or x.get('expiryDate') or '',
                     'representative':str(x.get('rprsntIndstrytyYn') or '')}
                    for x in industry_rows
                    if from_requested_company(x) and re.fullmatch(r'\d{4}',str(x.get('indstrytyCd') or ''))
                ]
                result = {
                    'ok':True, 'bizno':bizno, 'found':bool(matching),
                    'company':{'name':matching[0].get('corpNm') or '',
                               'registeredAt':matching[0].get('rgstDt') or '',
                               'address':_pick(matching[0],['adrs','corpBscAddr','corpBscAdr','corpAddr','addr','address','prcrmntCorpBscAdr','prcrmntCorpBscAddr','prcrmntCorpAddr']),
                               'addressDetail':_pick(matching[0],['dtlAdrs']),
                               'regionName':_pick(matching[0],['rgnNm']),
                               'regionCode':_pick(matching[0],['rgnCd']),
                               'employeeCount':_pick(matching[0],['emplyeNum']),
                               'headOfficeKind':_pick(matching[0],['hdoffceDivNm']),
                               'addressField':next((key for key in ['adrs','corpBscAddr','corpBscAdr','corpAddr','addr','address','prcrmntCorpBscAdr','prcrmntCorpBscAddr','prcrmntCorpAddr'] if matching[0].get(key)), ''),
                               'availableFields':sorted(matching[0].keys())
                              } if matching else None,
                    'industries':codes, 'industryCount':industry_total,
                    'unattributedResponseRows':sum(1 for x in industry_rows if not x.get('bizno') and not x.get('bsnsRgstNo')),
                    'complete':len(industry_rows) >= industry_total,
                    'has1468':any(x['code']=='1468' for x in codes),
                    'source':'나라장터 사용자정보서비스',
                    'checkedAt':datetime.datetime.utcnow().isoformat()+'Z'
                }
                with lock: cache[ck] = (time.time()+3600, result)
                return self.reply(200,result)
            if u.path == '/api/g2b/contract-capability':
                ck=('contract-capability',)
                with lock:
                    saved=cache.get(ck)
                    refresh_key=('contract-refresh-throttle',)+ck
                    throttle=cache.get(refresh_key)
                    # Only bypass FAILED cached responses; successful results remain
                    # immutable until TTL. Prevent unbounded public upstream refresh.
                    forced=(get('refresh','')=='1' and
                            (not saved or saved[1].get('ok') is False) and
                            (not throttle or throttle[0]<time.time()))
                    if forced:cache[refresh_key]=(time.time()+120,None)
                if saved and saved[0]>time.time() and not forced:
                    return self.reply(200,saved[1])
                try:result=contract_capability_query()
                except ApiError as e:
                    result={'ok':False,'authorized':None,'error':e.msg,
                            'service':'조달청 나라장터 계약정보서비스',
                            'applicationUrl':'https://www.data.go.kr/data/15129427/openapi.do',
                            'companyHistoryVerified':False}
                with lock:cache[ck]=(time.time()+3600,result)
                return self.reply(200,result)
            if u.path == '/api/g2b/contract-evidence':
                bid_no=get('bidNo').strip()
                bizno=re.sub(r'\\D','',get('bizno').strip())
                if not re.fullmatch(r'[a-zA-Z0-9-]{8,40}',bid_no) or len(bizno)!=10:
                    raise ApiError('invalid_contract_lookup',400)
                ck=('contract-evidence',bid_no,bizno)
                with lock:
                    saved=cache.get(ck)
                    refresh_key=('contract-refresh-throttle',)+ck
                    throttle=cache.get(refresh_key)
                    forced=(get('refresh','')=='1' and
                            (not saved or saved[1].get('ok') is False) and
                            (not throttle or throttle[0]<time.time()))
                    if forced:cache[refresh_key]=(time.time()+120,None)
                if saved and saved[0]>time.time() and not forced:
                    return self.reply(200,saved[1])
                try:result=contract_evidence_query(bid_no,bizno)
                except ApiError as e:
                    result={'ok':False,'bidNo':bid_no,'bizno':bizno,'error':e.msg,
                            'contractPerformanceVerified':False,
                            'officialUrl':'https://www.data.go.kr/data/15129459/openapi.do'}
                with lock:cache[ck]=(time.time()+6*3600,result)
                return self.reply(200,result)
            if u.path == '/api/g2b/contract-notice':
                bid_no=get('bidNo').strip()
                bizno=re.sub(r'\D','',get('bizno').strip())
                if not re.fullmatch(r'[a-zA-Z0-9-]{8,40}',bid_no) or len(bizno)!=10:
                    raise ApiError('invalid_contract_lookup',400)
                ck=('contract-notice',bid_no,bizno)
                with lock:saved=cache.get(ck)
                if saved and saved[0]>time.time():return self.reply(200,saved[1])
                result=contract_notice_lookup(bid_no,bizno)
                with lock:cache[ck]=(time.time()+(24*3600 if result.get('ok') else 1200),result)
                return self.reply(200,result)
            if u.path == '/api/g2b/bid-change-price':
                bid_no=get('bidNo').strip()
                order=get('order','000').strip()
                if not re.fullmatch(r'[a-zA-Z0-9-]{8,40}',bid_no) or not re.fullmatch(r'\d{3}',order):
                    raise ApiError('invalid_bid_identifier',400)
                ck=('bid-change-price',bid_no,order)
                with lock:saved=cache.get(ck)
                if saved and saved[0]>time.time():return self.reply(200,saved[1])
                result=bid_change_and_price_query(bid_no,order)
                with lock:cache[ck]=(time.time()+(12*3600 if result.get('ok') else 1200),result)
                return self.reply(200,result)
            if u.path == '/api/g2b/bid-evidence':
                bid_no=get('bidNo').strip()
                order=get('order','000').strip()
                if not re.fullmatch(r'[a-zA-Z0-9-]{8,40}',bid_no) or not re.fullmatch(r'\d{3}',order):
                    raise ApiError('invalid_bid_identifier',400)
                ck=('bid-evidence',bid_no,order)
                with lock:saved=cache.get(ck)
                if saved and saved[0]>time.time():return self.reply(200,saved[1])
                result=bid_evidence_query(bid_no,order)
                # Do not retain upstream failures for six hours. A transient
                # 429 is handled by the shared cooldown above, not a false
                # negative qualification verdict.
                complete=(result.get('region') or {}).get('complete') and (result.get('attachments') or {}).get('complete') and (result.get('noticeDocuments') or {}).get('complete')
                lifetime=6*3600 if complete else 600
                with lock:cache[ck]=(time.time()+lifetime,result)
                return self.reply(200,result)
            if u.path == '/api/g2b/eligibility':
                bid_no=get('bidNo').strip()
                order=get('order','000').strip()
                if not re.fullmatch(r'[a-zA-Z0-9-]{8,40}',bid_no) or not re.fullmatch(r'\d{3}',order):
                    raise ApiError('invalid_bid_identifier',400)
                ck=('eligibility',bid_no,order)
                con=open_bid_db()
                try:
                    prev=con.execute('SELECT payload,checked_at FROM bid_license_cache WHERE bid_no=? AND bid_ord=?',(bid_no,order)).fetchone()
                    if prev:
                        try:
                            checked=datetime.datetime.fromisoformat(prev[1].replace('Z','+00:00'))
                            age=(datetime.datetime.now(datetime.timezone.utc)-checked).total_seconds()
                            if age<7*86400:
                                return self.reply(200,json.loads(prev[0]))
                        except (ValueError,TypeError,OverflowError): pass
                finally: con.close()
                with lock: saved=cache.get(ck)
                if saved and saved[0]>time.time():
                    return self.reply(200,saved[1])
                data=request_api(API_BASE,'getBidPblancListInfoLicenseLimit',{
                    'pageNo':1,'numOfRows':100,'inqryDiv':2,'bidNtceNo':bid_no,'bidNtceOrd':order
                })
                rows=list(data['items'])
                total=data['totalCount']
                for page in range(2,min((total+99)//100,10)+1):
                    nxt=request_api(API_BASE,'getBidPblancListInfoLicenseLimit',{
                        'pageNo':page,'numOfRows':100,'inqryDiv':2,
                        'bidNtceNo':bid_no,'bidNtceOrd':order})
                    rows.extend(nxt['items'])
                requirements=[]
                for row in rows:
                    if row.get('bidNtceNo') and str(row.get('bidNtceNo'))!=bid_no:
                        continue
                    if row.get('bidNtceOrd') and str(row.get('bidNtceOrd')).zfill(3)!=order:
                        continue
                    name=str(row.get('lcnsLmtNm') or '').strip()
                    industry=str(row.get('permsnIndstrytyList') or '').strip()
                    # Prefer official industry-code field over free-text years.
                    raw_codes=re.findall(r'(?<!\d)\d{4}(?!\d)',industry or name)
                    codes=[c for c in raw_codes if not re.match(r'^20\d{2}$',c)]
                    desc=name+' '+industry
                    if re.search(r'또는|택일|중\s*(?:하나|1종)|\bOR\b',desc,re.I):
                        logic='OR'
                    elif re.search(r'모두|동시\s*보유|각각\s*보유|\bAND\b',desc,re.I):
                        logic='AND'
                    else:
                        logic='UNKNOWN'
                    requirements.append({
                        'name':name or '면허 제한 내용 확인 필요',
                        'codes':list(dict.fromkeys(codes)),
                        'logic':logic,
                        'group':str(row.get('lmtGrpNo') or ''),
                        'sequence':str(row.get('lmtSno') or ''),
                        'permittedIndustries':industry,
                        'fieldRestrictions':str(row.get('indstrytyMfrcFldList') or '')
                    })
                result={'ok':True,'bidNo':bid_no,'order':order,'requirements':requirements,
                        'count':len(requirements),'totalCount':total,
                        'complete':len(rows)>=total,
                        'source':'나라장터 입찰공고정보서비스 면허제한',
                        'limitations':'면허제한 항목만 포함. 직접생산·중소기업확인·실적·지역·원문 추가조건은 별도 확인 필요',
                        'checkedAt':datetime.datetime.utcnow().isoformat()+'Z'}
                con=open_bid_db()
                try:
                    with con:
                        con.execute('INSERT OR REPLACE INTO bid_license_cache(bid_no,bid_ord,payload,checked_at) VALUES(?,?,?,?)',
                            (bid_no,order,json.dumps(result,ensure_ascii=False,separators=(',',':')),result['checkedAt']))
                finally:con.close()
                with lock: cache[ck]=(time.time()+3600,result)
                return self.reply(200,result)
            if u.path == '/api/g2b/awards':
                bid_no = get('bidNo').strip()
                if not re.fullmatch(r'[a-zA-Z0-9-]{8,40}',bid_no):
                    raise ApiError('invalid_bid_no',400)
                return self.reply(200,cached_awards_query(bid_no))
            if u.path != '/api/g2b/bids': raise ApiError('not_found',404)
            kind = get('kind','servc')
            if kind not in BID_OPS: raise ApiError('invalid_kind',400)
            start,end = get('from'),get('to')
            d1,d2 = date(start),date(end)
            if d1 > d2 or (d2-d1).days > 6: raise ApiError('date_window_must_be_1_to_7_days',400)
            try: page,rows = int(get('page','1')),int(get('rows','50'))
            except ValueError: raise ApiError('invalid_pagination',400)
            if not (1 <= page <= 20 and 1 <= rows <= 100): raise ApiError('invalid_pagination',400)
            ck = (kind,start,end,page,rows)
            with lock: saved = cache.get(ck)
            if saved and saved[0] > time.time():
                out = dict(saved[1]);out['cached']=True
                return self.reply(200,out)
            data = request_api(API_BASE,BID_OPS[kind],{
                'pageNo':page,'numOfRows':rows,'inqryDiv':1,
                'inqryBgnDt':start+'0000','inqryEndDt':end+'2359'})
            result = {'ok':True,'kind':kind,'from':start,'to':end,'page':page,
                'rows':rows,'totalCount':data['totalCount'],
                'items':[format_bid(x,kind) for x in data['items']],
                'generated_at':datetime.datetime.utcnow().isoformat()+'Z','cached':False}
            # The database write must succeed before acknowledging the fetch.
            stats=persist_bids(result['items'])
            result['persisted']=True
            result['savedReceived']=stats['received']
            result['savedTotal']=stats['storedTotal']
            with lock:
                if len(cache)>150:
                    # A blanket clear would reset the official API's 429 circuit breaker.
                    now=time.time()
                    for key,entry in list(cache.items()):
                        if isinstance(entry,tuple) and len(entry)==2 and entry[0]<now:
                            del cache[key]
                cache[ck] = (time.time()+900,result)
            self.reply(200,result)
        except ApiError as e:
            self.reply(e.status,{'ok':False,'error':e.msg})
        except Exception:
            self.reply(502,{'ok':False,'error':'internal_upstream_error'})

    def do_POST(self):
        try:
            if urlparse(self.path).path != '/api/g2b/worklinks-state':
                raise ApiError('not_found', 404)
            origin = self.headers.get('Origin', '')
            if origin and origin not in ORIGINS:
                raise ApiError('origin_not_allowed', 403)
            project, user_id = worklinks_verify_identity(self.headers.get('Authorization', ''))
            try:
                size = int(self.headers.get('Content-Length') or '0')
            except ValueError:
                raise ApiError('invalid_body', 400)
            if not (0 < size <= 4096):
                raise ApiError('invalid_body', 400)
            try:
                body = json.loads(self.rfile.read(size).decode('utf-8'))
            except (ValueError, UnicodeError):
                raise ApiError('invalid_json', 400)
            if not isinstance(body, dict):
                raise ApiError('invalid_json', 400)
            return self.reply(200, worklinks_state_put(project, user_id, body))
        except ApiError as e:
            return self.reply(e.status, {'ok':False, 'error':e.msg})
        except Exception:
            return self.reply(503, {'ok':False, 'error':'state_store_unavailable'})

    def log_message(self, fmt, *args):
        # Logs client request path only; never upstream URLs or keys.
        sys.stderr.write('[worklinks-g2b] '+fmt%args+'\n')

if __name__=='__main__':
    server = ThreadedServer((BIND_HOST,PORT),Handler)
    if bool(TLS_CERT_FILE) != bool(TLS_KEY_FILE):
        raise SystemExit('TLS certificate and key must both be supplied')
    if BIND_HOST not in ('127.0.0.1','::1','localhost') and not TLS_CERT_FILE:
        raise SystemExit('Refusing public plaintext HTTP: configure G2B_TLS_CERT_FILE and G2B_TLS_KEY_FILE')
    if TLS_CERT_FILE:
        # TLS 1.2 minimum; CentOS7 Python 2.7 SSLContext availability depends on security updates.
        if not hasattr(ssl,'PROTOCOL_TLSv1_2'):
            raise SystemExit('Python/OpenSSL with TLS 1.2 required for direct HTTPS')
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.load_cert_chain(certfile=TLS_CERT_FILE,keyfile=TLS_KEY_FILE)
        server.socket = context.wrap_socket(server.socket,server_side=True)
        print('G2B serving HTTPS on %s:%s' % (BIND_HOST,PORT))
    else:
        print('G2B serving HTTP (loopback only) on %s:%s' % (BIND_HOST,PORT))
    server.serve_forever()
