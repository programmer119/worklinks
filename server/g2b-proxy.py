#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""WorkLinks G2B API proxy. CentOS 7 / Python 2.7+ standard library only."""
from __future__ import print_function
import os, sys, re, json, time, datetime, threading, ssl, sqlite3
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

def request_api(base, operation, params):
    token = get_key()
    if not token: raise ApiError('secret_not_configured', 503)
    args = {'serviceKey':token, 'type':'json'}
    args.update(params)
    url = base + '/' + operation + '?' + urlencode(args)
    try:
        response = urlopen(Request(url, headers={
            'Accept':'application/json', 'User-Agent':'WorkLinksG2B/1.0'
        }), timeout=14)
        raw = response.read()
    except HTTPError as e: raise ApiError('upstream_http_' + str(e.code))
    except (URLError, IOError, ValueError): raise ApiError('upstream_unreachable')
    try: doc = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError): raise ApiError('upstream_not_json')
    hdr = doc.get('response', {}).get('header', {})
    rc = str(hdr.get('resultCode', 'missing'))
    if rc not in ('00','0'): raise ApiError('upstream_result_' + re.sub(r'[^a-zA-Z0-9_]','',rc)[:20])
    body = doc.get('response', {}).get('body', {})
    items = body.get('items') or []
    if isinstance(items, dict): items = items.get('item') or []
    if not isinstance(items, list): items = [items]
    return {'items':items,'totalCount':int(body.get('totalCount') or len(items))}

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
        where='WHERE sw_candidate=1' if only_sw else ''
        history=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recurring_projects'").fetchone()
        if history:
            rows=con.execute('SELECT b.payload,r.history_json,r.repeat_years FROM bid_notices b '+
                'LEFT JOIN recurring_projects r ON b.kind=r.kind AND b.bid_no=r.bid_no '+
                (('WHERE b.sw_candidate=1 ') if only_sw else '')+
                'ORDER BY b.last_seen DESC,b.kind,b.bid_no DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        else:
            rows=[(v[0],None,0) for v in con.execute('SELECT payload FROM bid_notices '+where+
                    ' ORDER BY last_seen DESC,kind,bid_no DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()]
        items=[]
        for payload,series,years in rows:
            obj=json.loads(payload)
            if series and (years or 0)>=2:
                try:
                    obj['repeatHistory']=json.loads(series)
                    obj['repeatYears']=int(years)
                except (ValueError,TypeError): pass
            items.append(obj)
        return {'ok':True,'items':items,'totalCount':matching if only_sw else total,
                'storedTotal':total,'candidateTotal':matching,
                'limit':limit,'offset':offset,'persisted':True}
    finally:con.close()

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
            self.send_header('Access-Control-Allow-Methods','GET, OPTIONS')
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
            if not get_key(): raise ApiError('secret_not_configured',503)
            if u.path == '/api/g2b/crawl-status':
                return self.reply(200,crawler_state())
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
                matching = [x for x in basic['items'] if re.sub(r'[^0-9]','',str(x.get('bizno') or '')) == bizno]
                codes = [
                    {'code':str(x.get('indstrytyCd') or ''),
                     'name':x.get('indstrytyNm') or '',
                     'status':x.get('indstrytyStatsNm') or '',
                     'registeredAt':x.get('rgstDt') or '',
                     'expiresAt':x.get('vldPrdExprtDt') or '',
                     'representative':str(x.get('rprsntIndstrytyYn') or '')}
                    for x in industry['items']
                    if re.sub(r'[^0-9]', '', str(x.get('bizno') or '')) == bizno
                ]
                result = {
                    'ok':True, 'bizno':bizno, 'found':bool(matching),
                    'company':{'name':matching[0].get('corpNm') or '',
                               'registeredAt':matching[0].get('rgstDt') or ''} if matching else None,
                    'industries':codes, 'industryCount':industry['totalCount'],
                    'complete':len(industry['items']) >= industry['totalCount'],
                    'has1468':any(x['code']=='1468' for x in codes),
                    'source':'나라장터 사용자정보서비스',
                    'checkedAt':datetime.datetime.utcnow().isoformat()+'Z'
                }
                with lock: cache[ck] = (time.time()+3600, result)
                return self.reply(200,result)
            if u.path == '/api/g2b/eligibility':
                bid_no=get('bidNo').strip()
                order=get('order','000').strip()
                if not re.match(r'^[a-zA-Z0-9-]{8,40}
                bid_no = get('bidNo').strip()
                if not re.match(r'^[a-zA-Z0-9-]{8,40}$',bid_no):
                    raise ApiError('invalid_bid_no',400)
                data = request_api(AWARD_BASE,'getScsbidListSttusServc',{
                    'pageNo':1,'numOfRows':50,'inqryDiv':4,'bidNtceNo':bid_no})
                return self.reply(200,{'ok':True,'totalCount':data['totalCount'],'items':data['items']})
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
                if len(cache)>150: cache.clear()
                cache[ck] = (time.time()+900,result)
            self.reply(200,result)
        except ApiError as e:
            self.reply(e.status,{'ok':False,'error':e.msg})
        except Exception:
            self.reply(502,{'ok':False,'error':'internal_upstream_error'})

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
,bid_no) or not re.match(r'^\d{3}
                bid_no = get('bidNo').strip()
                if not re.match(r'^[a-zA-Z0-9-]{8,40}$',bid_no):
                    raise ApiError('invalid_bid_no',400)
                data = request_api(AWARD_BASE,'getScsbidListSttusServc',{
                    'pageNo':1,'numOfRows':50,'inqryDiv':4,'bidNtceNo':bid_no})
                return self.reply(200,{'ok':True,'totalCount':data['totalCount'],'items':data['items']})
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
                if len(cache)>150: cache.clear()
                cache[ck] = (time.time()+900,result)
            self.reply(200,result)
        except ApiError as e:
            self.reply(e.status,{'ok':False,'error':e.msg})
        except Exception:
            self.reply(502,{'ok':False,'error':'internal_upstream_error'})

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
,order):
                    raise ApiError('invalid_bid_identifier',400)
                ck=('eligibility',bid_no,order)
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
                    if row.get('bidNtceOrd') and str(row.get('bidNtceOrd'))!=order:
                        continue
                    name=str(row.get('lcnsLmtNm') or '').strip()
                    industry=str(row.get('permsnIndstrytyList') or '').strip()
                    codes=re.findall(r'(?<!\d)\d{4}(?!\d)',name+' '+industry)
                    requirements.append({
                        'name':name or '면허 제한 내용 확인 필요',
                        'codes':list(dict.fromkeys(codes)),
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
                with lock: cache[ck]=(time.time()+3600,result)
                return self.reply(200,result)
            if u.path == '/api/g2b/awards':
                bid_no = get('bidNo').strip()
                if not re.match(r'^[a-zA-Z0-9-]{8,40}$',bid_no):
                    raise ApiError('invalid_bid_no',400)
                data = request_api(AWARD_BASE,'getScsbidListSttusServc',{
                    'pageNo':1,'numOfRows':50,'inqryDiv':4,'bidNtceNo':bid_no})
                return self.reply(200,{'ok':True,'totalCount':data['totalCount'],'items':data['items']})
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
                if len(cache)>150: cache.clear()
                cache[ck] = (time.time()+900,result)
            self.reply(200,result)
        except ApiError as e:
            self.reply(e.status,{'ok':False,'error':e.msg})
        except Exception:
            self.reply(502,{'ok':False,'error':'internal_upstream_error'})

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
