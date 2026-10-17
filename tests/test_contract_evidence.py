#!/usr/bin/env python3
"""Contract-process evidence is attributable only by explicit matching bizno."""
import os,runpy
from pathlib import Path
import io
path='/app/api.py' if os.path.isfile('/app/api.py') else str(Path(__file__).resolve().parents[1]/'server/g2b-proxy.py')
p=runpy.run_path(path,run_name='worklinks_contract_test')
g=p['contract_evidence_query'].__globals__
original=g['request_api']
BID='R25BK00826083'
def mock(base,op,params):
    assert 'CntrctProcssIntgOpenService' in base and op=='getCntrctProcssIntgOpenServc'
    assert params['bidNtceNo']==BID
    return {'totalCount':4,'items':[
        {'bidNtceNo':BID,'cntrctNo':'C1','cntrctNm':'조선왕조 기록유산','cntrctCorpBizno':'130-81-85973',
         'cntrctAmt':'45000000','cntrctCnclsDate':'2025-08-01'},
        {'bidNtceNo':BID,'cntrctNo':'C2','cntrctCorpBizno':'9999999999'},
        {'bidNtceNo':BID,'cntrctNo':'C3','cntrctNm':'사업자 미기재'},
        {'bidNtceNo':'DIFFERENT','cntrctNo':'C4','cntrctCorpBizno':'1308185973'}]}
g['request_api']=mock
try:
    r=p['contract_evidence_query'](BID,'1308185973')
    assert r['ok'] and r['complete']
    assert r['attributableCount']==1 and r['unattributedCount']==1 and r['otherCompanyCount']==1
    assert r['contracts'][0]['contractNo']=='C1'
    assert r['contracts'][0]['companyBiznoMatched'] is True
    assert r['contracts'][0]['performanceComplete'] is None
    assert r['contracts'][0]['inspectionComplete'] is None
    assert r['contractPerformanceVerified'] is False
    # Nested JSON arrays must be scanned for the CONTRACTOR, not the winning bidder.
    import json
    def nested(base,op,params):
        return {'totalCount':2,'items':[
            {'bidNtceNo':BID,'bidwinrInfoList':[{'bidwinnrBizno':'1308185973'}],
             'cntrctInfoList':json.dumps([
               {'dcsnCntrctNo':'C-NEST','cntrctNm':'용역계약',
                'corpList':[{'corpBizno':'130-81-85973'}]},
               {'dcsnCntrctNo':'C-OTHER',
                'corpList':[{'corpBizno':'9999999999'}]}])},
            {'bidNtceNo':BID,'bidwinrInfoList':[{'bidwinnrBizno':'1308185973'}],
             'cntrctInfoList':[]}]}
    g['request_api']=nested
    nr=p['contract_evidence_query'](BID,'1308185973')
    assert nr['attributableCount']==1 and nr['contracts'][0]['contractNo']=='C-NEST'
    assert nr['otherCompanyCount']==1
    assert nr['unattributedCount']==1
    assert nr['nestedContractItems']==2
    def only_winning(base,op,params):
        return {'totalCount':1,'items':[{'bidNtceNo':BID,
          'bidwinrInfoList':[{'bidwinnrBizno':'1308185973'}]}]}
    g['request_api']=only_winning
    nw=p['contract_evidence_query'](BID,'1308185973')
    assert nw['attributableCount']==0
    def denied(base,op,params):raise p['ApiError']('upstream_http_403_SERVICE_ACCESS_DENIED_ERROR')
    g['request_api']=denied
    r2=p['contract_capability_query']()
    assert r2['authorized'] is False and r2['alternative']['ok'] is False
    assert len(r2['probes'])==2
finally:
    g['request_api']=original
# Independent contract-info lookup: only the SAME notice and an explicitly
# matching contractor business ID count as a contract. Awards are not proof.
def contract_register_mock(base,op,params):
    assert 'CntrctInfoService' in base
    assert op=='getCntrctInfoListServcPPSSrch'
    assert params['ntceNo']==BID and params['inqryDiv']==4
    assert 'bidNtceNo' not in params, 'PPSSrch official parameter is ntceNo'
    return {'totalCount':4,'items':[
        {'ntceNo':BID,'dcsnCntrctNo':'REG-1','cntrctNm':'실제 용역 계약',
         'corpList':[{'corpBizno':'130-81-85973'}],
         'thtmCntrctAmt':'150000000','cntrctPrd':'1년','cntrctCnclsDate':'2025-10-01'},
        {'ntceNo':BID,'dcsnCntrctNo':'OTHER',
         'corpList':[{'corpBizno':'9999999999'}]},
        {'ntceNo':'DIFFERENT','dcsnCntrctNo':'WRONG-NOTICE',
         'corpList':[{'corpBizno':'1308185973'}]},
        {'dcsnCntrctNo':'UNKNOWN-NOTICE','corpList':[{'corpBizno':'1308185973'}]}
    ]}
g['request_api']=contract_register_mock
try:
    exact=p['contract_notice_lookup'](BID,'1308185973')
    assert exact['ok'] and exact['complete']
    assert exact['attributableCount']==1 and exact['contracts'][0]['contractNo']=='REG-1'
    assert exact['contracts'][0]['companyBiznoMatched']
    assert exact['contracts'][0]['amount']=='150000000'
    assert exact['otherCompanyCount']==1 and exact['unattributedCount']==2
    assert exact['contracts'][0]['performanceComplete'] is None
    def winner_only(base,op,params):
        return {'totalCount':1,'items':[{'ntceNo':BID,
           'bidwinnrBizno':'1308185973','corpList':[]}]}
    g['request_api']=winner_only
    assert p['contract_notice_lookup'](BID,'1308185973')['attributableCount']==0
    def denied_register(base,op,params):
        raise p['ApiError']('upstream_http_403_SERVICE_ACCESS_DENIED_ERROR')
    g['request_api']=denied_register
    failed=p['contract_notice_lookup'](BID,'1308185973')
    assert failed['ok'] is False and failed['contracts']==[]
finally:
    g['request_api']=original

# Regression: the provider returned this nonstandard HTTP-200 error envelope
# for the old bad bidNtceNo parameter. It must NEVER become "no contracts".
env=p['request_api'].__globals__
orig_open=env['urlopen']
orig_key=env['get_key']
class Fake200:
    def __init__(self,body):self.body=body
    def read(self):return self.body
def provider_error(req,timeout):
    assert 'ntceNo=' in req.full_url and 'bidNtceNo=' not in req.full_url
    return Fake200(b'{"nkoneps.com.response.ResponseError":{"description":"bad query"}}')
try:
    env['urlopen']=provider_error
    env['get_key']=lambda:'test-not-real-secret'
    env['cache'].pop(('upstream-rate-cooldown',p['CONTRACT_BASE']),None)
    incorrect=p['contract_notice_lookup'](BID,'1308185973')
    assert incorrect['ok'] is False
    assert incorrect['error']=='upstream_provider_response_error'
    assert incorrect['attributableCount']==0 and incorrect['complete'] is False
finally:
    env['urlopen']=orig_open
    env['get_key']=orig_key

class FakeHTTP403:
    code=403
    def read(self,limit):
        return b'<resultCode>SERVICE_ACCESS_DENIED_ERROR</resultCode><serviceKey>SECRET</serviceKey>'
err=p['classify_upstream_http_error'](FakeHTTP403())
assert err=='upstream_http_403_SERVICE_ACCESS_DENIED_ERROR' and 'SECRET' not in err
print('G2B_CONTRACT_EVIDENCE_PREFLIGHT=PASS')
