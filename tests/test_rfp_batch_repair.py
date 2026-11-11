#!/usr/bin/env python3
"""Frozen RFP repair keeps successful evidence and limits retries, without network."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import repair_changcom_top500_rfp as repair

original_process, original_fetch = repair.process, repair.fetch_json
calls = []
try:
    def fake_process(no, order, metadata=None, previous=None):
        calls.append(('extract', no))
        if no == 'R26BK00000001':
            return {'status':'text_extracted_requires_review',
                    'manifestComplete':True,
                    'files':[previous['files'][0],{'name':'fixed.hwp',
                               'readable':True,'sourceSha256':'b'*64}]}
        return {'status':'no_official_attachment_metadata','files':[]}
    def fake_fetch(url):
        calls.append(('metadata',url))
        return {'attachments':{'ok':True,'complete':True,'items':[]},
                'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
    repair.process, repair.fetch_json = fake_process, fake_fetch
    with tempfile.TemporaryDirectory() as td:
        snap = Path(td) / 'snapshots'
        snap.mkdir()
        records = {
          'R26BK00000001:000':{'status':'text_extracted_requires_review',
              'manifestComplete':True,'files':[
                {'name':'old.pdf','readable':True,'sourceSha256':'a'*64},
                {'name':'failed.hwp','readable':False,'errorCategory':'hwp5txt_failed'}]},
          'R26BK00000002:000':{'status':'text_extracted_requires_review',
              'manifestComplete':True,'files':[
                {'name':'good.pdf','readable':True,'sourceSha256':'c'*64}]},
          'R26BK00000003:000':{'status':'no_official_attachment_metadata','files':[]}
        }
        (snap/repair.STATE_NAME).write_text(json.dumps(
            {'ok':True,'scans':records,'metadataCalls':47}))
        (snap/repair.META_NAME).write_text(json.dumps({
            'ok':True,'byNotice':{key:{
              'attachments':{'ok':True,'complete':True,'items':[]},
              'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
              for key in records},'targets':list(records)}))
        old={'ok':True,'byNotice':{'HISTORIC:000':{
             'status':'text_extracted_requires_review'}}}
        for path in ('rfp-clauses.json','rfp-coverage-index.json'):
            (snap/path).write_text(json.dumps(old))
        dry=repair.run(td)
        assert dry['frozen']==3 and dry['incomplete']==2 and not calls
        done=repair.run(td,execute=True)
        assert done['readableDocumentCount']==3 and done['incompleteNoticeCount']==1
        assert sum(t=='metadata' for t,_ in calls)==1
        assert not any(x==('extract','R26BK00000002') for x in calls)
        state=json.loads((snap/repair.STATE_NAME).read_text())
        assert state['metadataCalls']==47
        assert state['scans']['R26BK00000001:000']['files'][0]['sourceSha256']=='a'*64
        index=json.loads((snap/'rfp-coverage-index.json').read_text())
        assert 'HISTORIC:000' in index['byNotice']
        repair.run(td,execute=True)
        repair.run(td,execute=True)
        stopped=repair.run(td,execute=True)
        assert stopped['repairAttemptedThisRun']==0
        assert stopped['attemptLimitReached']==1
        assert 'R26BK00000003:000' in stopped['unresolvedNoticeKeys']
finally:
    repair.process, repair.fetch_json = original_process, original_fetch
print('WORKLINKS_FROZEN_RFP_REPAIR_NO_NETWORK=PASS')
