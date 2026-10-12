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
    raise AssertionError(operation)
g['request_api']=fake
try:
    data=p['bid_evidence_query']('R26BK01756420','000')
    assert data['ok']
    assert data['region']['ok'] and data['region']['complete']
    assert data['region']['count']==2
    assert data['region']['items']==[{'name':'서울특별시','code':'11'}]
    assert len(data['attachments']['items'])==2
    assert data['attachments']['items'][0]['name']=='제안요청서.pdf'
    assert data['attachments']['items'][1]['url']==''
    assert len(calls)==2 and all(call[2]['bidNtceOrd']=='000' for call in calls)
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
    assert operation=='getCntrctInfoListServc'
    assert 'CntrctInfoService' in base
    return {'items':[{'cntrctNo':'T-123','cntrctNm':'Test only'}],'totalCount':1}
g['request_api']=contract_mock
try:
    cap=p['contract_capability_query']()
    assert cap['authorized'] and cap['ok']
    assert cap['companyHistoryVerified'] is False
    assert 'cntrctNo' in cap['schemaFields']
finally:
    g['request_api']=original
print('G2B_BID_EVIDENCE_PREFLIGHT=PASS')
