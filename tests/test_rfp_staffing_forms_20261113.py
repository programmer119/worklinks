#!/usr/bin/env python3
"""Regression: blank submission forms must not block project staffing scans."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh_worklinks_rfp import (
    staffing_ancillary_form_without_extractable_text as form,
    staffing_effective_file_complete as complete,
    STAFFING_ROLE_SCAN_VERSION,
    compact_coverage,
)
def f(name, category='no_searchable_text'):
    return {'name':name,'readable':False,'errorCategory':category}
for name in ('입찰참가신청서.hwp','서약서(서식).hwp','입찰 참가 신청서.hwpx'):
    assert form(f(name)),name
for name in ('제안요청서.hwp','투입인력명세서.hwp','기술제안서.pdf','기타첨부.hwp',
             '서약서(직원재직).hwp','입찰참가신청서_인력명세.hwp'):
    assert not form(f(name)),name
assert not form(f('입찰참가신청서.hwp','hwp_parse_failed'))
assert not form({'name':'입찰참가신청서.hwp','readable':True,'errorCategory':'no_searchable_text'})
source={'name':'제안요청서.hwp','readable':True,'sourceTextScanComplete':True,
        'staffingRoleScanVersion':STAFFING_ROLE_SCAN_VERSION,
        'staffingRoleScanTruncated':False,
        'sourceSha256':'a'*64,'staffingRoles':[],'staffingFacts':[]}
for name in ('입찰참가신청서.hwp','서약서(서식).hwp'):
    files=[source, f(name)]
    assert all(complete(z,files) for z in files),name
    record={'status':'text_extracted_requires_review','manifestComplete':True,
            'files':files,'reviewComplete':False,
            'readableDocumentCount':1,'unreadableDocumentCount':1}
    covered=compact_coverage(record)
    assert covered['staffingRoleScanComplete'] is True, covered
    assert covered['files'][1]['staffingScopeExcluded'] is True
    assert covered['files'][1]['errorCategory']=='no_searchable_text'
    assert covered['files'][1]['readable'] is False
    assert covered['reviewComplete'] is False
    # The same record with an unreadable technical proposal is NOT complete.
    bad=compact_coverage({**record,'files':[source,f('기술제안서.hwp')]})
    assert bad['staffingRoleScanComplete'] is False
# A missing parser pass for a valid RFP must remain incomplete.
outdated={**source,'staffingRoleScanVersion':0}
assert not complete(outdated,[outdated,f('입찰참가신청서.hwp')])
print('RFP_STAFFING_FORM_SCOPE_AND_FAILURE_PRESERVATION_PASS')
