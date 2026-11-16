#!/usr/bin/env python3
"""A 438k character genuine RFP must not be silently truncated at 350k."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as r
import repair_open_rfp_cached_attachments as repair

assert r.RFP_QUALIFICATION_TEXT_LIMIT==1_000_000
assert r.STAFFING_ROLE_TEXT_LIMIT==r.RFP_QUALIFICATION_TEXT_LIMIT
text=('일반 사업 소개 문서의 설명입니다.\n'*18000)
assert len(text)>350000
text+='\n투입 인력: 개발자 2명\n'
assert len(text)<r.RFP_QUALIFICATION_TEXT_LIMIT
clauses=r.extract_rule_candidates(text,'제안요청서.hwpx')
audit=r.preserve_unclassified_qualification(text,'제안요청서.hwpx',clauses)
assert audit['sourceTextScanComplete'] is True,audit
roles=r.extract_staffing_roles(text,'제안요청서.hwpx')
assert any(role.get('count')==2 and '개발' in role.get('role','') for role in roles),roles

# Longer than the configured limit remains incomplete; do not fabricate
# coverage beyond examined text.
very_long=text+('가'*1_000_001)
audit=r.preserve_unclassified_qualification(very_long,'제안요청서.hwpx',
                                           r.extract_rule_candidates(very_long,'제안요청서.hwpx'))
assert audit['sourceTextScanComplete'] is False,audit
assert repair.READER_ATTEMPT_VERSION.endswith('v15-20261116')
print('RFP_LONG_DOCUMENT_FULL_SOURCE_COVERAGE_AND_FAIL_CLOSED=PASS')
