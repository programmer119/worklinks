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
print('WORKLINKS_RFP_FAILURE_CLASSIFICATION=PASS')
