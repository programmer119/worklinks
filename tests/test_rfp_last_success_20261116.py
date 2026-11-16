#!/usr/bin/env python3
"""Do not erase 4-insurance, headcount and onsite successes on safe rescans."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rfp_management_reconcile import (
    last_success_thumbnail,preserve_last_success_thumbnail,
    same_thumbnail_original,completed_thumbnail_source)

sha='a'*64
sig='g2b-document-manifest-v5-'+'b'*64
old={'status':'text_extracted_requires_review',
     'checkedAt':'2026-11-16T01:00:00Z',
     'classificationVersion':22,'hwpxReaderVersion':2,
     'manifestSignature':sig,'manifestComplete':True,
     'staffingRoleScanComplete':True,
     'files':[{'name':'사업제안서.pdf','readable':True,'sourceSha256':sha,
       'sourceTextScanComplete':True,'qualificationScanTruncated':False,
       'staffingRoleScanVersion':3,'staffingFactScanVersion':1,
       'staffingRoleScanTruncated':False}],
     'staffingRoles':[{'role':'개발자','count':2,'sourceFile':'사업제안서.pdf',
                       'sourceText':'개발자 2명'}],
     'staffingFacts':[{'kind':'staffing_requirement','requirementType':'onsite',
                       'sourceText':'상주 인력 2명 배치 의무',
                       'sourceFile':'사업제안서.pdf'}],
     'thumbnailClauses':[{'type':'staff_proof',
       'text':'입찰 참가 시 4대보험 가입 증명서 제출 필수',
       'sourceFile':'사업제안서.pdf'},
       {'type':'staff_proof','text':'상주 인력 2명 배치 의무',
        'sourceFile':'사업제안서.pdf'}]}
assert completed_thumbnail_source(old)
new={**old,'checkedAt':'2026-11-16T02:00:00Z','status':'partial',
     'files':[dict(old['files'][0],readable=False,sourceTextScanComplete=False,
                   sourceSha256=sha,errorCategory='ocr_deferred_to_repair')],
     'staffingRoleScanComplete':False,'staffingRoles':[],'staffingFacts':[]}
saved=preserve_last_success_thumbnail(new,old)
assert saved['lastSuccessfulThumbnail']['staffingRoles'][0]['count']==2
assert saved['lastSuccessfulThumbnail']['thumbnailClauses'][0]['text'].startswith('입찰 참가 시')
assert 'lastSuccessfulThumbnail' not in saved['lastSuccessfulThumbnail']
again={**new,'checkedAt':'2026-11-16T03:00:00Z'}
again=preserve_last_success_thumbnail(again,saved)
assert again['lastSuccessfulThumbnail']==saved['lastSuccessfulThumbnail']
# A new successfully completed version retires historical fallback.
finished={**old,'checkedAt':'2026-11-16T04:00:00Z'}
assert 'lastSuccessfulThumbnail' not in preserve_last_success_thumbnail(
  finished,saved)
# Different official manifest or byte hash means do NOT reuse a verdict.
changed=dict(new,manifestSignature='different-official-manifest')
assert not same_thumbnail_original(changed,old)
assert 'lastSuccessfulThumbnail' not in preserve_last_success_thumbnail(changed,saved)
changed_bytes=dict(new,files=[dict(new['files'][0],sourceSha256='c'*64)])
assert not same_thumbnail_original(changed_bytes,old)
assert 'lastSuccessfulThumbnail' not in preserve_last_success_thumbnail(changed_bytes,saved)
pending_manifest=dict(new,manifestChangePending=True)
assert 'lastSuccessfulThumbnail' not in preserve_last_success_thumbnail(
    pending_manifest,saved)
# No original hash and no manifest signature: fail closed, not just filenames.
unsigned={**old,'manifestSignature':''}
uncertain={**new,'manifestSignature':'',
           'files':[dict(new['files'][0],sourceSha256='')]}
assert not same_thumbnail_original(uncertain,unsigned)
# One successful badge must survive even when a different PDF failed and
# the notice never became fully current. Never promote a negative from this.
partial={**old,'manifestComplete':False,'staffingRoleScanComplete':False}
assert not completed_thumbnail_source(partial)
assert last_success_thumbnail(partial),'source-cited partial positives are valid'
recheck=dict(new,'lastSuccessfulThumbnail':{})
retained=preserve_last_success_thumbnail(recheck,partial)
assert retained['lastSuccessfulThumbnail']['staffingRoles'][0]['role']=='개발자'
assert retained['lastSuccessfulThumbnail']['thumbnailClauses'][0]['text'].startswith('입찰 참가')
print('RFP_INDIVIDUAL_POSITIVE_SURVIVES_INCOMPLETE_WHOLE_NOTICE=PASS')
print('RFP_LAST_SUCCESS_PRESERVED_AND_SHA_GUARDED=PASS')
