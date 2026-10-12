#!/usr/bin/env python3
"""Classify RFP retrieval gaps without asserting that an attachment does not exist."""
import importlib.util
from pathlib import Path
script=Path(__file__).resolve().parents[1]/'scripts/refresh_worklinks_rfp.py'
spec=importlib.util.spec_from_file_location('worklinks_rfp',script)
rfp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(rfp)
orig_fetch=rfp.fetch_json
orig_download=rfp.download
try:
    def response(items,count=0,ok=True,complete=True,error=''):
        return {'attachments':{'ok':ok,'complete':complete,'items':items,
                'count':count,'error':error}}
    rfp.fetch_json=lambda _:response([],0)
    zero=rfp.process('R26BK12345678','000')
    assert zero['status']=='no_official_attachment_metadata'
    assert zero['reasonCode']=='eorder_api_zero__notice_detail_api_error'
    assert zero['reviewComplete'] is False
    rfp.fetch_json=lambda _:dict(response([],0),noticeDocuments={'ok':True,'complete':True,'items':[]})
    nofiles=rfp.process('R26BK12345678','000')
    assert nofiles['reasonCode']=='eorder_api_zero__notice_detail_zero_files'
    rfp.fetch_json=lambda _:dict(response([{'name':'RFP.hwp',
      'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/document.hwp'}],1),
      noticeDocuments={'ok':True,'complete':True,'items':[{'name':'RFP.hwp'}]})
    rfp.download=lambda _:b'not-a-hwp'
    detail=rfp.process('R26BK12345678','000')
    assert detail['files'][0]['errorCategory']=='invalid_hwp'
    rfp.fetch_json=lambda _:response([],None,False,False,'upstream_http_403')
    unauthorized=rfp.process('R26BK12345678','000')
    assert unauthorized['reasonCode']=='metadata_api_error'
    assert unauthorized['sourceError']=='upstream_http_403'
    rfp.fetch_json=lambda _:response([{'name':'제안서.docx',
         'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/invalid.docx'}],1)
    unsupported=rfp.process('R26BK12345678','000')
    assert unsupported['status']=='text_unavailable'
    assert unsupported['files'][0]['errorCategory']=='unsupported_attachment_format'
    rfp.fetch_json=lambda _:response([{'name':'제안서.hwp',
         'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadRfpFile.do'}],1)
    rfp.download=lambda _:b'not-a-hwp'
    invalid=rfp.process('R26BK12345678','000')
    assert invalid['files'][0]['errorCategory']=='invalid_hwp'
    assert invalid['reviewComplete'] is False
finally:
    rfp.fetch_json=orig_fetch
    rfp.download=orig_download
# Pagination, already-checked suppression, urgency and 1468 matching priority.
orig_discovery=rfp.fetch_json
try:
    fake_date=rfp.dt.datetime.now(rfp.dt.timezone(rfp.dt.timedelta(hours=9))).date()
    deadline=fake_date.strftime('%Y%m%d')+'1700'
    rows=[
      {'bidNo':'R26BK12345601','order':'000','kind':'servc','closes':deadline,
       'bidEligibility':{'requirements':[{'codes':['1468']}]}},
      {'bidNo':'R26BK12345602','order':'000','kind':'servc','closes':deadline},
      {'bidNo':'R26BK12345603','order':'000','kind':'thng','closes':deadline},
    ]
    calls=[]
    def pages(url):
        calls.append(url)
        if 'offset=0' in url:
            return {'ok':True,'totalCount':503,'items':rows+[
               {'bidNo':'bad','order':'000','closes':deadline} for _ in range(497)]}
        if 'offset=500' in url:
            return {'ok':True,'totalCount':503,'items':[
             {'bidNo':'R26BK12345604','order':'000','kind':'servc','closes':deadline,
              'bidEligibility':{'requirements':[{'codes':['1468']}]}}
             for _ in range(3)]}
        raise AssertionError(url)
    rfp.fetch_json=pages
    prior={'R26BK12345601:000':{'classificationVersion':4,'checkedAt':
       rfp.dt.datetime.now(rfp.dt.timezone.utc).isoformat(),'reviewComplete':False}}
    result=rfp.discover(10,prior)
    assert len(calls)==2,'discovery must request the next 500 notice page'
    assert result[0][0]=='R26BK01756420','fixture must remain for regression'
    assert result[1][0]=='R26BK12345604','new matching code 1468 should be prioritized'
    assert all(v[0]!='R26BK12345601' for v in result)
finally:
    rfp.fetch_json=orig_discovery

sample='''- 소프트웨어사업자(컴퓨터관련서비스사업)[업종코드 : 1468] 업종으로 반드시 등록한 자
- 직접생산확인증명서(세부품명: 정보시스템유지관리서비스, 세부품명번호 : 8111189901)를 소지한 자
- 제안서에는 투입인력 재직·경력·학력·자격증명서 서류 원본 또는 사본을 첨부하여야 함
- 공동수급 금지. 단독입찰만 허용
''';
c=rfp.extract_rule_candidates(sample,'공식 제안요청서.hwp')
assert any(x['type']=='industry_code' and '1468' in x['codes'] for x in c)
assert any(x['type']=='direct_production' and '8111189901' in x['codes'] for x in c)
assert any(x['type']=='staff_proof' and x['reviewStatus']=='unreviewed' for x in c)
assert all(x['documentRequiresManualFullReview'] for x in c)

print('WORKLINKS_RFP_FAILURE_CLASSIFICATION=PASS')
