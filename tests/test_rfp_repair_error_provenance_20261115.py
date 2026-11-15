#!/usr/bin/env python3
"""A failed verified-original repair must publish its real new cause."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import repair_open_rfp_cached_attachments as r

def attempted(**changes):
    return {'lastReaderAttemptVersion':r.READER_ATTEMPT_VERSION,
            'lastReaderAttemptAt':'2026-11-15T04:30:00Z',**changes}

# Genuine XLS can remain labeled HWP failure until refreshed. Latest failure
# replaces obsolete provenance instead of being hidden in workflow logs only.
previous={'name':'supplier.xls','readable':False,
          'errorCategory':'hwp5txt_failed','error':'ValueError: hwp5txt_failed'}
incoming=attempted(name='supplier.xls',readable=False,detectedFormat='xls',
      errorCategory='legacy_xls_reader_failed',error='XLRDError: parse failure')
assert r.merge_verified_repair_attempt(previous,incoming) is False
assert previous['errorCategory']=='legacy_xls_reader_failed',previous
assert previous['detectedFormat']=='xls' and 'XLRDError' in previous['error']
assert previous['lastReaderAttemptVersion']==r.READER_ATTEMPT_VERSION

# No new metadata-only error may overwrite a completed SHA-verified file.
complete={'name':'rfp.pdf','readable':True,'sourceTextScanComplete':True,
          'sourceSha256':'a'*64}
assert r.merge_verified_repair_attempt(complete,incoming) is False
assert complete['readable'] is True and 'errorCategory' not in complete

# A returned partial PDF stays incomplete with precise unresolved-page details.
old={'name':'proposal.pdf','readable':False,'errorCategory':'file_extract_failure'}
partial=attempted(name='proposal.pdf',readable=False,sourceTextScanComplete=False,
                  detectedFormat='pdf',errorCategory='pdf_ocr_incomplete',
                  error='pdf_ocr_incomplete: unresolved PDF pages in source',
                  extractionEvidence={'sourceComplete':False,'unresolvedPages':3})
assert r.merge_verified_repair_attempt(old,partial) is False
assert old['errorCategory']=='pdf_ocr_incomplete'
assert old['extractionEvidence']['unresolvedPages']==3

# Complete local source SHA clears error and upgrades only this file.
verified=attempted(name='proposal.pdf',readable=True,sourceTextScanComplete=True,
                   sourceSha256='b'*64,detectedFormat='pdf')
assert r.merge_verified_repair_attempt(old,verified) is True
assert old['sourceSha256']=='b'*64 and old['readable'] is True
assert 'errorCategory' not in old and 'error' not in old

# Unattempted source must not make a stale snapshot change.
untouched={'name':'short.hwp','readable':False,'errorCategory':'invalid_hwp'}
assert r.merge_verified_repair_attempt(untouched,
         {'name':'short.hwp','errorCategory':'no_searchable_text'}) is False
assert untouched['errorCategory']=='invalid_hwp'
print('RFP_REPAIR_ERROR_PROVENANCE_REGRESSION=PASS')
