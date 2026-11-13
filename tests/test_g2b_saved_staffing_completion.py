#!/usr/bin/env python3
"""Offline coverage contract: server saved API must honor verified staffing scope."""
from pathlib import Path
import runpy
src=Path(__file__).resolve().parents[1]/'server/g2b-proxy.py'
functions=runpy.run_path(str(src),run_name='staffing_api_coverage_test')
saved=functions['saved_rfp_search_state']
def read(name,sha='a'*64):
    return {'name':name,'readable':True,'sourceSha256':sha,
        'sourceTextScanComplete':True,'staffingRoleScanVersion':4,
        'staffingRoleScanTruncated':False}
def blank(name):
    return {'name':name,'readable':False,'errorCategory':'no_searchable_text'}
for form in ('입찰참가신청서.hwp','서약서(서식).hwp'):
    files=[read('제안요청서.hwp'),blank(form)]
    row={'manifestComplete':True,'status':'text_extracted_requires_review',
         'staffingRoleScanComplete':True,'files':files}
    result=saved(row,compact=False)
    assert result['staffingRoleScanComplete'] is True,(form,result)
    assert result['fileStatuses'][1]['errorCategory']=='no_searchable_text'
    assert result['scanComplete'] is False,'General extraction error must stay separate'
    assert saved(row,compact=True)['staffingRoleScanComplete'] is True
    assert saved({**row,'staffingRoleScanComplete':False})['staffingRoleScanComplete'] is False
    assert saved({**row,'files':[read('제안요청서.hwp'),blank('인력배치계획서.hwp')]})['staffingRoleScanComplete'] is False
    assert saved({**row,'files':[{'name':'제안요청서.hwp','readable':True,
        'staffingRoleScanVersion':0},blank(form)]})['staffingRoleScanComplete'] is False
    assert saved({**row,'files':[read('제안요청서.hwp'),blank(form),
        {'name':'인력계획서.pdf','readable':False,'errorCategory':'unreadable'}]})['staffingRoleScanComplete'] is False
print('G2B_SAVED_SOURCE_SCOPED_STAFFING_COMPLETE_PASS')
