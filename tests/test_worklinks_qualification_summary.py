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
print('WORKLINKS_QUALIFICATION_SUMMARY_NO_NETWORK=PASS')
