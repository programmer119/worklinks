#!/usr/bin/env python3
"""G2B region/e-order evidence must preserve provenance and never imply full proof."""
import os,runpy
from pathlib import Path
path='/app/api.py' if os.path.isfile('/app/api.py') else str(Path(__file__).resolve().parents[1]/'server/g2b-proxy.py')
p=runpy.run_path(path,run_name='worklinks_bid_evidence_unit')
g=p['bid_evidence_query'].__globals__
original=g['request_api']
calls=[]
def fake(base,operation,params):
    calls.append((base,operation,params.copy()))
    if operation=='getBidPblancListInfoPrtcptPsblRgn':
        return {'items':[{'bidNtceNo':'R26BK01756420','bidNtceOrd':'000','prtcptPsblRgnNm':'서울특별시','prtcptPsblRgnCd':'11'},
                         {'bidNtceNo':'R26BK00000001','prtcptPsblRgnNm':'잘못된공고'}], 'totalCount':2}
    if operation=='getBidPblancListInfoEorderAtchFileInfo':
        return {'items':[{'bidNtceNo':'R26BK01756420','atchFileNm':'제안요청서.pdf','atchFileUrl':'https://www.g2b.go.kr/docs/rfp.pdf'},
                         {'bidNtceNo':'R26BK01756420','atchFileNm':'부적절','atchFileUrl':'javascript:alert(1)'}], 'totalCount':2}
    if operation=='getBidPblancListInfoServc':
        return {'items':[{'bidNtceNo':'R26BK01756420','bidNtceOrd':'000',
            'ntceSpecDocUrl1':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/documents/rfp.pdf',
            'ntceSpecFileNm1':'입찰공고 제안요청서.pdf',
            'ntceSpecDocUrl2':'https://www.g2b.go.kr/docs/rfp.pdf',
            'ntceSpecFileNm2':'별도 과업지시서.pdf'}], 'totalCount':1}
    raise AssertionError(operation)
g['request_api']=fake
try:
    data=p['bid_evidence_query']('R26BK01756420','000')
    assert data['ok']
    assert data['region']['ok'] and data['region']['complete']
    assert data['region']['count']==2
    assert data['region']['items']==[{'name':'서울특별시','code':'11'}]
    assert len(data['attachments']['items'])==3
    assert data['attachments']['items'][0]['name']=='제안요청서.pdf'
    assert data['attachments']['items'][1]['url']==''
    assert data['attachments']['items'][2]['source']=='notice_detail'
    assert data['attachments']['items'][2]['name']=='입찰공고 제안요청서.pdf'
    assert data['attachments']['eorderCount']==2
    assert data['attachments']['noticeDetailDocumentCount']==2
    assert data['noticeDocuments']['ok']
    assert len(calls)==3 and all(call[2]['bidNtceOrd']=='000' for call in calls)
    # The public notice may contain an RFP even if the e-order API returns zero.
    def eorder_zero(base,operation,params):
        if operation=='getBidPblancListInfoServc':
            return {'items':[{'bidNtceNo':'R26BK01756420',
                'ntceSpecDocUrl1':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/rfp.hwp',
                'ntceSpecFileNm1':'입찰참가 제안요청서.hwp'}],'totalCount':1}
        return {'items':[],'totalCount':0}
    g['request_api']=eorder_zero
    recovered=p['bid_evidence_query']('R26BK01756420','000')
    assert recovered['attachments']['eorderCount']==0
    assert recovered['attachments']['noticeDetailDocumentCount']==1
    assert recovered['attachments']['items'][0]['name']=='입찰참가 제안요청서.hwp'
    assert recovered['attachments']['items'][0]['source']=='notice_detail'
    def blocked(base,operation,params):
        raise p['ApiError']('upstream_result_PERMISSION_DENIED')
    g['request_api']=blocked
    denied=p['bid_evidence_query']('R26BK01756420','000')
    assert not denied['ok'] and not denied['region']['ok']
    assert denied['region']['error']=='upstream_result_PERMISSION_DENIED'
finally:
    g['request_api']=original
# Authorization discovery is separate from a company's proven performance.
def contract_mock(base,operation,params):
    if operation=='getCntrctInfoListServc':
        assert 'CntrctInfoService' in base
        return {'items':[{'cntrctNo':'T-123','cntrctNm':'Test only'}],'totalCount':1}
    assert operation=='getCntrctProcssIntgOpenServc'
    assert 'CntrctProcssIntgOpenService' in base
    assert params['bidNtceNo']=='R25BK00826083'
    return {'items':[], 'totalCount':0}
g['request_api']=contract_mock
try:
    cap=p['contract_capability_query']()
    assert cap['authorized'] and cap['ok']
    assert cap['companyHistoryVerified'] is False
    assert 'cntrctNo' in cap['schemaFields']
    assert cap['alternative']['ok']
    assert cap['contractPerformanceVerified'] is False
finally:
    g['request_api']=original
# Contract fallback must never treat winning a bid as completed project performance.
def process_mock(base,operation,params):
    assert operation=='getCntrctProcssIntgOpenServc'
    assert 'CntrctProcssIntgOpenService' in base
    assert params['bidNtceNo']=='R25BK00826083'
    return {'items':[
        {'bidNtceNo':'R25BK00826083','cntrctNo':'C1','cntrctCorpBizno':'130-81-85973','cntrctAmt':'123456789'},
        {'bidNtceNo':'R25BK00826083','cntrctNo':'C2','cntrctCorpBizno':'1111111111'},
        {'bidNtceNo':'R25BK00826083','cntrctNo':'C3'}
    ],'totalCount':3}
g['request_api']=process_mock
try:
    contracts=p['contract_evidence_query']('R25BK00826083','1308185973')
    assert contracts['attributableCount']==1
    assert contracts['otherCompanyCount']==1
    assert contracts['unattributedCount']==1
    assert contracts['contracts'][0]['contractNo']=='C1'
    assert contracts['contracts'][0]['performanceComplete'] is None
    assert contracts['contractPerformanceVerified'] is False
finally:g['request_api']=original
class Fake403:
    code=403
    def read(self,size):
        return b'SERVICE_ACCESS_DENIED_ERROR?serviceKey=SECRET_TOKEN'
classified=p['classify_upstream_http_error'](Fake403())
assert classified=='upstream_http_403_SERVICE_ACCESS_DENIED_ERROR'
assert 'SECRET_TOKEN' not in classified
# A provider-side 429 must stop futile repeated calls; no credential is inferred.
import io
try: from urllib2 import HTTPError as HttpRateError
except ImportError: from urllib.error import HTTPError as HttpRateError
globals_api=p['request_api'].__globals__
old_open=globals_api['urlopen'];old_key=globals_api['get_key']
api_base=p['API_BASE']
attempts=[]
def quota_exhausted(request,timeout):
    attempts.append(1)
    raise HttpRateError('https://apis.data.go.kr/1230000/example',429,
        'Too many requests',{},io.BytesIO(b'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR'))
try:
    globals_api['urlopen']=quota_exhausted
    globals_api['get_key']=lambda:'unit-test-key'
    globals_api['cache'].pop(('upstream-rate-cooldown',api_base),None)
    try:p['request_api'](api_base,'getBidPblancListInfoLicenseLimit',{'bidNtceNo':'R26BK01756420'})
    except p['ApiError'] as e:
        assert 'upstream_http_429' in e.msg
    else:raise AssertionError('upstream quota exhaustion not detected')
    try:p['request_api'](api_base,'getBidPblancListInfoPrtcptPsblRgn',{'bidNtceNo':'R26BK01756420'})
    except p['ApiError'] as e:
        assert e.msg=='upstream_temporarily_rate_limited'
    else:raise AssertionError('quota circuit breaker absent')
    assert len(attempts)==1,'one 429 should suppress further upstream requests'
    globals_api['cache'][('upstream-rate-cooldown',api_base)]=0
    try:p['request_api'](api_base,'getBidPblancListInfoPrtcptPsblRgn',{})
    except p['ApiError'] as e:
        assert 'upstream_http_429' in e.msg
    else:raise AssertionError('expired cooldown did not permit retry')
    assert len(attempts)==2,'cooldown expiry should permit one retry'
finally:
    globals_api['urlopen']=old_open
    globals_api['get_key']=old_key
    globals_api['cache'].pop(('upstream-rate-cooldown',api_base),None)

print('G2B_BID_EVIDENCE_PREFLIGHT=PASS')
