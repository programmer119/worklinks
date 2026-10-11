#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""WorkLinks G2B API proxy. CentOS 7 / Python 2.7+ standard library only."""
from __future__ import print_function
import os, sys, re, json, time, datetime, threading
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
SECRET_PATH = os.environ.get('G2B_SECRET_PATH', '/home/worklinks/g2b/secrets/g2b.env')
API_BASE = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService'
AWARD_BASE = 'https://apis.data.go.kr/1230000/as/ScsbidInfoService'
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
            if u.path == '/api/g2b/company':
                # Business registration operation must be verified against the official API schema.
                raise ApiError('company_operation_requires_official_mapping',501)
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
    ThreadedServer(('127.0.0.1',PORT),Handler).serve_forever()
