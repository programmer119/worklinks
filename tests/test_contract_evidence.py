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
class FakeHTTP403:
    code=403
    def read(self,limit):
        return b'<resultCode>SERVICE_ACCESS_DENIED_ERROR</resultCode><serviceKey>SECRET</serviceKey>'
err=p['classify_upstream_http_error'](FakeHTTP403())
assert err=='upstream_http_403_SERVICE_ACCESS_DENIED_ERROR' and 'SECRET' not in err
print('G2B_CONTRACT_EVIDENCE_PREFLIGHT=PASS')
