#!/usr/bin/env python3
"""Never claim broken HML read; reuse only a same-title, scanned official PDF."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair

def sample(pdf_name='입찰공고문(2027년 수입 공 컨테이너 종합정보관리시스템 위탁운영).pdf'):
    hml={'name':'입찰공고문(2027년 수입 공 컨테이너 종합정보관리시스템 위탁운영).hml',
         'readable':False,'sourceTextScanComplete':False,'errorCategory':'hml_xml_truncated',
         'sourceSha256':'b'*64}
    pdf={'name':pdf_name,'readable':True,'sourceTextScanComplete':True,
         'qualificationScanTruncated':False,'sourceSha256':'a'*64,
         'staffingRoleScanVersion':reader.STAFFING_ROLE_SCAN_VERSION,
         'staffingFactScanVersion':reader.STAFFING_FACT_SCAN_VERSION,
         'staffingRoleScanTruncated':False}
    return hml,pdf

hml,pdf=sample()
assert reader.verified_pdf_companion(hml,[hml,pdf]) is pdf
assert repair.reader_retry_files({'files':[hml,pdf]})==[hml]
assert reader.annotate_official_pdf_siblings([hml,pdf])==1
assert hml['readable'] is False and hml['sourceTextScanComplete'] is False
assert hml['skippedDuplicateFormat'] is True
assert hml['alternatePdfEvidence']==pdf['name']
assert hml['alternatePdfSourceSha256']==pdf['sourceSha256']
assert hml['alternatePdfEvidenceMode']=='same_basename_not_proven_identical'
assert 'errorCategory' not in hml
assert reader.staffing_effective_file_complete(hml,[hml,pdf])
assert repair.reader_retry_files({'files':[hml,pdf]})==[]

for failed_pdf in (
    {'name':pdf['name'],'readable':True,'sourceTextScanComplete':False,
     'sourceSha256':'a'*64},
    {'name':pdf['name'],'readable':True,'sourceTextScanComplete':True,
     'sourceSha256':''},
    {'name':pdf['name'],'readable':True,'sourceTextScanComplete':True,
     'qualificationScanTruncated':True,'sourceSha256':'a'*64},
    {'name':'다른 공고문.pdf','readable':True,'sourceTextScanComplete':True,
     'sourceSha256':'a'*64}):
    bad,good=sample()
    good.update(failed_pdf)
    assert reader.verified_pdf_companion(bad,[bad,good]) is None
    assert reader.annotate_official_pdf_siblings([bad,good])==0
    assert bad.get('errorCategory')=='hml_xml_truncated'
    assert bad.get('skippedDuplicateFormat') is not True
    assert not reader.staffing_effective_file_complete(bad,[bad,good])

print('RFP_HML_SAME_STEM_VERIFIED_PDF_ONLY=PASS')
