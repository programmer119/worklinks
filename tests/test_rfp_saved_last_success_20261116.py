#!/usr/bin/env python3
"""Saved and card endpoints share one source-identity guarded prior-success view."""
import json,os,runpy,tempfile
from pathlib import Path
from unittest.mock import patch
api=Path('/app/api.py')
if not api.exists():api=Path(__file__).resolve().parents[1]/'server/g2b-proxy.py'
mod=runpy.run_path(str(api),run_name='saved_last_success_regression')
fn=mod['read_saved_rfp_card_states']
sha='a'*64
key='R26BK01810506:001'
prior={'status':'text_extracted_requires_review','checkedAt':'2026-11-15T13:00:00Z',
 'manifestComplete':True,'manifestSignature':'official-v1',
 'classificationVersion':22,'hwpxReaderVersion':3,
 'staffingRoleScanComplete':True,
 'files':[{'name':'제안요청서.pdf','readable':True,'sourceSha256':sha,
   'sourceTextScanComplete':True,'qualificationScanTruncated':False,
   'staffingRoleScanVersion':3,'staffingFactScanVersion':1,
   'staffingRoleScanTruncated':False}],
 'staffingRoles':[{'role':'개발자','count':2,'sourceFile':'제안요청서.pdf',
  'sourceText':'개발자 2명'}],
 'staffingFacts':[],
 'thumbnailClauses':[{'type':'staff_proof',
    'text':'입찰 참가 시 4대보험 가입 증명서 제출 필수',
    'sourceFile':'제안요청서.pdf'}]}
new={**prior,'checkedAt':'2026-11-16T11:00:00Z','status':'source_incomplete',
 'staffingRoleScanComplete':False,
 'files':[dict(prior['files'][0],readable=False,sourceTextScanComplete=False)],
 'staffingRoles':[],'staffingFacts':[],'thumbnailClauses':[],
 'lastSuccessfulThumbnail':prior}
with tempfile.TemporaryDirectory() as d:
 root=Path(d)
 (root/'rfp-scanner-versions.json').write_text(
  json.dumps({'ok':True,'schemaVersion':1,'latest':{
    'classificationVersion':23,'staffingRoleScanVersion':4,
    'staffingFactScanVersion':2,'hwpxReaderVersion':3}}),encoding='utf8')
 with patch.dict(fn.__globals__,{'SNAPSHOT_ROOT':d,
                   'G2B_DB_PATH':str(root/'bids.sqlite3')}):
    got=fn([key],{key:new},compact=True)[key]
    assert got.get('parserCurrent') is False,got
    old=got.get('lastSuccessfulState')
    assert old,got
    assert old['scanComplete'] is True,old
    assert old['staffingRoleScanComplete'] is True,old
    assert old['staffingRoles'][0]['count']==2,old
    assert old['excerpts'][0]['text'].startswith('입찰 참가 시'),old
    assert old['versionSource']=='last_success',old
    # Historical complete (old reader) also needs a fallback even before
    # the first new scan creates a separate lastSuccessfulThumbnail.
    stale=fn([key],{key:prior},compact=True)[key]
    assert stale['parserCurrent'] is False,stale
    assert stale.get('lastSuccessfulState'),stale
    # Once a new complete source is current, do not keep the old badge.
    current={**prior,'classificationVersion':23,
      'files':[dict(prior['files'][0],staffingRoleScanVersion=4,
           staffingFactScanVersion=2)],
      'lastSuccessfulThumbnail':prior}
    done=fn([key],{key:current},compact=True)[key]
    assert done['parserCurrent'] is True,done
    assert 'lastSuccessfulState' not in done,done
    # Changed source hashes/manifest never get a historical badge.
    changed=dict(new,manifestSignature='new-different-manifest')
    bad=fn([key],{key:changed},compact=True)[key]
    assert 'lastSuccessfulState' not in bad,bad
    mutated={**new,'files':[dict(new['files'][0],sourceSha256='b'*64)]}
    bad2=fn([key],{key:mutated},compact=True)[key]
    assert 'lastSuccessfulState' not in bad2,bad2
print('RFP_SAVED_API_PREVIOUS_RESULT_ONLY_IF_SAME_OFFICIAL_ORIGINAL=PASS')
