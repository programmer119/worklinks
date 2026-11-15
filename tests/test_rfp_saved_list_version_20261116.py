#!/usr/bin/env python3
"""Offline integration regression for /saved RFP version provenance.

This proves a completed notice that is served by the ordinary list endpoint
has the same current-parser status as /rfp-card-evidence, including when a
newer per-notice checkpoint supersedes the older coverage index.
"""
import datetime,json,os,runpy,sqlite3,tempfile
from pathlib import Path
from unittest.mock import patch

api=Path('/app/api.py')
if not api.exists():
    api=Path(__file__).resolve().parents[1]/'server/g2b-proxy.py'

with tempfile.TemporaryDirectory(prefix='worklinks-saved-version-') as tmp:
    db_path=str(Path(tmp)/'bids.sqlite3')
    with patch.dict(os.environ,{'G2B_DB_PATH':db_path}):
        module=runpy.run_path(str(api),run_name='test_saved_rfp_card_versions')
    g=module['query_saved_bids'].__globals__

    versions={'classificationVersion':23,'staffingRoleScanVersion':4,
              'staffingFactScanVersion':2,'hwpxReaderVersion':3}
    Path(tmp,'rfp-scanner-versions.json').write_text(
        json.dumps({'ok':True,'schemaVersion':1,'latest':versions}),encoding='utf-8')

    def record(checked,classification=23):
        return {'checkedAt':checked,'status':'text_extracted_requires_review',
                'manifestComplete':True,'classificationVersion':classification,
                'hwpxReaderVersion':3,'staffingRoleScanComplete':True,'files':[
                    {'name':'공고서.hwp','readable':False,
                     'skippedDuplicateFormat':True,'alternatePdfEvidence':'공고서.pdf',
                     'alternatePdfSourceSha256':'a'*64},
                    {'name':'공고서.pdf','readable':True,
                     'sourceTextScanComplete':True,'qualificationScanTruncated':False,
                     'staffingRoleScanTruncated':False,'staffingRoleScanVersion':4,
                     'staffingFactScanVersion':2,'sourceSha256':'b'*64},
                    {'name':'제안요청서.hwpx','readable':True,
                     'sourceTextScanComplete':True,'qualificationScanTruncated':False,
                     'staffingRoleScanTruncated':False,'staffingRoleScanVersion':4,
                     'staffingFactScanVersion':2,'sourceSha256':'c'*64}]}

    keys=['R26BK01810506:001','R26BK01826049:000']
    newer={'R26BK01810506:001':record('2026-11-15T15:10:21Z'),
           'R26BK01826049:000':record('2026-11-15T16:52:56Z')}
    index={keys[0]:record('2026-11-14T15:10:21Z',classification=20),
           keys[1]:newer[keys[1]]}

    checkpoint=sqlite3.connect(str(Path(tmp)/'rfp-notice-progress.sqlite3'))
    checkpoint.execute('CREATE TABLE rfp_notice_checkpoints ('
      'notice_key TEXT PRIMARY KEY, checked_at TEXT, evidence_json TEXT)')
    checkpoint.execute('INSERT INTO rfp_notice_checkpoints VALUES(?,?,?)',
      (keys[0],newer[keys[0]]['checkedAt'],json.dumps(newer[keys[0]])))
    checkpoint.commit()
    checkpoint.close()

    rows=[{'kind':'servc','bidNo':'R26BK01810506','order':'001',
           'title':'IU-EXCEL 교육모델 인증제도 지원 시스템 구축'},
          {'kind':'servc','bidNo':'R26BK01826049','order':'000',
           'title':'국립창원대학교 장비활용포털 통합 홈페이지 구축'}]
    with patch.dict(g,{'SNAPSHOT_ROOT':tmp,
                       'read_saved_rfp_evidence_index':lambda: index}):
        module['persist_bids'](rows)
        listed=module['query_saved_bids'](20,0,True)
        found={x['bidNo']+':'+str(x['order']).zfill(3):x['rfpSavedState']
               for x in listed['items']}
        cards=module['rfp_card_evidence_batch'](','.join(keys))['byNotice']
        assert set(found)==set(keys),(found.keys(),keys)
        for key in keys:
            state=found[key]
            assert state['complete'] is True,(key,state)
            assert state['scanComplete'] is True,(key,state)
            assert state['staffingRoleScanComplete'] is True,(key,state)
            assert state['parserCurrent'] is True,(key,state)
            assert state['classificationVersion']==23,(key,state)
            assert state['staffingRoleVersions']==[4],(key,state)
            assert state['staffingFactVersions']==[2],(key,state)
            assert cards[key]['parserCurrent']==state['parserCurrent']
            assert cards[key]['versionSource']==state['versionSource']
        assert found[keys[0]]['versionSource']=='checkpoint',found[keys[0]]
        assert found[keys[1]]['versionSource']=='coverage_index',found[keys[1]]
        search=module['query_saved_bids'](20,0,True,query='IU-EXCEL')
        assert search['totalCount']==1,search
        assert search['items'][0]['rfpSavedState']['parserCurrent'] is True,search
        print('WORKLINKS_SAVED_LIST_RFP_CURRENT_VERSION_AND_CARD_AGREE=PASS')
        print('WORKLINKS_SAVED_LIST_LIVE_CHECKPOINT_OVERRIDES_OLD_INDEX=PASS')
