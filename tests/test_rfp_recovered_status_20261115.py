#!/usr/bin/env python3
"""A fully readable SHA-verified repair cannot leave status=text_unavailable."""
import datetime
import sys
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import repair_open_rfp_cached_attachments as repair

stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
valid={'name':'입찰공고자료.zip','readable':True,
       'sourceTextScanComplete':True,'sourceSha256':'c'*64,
       'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
       'extractionEvidence':{'extractionMethod':'hwpx_embedded_image_ocr'}}
record={'status':'text_unavailable','reasonCode':'download_or_format_failure',
    'manifestComplete':True,'files':[valid],'reviewComplete':False,
    'requiredConditionsComplete':False}
with patch.object(repair.rfp,'staffing_summary',return_value={}),\
     patch.object(repair.rfp,'staffing_fact_summary',return_value={}):
    repair.update_counts(record,stamp,[])
assert record['readableDocumentCount']==1,record
assert record['unreadableDocumentCount']==0,record
assert record['status']=='text_extracted_requires_review',record
assert record['reasonCode']=='readable_text_requires_full_review',record
assert record['reviewComplete'] is False and record['requiredConditionsComplete'] is False
assert record['staffingRoleScanComplete'] is not None

# Partially repaired source has readable text but must not pretend legal
# requirements are complete, or erase an unresolved sibling error.
partial={'status':'text_unavailable','reasonCode':'download_or_format_failure',
    'manifestComplete':True,'files':[dict(valid),{
         'name':'bad-binary.hwp','readable':False,'errorCategory':'hwp_record_fallback_failed'}]}
with patch.object(repair.rfp,'staffing_summary',return_value={}),\
     patch.object(repair.rfp,'staffing_fact_summary',return_value={}):
    repair.update_counts(partial,stamp,[])
assert partial['status']=='text_extracted_requires_review'
assert partial['unreadableDocumentCount']==1
assert partial['files'][1]['errorCategory']=='hwp_record_fallback_failed'
assert partial['reviewComplete'] is False and partial['requiredConditionsComplete'] is False

# No restored file must leave status as an honest failure.
unread={'status':'text_unavailable','reasonCode':'download_or_format_failure',
    'manifestComplete':True,'files':[{'name':'broken.hwpx','readable':False,
      'errorCategory':'hwpx_image_ocr_incomplete'}]}
with patch.object(repair.rfp,'staffing_summary',return_value={}),\
     patch.object(repair.rfp,'staffing_fact_summary',return_value={}):
    repair.update_counts(unread,stamp,[])
assert unread['status']=='text_unavailable',unread
assert unread['reasonCode']=='download_or_format_failure',unread
print('RFP_VERIFIED_REPAIRED_SOURCE_STATUS_AND_NO_FALSE_LEGAL_REVIEW=PASS')
