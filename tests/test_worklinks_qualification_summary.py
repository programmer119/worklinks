#!/usr/bin/env python3
"""Offline proof that RFP review progress never becomes bidder eligibility."""
import importlib.util
import json
from pathlib import Path
import tempfile

source = Path(__file__).resolve().parents[1] / 'scripts' / 'analyze_worklinks_rfp_ai.py'
spec = importlib.util.spec_from_file_location('qualification_review', str(source))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as temp:
    output = Path(temp) / 'qualification-review.json'
    notice = {
        'status': 'text_extracted_requires_review',
        'checkedAt': '2026-11-12T09:00:00Z',
        'manifestComplete': True, 'attachmentManifestCount': 1,
        'files': [{
            'name': '입찰 공고서.pdf', 'readable': True,
            'sourceSha256': 'a'*64, 'textSha256': 'b'*64,
            'sourceTextScanComplete': False,
            'unmatchedQualificationAnchorCount': 1,
            'qualificationScanTruncated': False,
            'clauseCandidatesTruncated': False,
            'clauseCandidates': [{
                'type': 'industry_code',
                'sourceText': '입찰에 참가하는 사업자는 소프트웨어사업자 업종코드 1468 등록을 필하여야 한다.',
                'codes': ['1468']
            }]
        }]
    }
    source_data = {'ok': True, 'generatedAt': '2026-11-12T09:00:00Z',
                   'byNotice': {'R26BK01808709:000': notice}}
    mod.run_summary_only(source_data, output, 1)
    first = json.loads(output.read_text(encoding='utf8'))
    assert first['analyzedCount'] == 1
    assert first['reviewCompleteCount'] == 0
    result = first['byNotice']['R26BK01808709:000']
    assert result['automaticEligibilityApproved'] is False
    assert result['blockers']
    assert 'sourceText' not in json.dumps(first)
    mod.run_summary_only(source_data, output, 1)
    second = json.loads(output.read_text(encoding='utf8'))
    assert second['analyzedCount'] == 1
    notice['files'][0]['sourceTextScanComplete'] = True
    notice['files'][0]['unmatchedQualificationAnchorCount'] = 0
    mod.run_summary_only(source_data, output, 1)
    third = json.loads(output.read_text(encoding='utf8'))
    assert third['byNotice']['R26BK01808709:000']['automaticEligibilityApproved'] is False
    assert third['byNotice']['R26BK01808709:000']['sourceCheckedAt'] == notice['checkedAt']

# A damaged sibling file must not erase a separately sourced, fully
# interpreted requirement. Nor may it imply the notice is fully reviewed.
import hashlib
quote = '입찰참가자격으로 소프트웨어사업자 업종코드 1468 등록을 필한 업체'
digest = hashlib.sha256(quote.encode()).hexdigest()
mixed_notice = {
    'status': 'text_extracted_requires_review',
    'manifestComplete': True, 'attachmentManifestCount': 2,
    'files': [
        {'name': '입찰공고문.pdf', 'readable': True,
         'sourceSha256': digest, 'textSha256': digest,
         'sourceTextScanComplete': True,
         'unmatchedQualificationAnchorCount': 0,
         'clauseCandidates': [{
             'type': 'industry_code', 'codes': ['1468'],
             'sourceFile': '입찰공고문.pdf', 'sourceText': quote}]},
        {'name': '기술지원협약서.pdf', 'readable': False,
         'errorCategory': 'pdf_unreadable_page'}
    ]
}
mixed = mod.process_one('R26TEST:000', mixed_notice, None,
                        mod.rule_based_interpret, mode='rule_based')
assert mixed['reviewComplete'] is False
assert mixed['requirementCoverage'][0]['status'] == 'confirmed_in_scanned_document'
assert mixed['requirementCoverage'][0]['bidderEligibilityVerified'] is False
assert 'unreadable_or_unhashed_document' in mixed['fullDocumentAudit']['blockers']
with tempfile.TemporaryDirectory() as temp:
    output = Path(temp) / 'summary.json'
    mod.run_summary_only({'byNotice': {'R26TEST:000': mixed_notice}}, output, 1)
    entry = json.loads(output.read_text())['byNotice']['R26TEST:000']
    assert entry['confirmedSourceClauses'] == 1
    assert entry['unreadableDocuments'] == 1
    assert entry['reviewComplete'] is False
    assert entry['automaticEligibilityApproved'] is False

print('WORKLINKS_QUALIFICATION_SUMMARY_NO_NETWORK=PASS')
