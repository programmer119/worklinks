#!/usr/bin/env python3
"""No-network integration: all official collector and proxy requests share durable SQLite."""
import importlib.util,json,os,pathlib,sqlite3,sys,tempfile,urllib.error
from unittest import mock

root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
sys.path.insert(0,str(root/'server'))
from rfp_call_ledger import CallLedger,cache_key

def load(file,name):
    spec=importlib.util.spec_from_file_location(name,root/'server'/file)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class Response:
    status=200
    def __init__(self,doc):self.raw=json.dumps(doc,ensure_ascii=False).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.raw if n<0 else self.raw[:n]

with tempfile.TemporaryDirectory() as tmp:
    dest=pathlib.Path(tmp)/'shared.sqlite3'
    with mock.patch.dict(os.environ,{'WORKLINKS_RFP_LEDGER_DB':str(dest),
                                    'G2B_SERVICE_KEY':'secret-test-do-not-store'}):
        proxy=load('g2b-proxy.py','g2b_api_shared_ledger_test')
        received=[]
        def provider(req,timeout=0):
            received.append(req.full_url)
            return Response({'response':{'header':{'resultCode':'00'},
                'body':{'items':[{'bidNtceNo':'R26BK01816467'}],'totalCount':1}}})
        with mock.patch.object(proxy,'urlopen',provider):
            first=proxy.request_api(proxy.API_BASE,'getBidPblancListInfoServcPPSSrch02',
                                    {'pageNo':1,'numOfRows':999,'inqryDiv':1})
            second=proxy.request_api(proxy.API_BASE,'getBidPblancListInfoServcPPSSrch02',
                                     {'pageNo':1,'numOfRows':999,'inqryDiv':1})
        assert first==second and len(received)==1,('proxy',len(received))
        assert first['totalCount']==1

        crawler=load('g2b-full-crawler.py','g2b_crawler_shared_ledger_test')
        got=[]
        def crawl_provider(req,timeout=0):
            got.append(req.full_url)
            return Response({'response':{'header':{'resultCode':'00'},
              'body':{'items':[{'bidNtceNo':'R26BK01816467','bidNtceOrd':'000'}],
                      'totalCount':1}}})
        with mock.patch.object(crawler.urllib.request,'urlopen',crawl_provider):
            x=crawler.call('secret-test-do-not-store','servc','20261112',1)
            y=crawler.call('secret-test-do-not-store','servc','20261112',1)
        assert x==y and len(got)==1,('crawler',len(got))

        standard=load('g2b-standard-worker.py','g2b_standard_shared_ledger_test')
        std_called=[]
        def std_provider(req,timeout=0):
            std_called.append(req.full_url)
            return Response({'response':{'header':{'resultCode':'00'},
               'body':{'totalCount':1,'items':[{'bidNtceNo':'R26BK01816467'}]}}})
        budget=[0,10]
        with mock.patch.object(standard.urllib.request,'urlopen',std_provider):
            a=standard.request_budgeted('B1','20261111',1,'private',budget)
            b=standard.request_budgeted('B1','20261111',1,'private',budget)
        assert a==b and len(std_called)==1 and budget[0]==1,(budget,len(std_called))

        eligibility=load('g2b-eligibility-worker.py','g2b_qualification_shared_ledger_test')
        local=[]
        def local_provider(req,timeout=0):
            local.append(req.full_url)
            return Response({'ok':True,'complete':True,'bidNo':'R26BK01816467',
                             'order':'000','requirements':[]})
        with mock.patch.object(eligibility.urllib.request,'urlopen',local_provider):
            assert eligibility.verify('R26BK01816467','000')['complete'] is True
        assert len(local)==1

        ledger=CallLedger(dest)
        counts=ledger.stats()['counts']
        assert counts['upstream_http:http_verified']==1,counts
        assert counts['upstream_api:verified_cache_reused']==1,counts
        assert counts['crawler_http:http_ok']==1,counts
        assert counts['crawler:verified_page_reused']==1,counts
        assert counts['standard_http:provider_verified']==1,counts
        assert counts['standard:verified_page_reused']==1,counts
        assert counts['qualification_local_http:http_verified']==1,counts
        with sqlite3.connect(dest) as conn:
            audit=json.dumps(conn.execute('SELECT kind,request_key,notice_key,error_class,detail FROM call_events').fetchall())
            assert 'secret-test-do-not-store' not in audit
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('G2B_ALL_OFFICIAL_COLLECTOR_API_DEDUP_AND_SHARED_LEDGER=PASS',counts,flush=True)
