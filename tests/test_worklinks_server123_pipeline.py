#!/usr/bin/env python3
"""No-network tests for server123 scheduler durability and publication."""
import gzip
import os
import sys
from unittest.mock import patch
import importlib.util
import json
import sqlite3
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace

source=Path(__file__).resolve().parents[1]/'server'/'worklinks-server123-pipeline.py'
spec=importlib.util.spec_from_file_location('worklinks_pipeline',str(source))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
# The supervisor reports the actual saved parser/file failure, not one
# generic reason shared by every retry.
assert m.scan_failure_diagnosis({'status':'text_extracted_requires_review',
    'manifestComplete':True,'staffingRoleScanComplete':False,
    'files':[{'name':'good.pdf','readable':True,'sourceTextScanComplete':True},
             {'name':'bad.pdf','readable':False,
              'errorCategory':'pdf_ocr_incomplete'}]},{
    'classificationVersion':23,'staffingRoleScanVersion':4,
    'staffingFactScanVersion':2,'hwpxReaderVersion':3
})=='scan_staffing_incomplete:pdf_ocr_incomplete'
assert m.scan_failure_diagnosis({'status':'text_unavailable',
    'files':[{'name':'r.zip','readable':False,
              'errorCategory':'invalid_hwp'}]},{
    'classificationVersion':23,'staffingRoleScanVersion':4,
    'staffingFactScanVersion':2,'hwpxReaderVersion':3
})=='scan_extraction_text_unavailable:invalid_hwp'
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    m.DATA=root
    m.SEEDS=root/'snapshots'
    m.SCRIPTS=root/'source'
    m.STATE=root/'scheduler.json'
    m.SEEDS.mkdir()
    m.SCRIPTS.mkdir()
    for script in ('refresh_worklinks_rfp.py','staffing_facts.py','analyze_worklinks_rfp_ai.py',
                   'refresh_worklinks_actionable.py',
                   'refresh_worklinks_open_award_fallback.py',
                   'batch_backfill_changcom_top500_rfp.py',
                   'repair_changcom_top500_rfp.py',
                   'repair_open_rfp_cached_attachments.py',
                   'rfp_call_ledger.py','rfp_dual_queue.py','rfp_management_reconcile.py','rfp_live_activity.py','rfp_bulk_manifests.py'):
        (m.SCRIPTS/script).write_text('# test fixture\n',encoding='utf-8')
    original={'ok':True,'generatedAt':'2026-11-01','byNotice':{
        'R26BK01808709:000':{'status':'text_extracted_requires_review'}}}
    for filename in ('rfp-clauses.json','rfp-coverage-index.json'):
        (m.SEEDS/filename).write_text(json.dumps(original),encoding='utf-8')
    (m.SEEDS/'rfp-top500-batch-state-20261111.json').write_text(json.dumps(
        {'ok':True,'scans':{},'metadataCalls':47}),encoding='utf-8')
    (m.SEEDS/'rfp-top500-batch-metadata-20261111.json').write_text(json.dumps(
        {'ok':True,'byNotice':{},'targets':[]}),encoding='utf-8')
    (m.SEEDS/'changcom-actionable.json').write_text(json.dumps({
        'ok':True,'bizno':'1308185973',
        'counts':{'indexedSWTotal':6000,'softwareService':1},'bids':[{'bidNo':'R26BK01808709'}]}),encoding='utf-8')
    with tempfile.TemporaryDirectory() as staging_dir:
        staged=m.stage_workspace(Path(staging_dir),minimal=True)
        assert (staged/'snapshots'/'rfp-clauses.json').is_symlink()
        assert (staged/'snapshots'/'rfp-top500-batch-metadata-20261111.json').is_symlink()
        assert not (staged/'snapshots'/'rfp-coverage-index.json').is_symlink()
        assert (staged/'scripts'/'staffing_facts.py').is_file(), 'RFP extractor must stage its dependency'
        assert not (staged/'startup-support').exists()
    def mock_runner(args,cwd,env,capture_output,text,timeout):
        assert env['WORKLINKS_G2B_API'].startswith('http://127.0.0.1:')
        assert 'serviceKey=' not in str(args)
        p=Path(cwd)/'startup-support'
        if 'repair_changcom_top500_rfp.py' in args[1]:
            assert '--execute' in args and '--data-dir' in args
            (Path(cwd)/'snapshots'/'rfp-top500-repair-report-20261111.json').write_text(
                json.dumps({'ok':True,'targetSavedScans':0,
                  'repairAttemptedThisRun':0}),encoding='utf-8')
        elif 'repair_open_rfp_cached_attachments.py' in args[1]:
            assert '--execute' in args and '--data-dir' in args
            assert args[args.index('--limit')+1]=='1'
            assert args[args.index('--max-files')+1]=='1'
            assert 'serviceKey=' not in env['WORKLINKS_G2B_API']
            # The staged snapshot is intentionally unchanged for this fixture.
        elif 'refresh_worklinks_rfp.py' in args[1]:
            updated={'ok':True,'generatedAt':'2026-11-11','byNotice':{
               'R26BK01808709:000':{'status':'text_extracted_requires_review'},
               'R26BK01809647:000':{'status':'text_extracted_requires_review'}}}
            for filename in ('rfp-clauses.json','rfp-coverage-index.json'):
                (p/filename).write_text(json.dumps(updated),encoding='utf-8')
        elif 'analyze_worklinks_rfp_ai.py' in args[1]:
            assert '--summary-only' in args and '--rule-based' in args
            (p/'qualification-review.json').write_text(json.dumps({
               'ok':True,'schemaVersion':1,'mode':'rule_based','byNotice':{
                  'R26BK01808709:000':{'reviewComplete':False,
                       'automaticEligibilityApproved':False}}}),encoding='utf-8')
        elif 'refresh_worklinks_open_award_fallback.py' in args[1]:
            updated={'ok':True,'totalSavedSw':6001,'count':1,'byNotice':{
                'R26BK01808709:000':{'awardMethod':'협상에 의한 계약'}}}
            (p/'g2b-award-fields-open.json').write_text(json.dumps(updated),encoding='utf-8')
        else:
            updated={'ok':True,'bizno':'1308185973',
                     'counts':{'indexedSWTotal':6001,'softwareService':1},
                     'bids':[{'bidNo':'R26BK01808709'}]}
            (p/'changcom-actionable.json').write_text(json.dumps(updated),encoding='utf-8')
        return SimpleNamespace(returncode=0,stdout='mock=ok',stderr='')
    m.run_once('rfp',mock_runner)
    assert len(json.loads((m.SEEDS/'rfp-coverage-index.json').read_text())['byNotice'])==2
    with gzip.open(str(m.SEEDS/'rfp-coverage-index.json')+'.gz','rb') as f:
        assert len(json.load(f)['byNotice'])==2
    m.run_once('actionable',mock_runner)
    m.run_once('awardFallback',mock_runner)
    m.run_once('rfpRepair',mock_runner)
    m.run_once('rfpOpenRepair',mock_runner)
    m.run_once('qualification',mock_runner)
    assert json.loads((m.SEEDS/'qualification-review.json').read_text())['byNotice']['R26BK01808709:000']['reviewComplete'] is False
    report=m.SEEDS/'rfp-top500-repair-report-20261111.json'
    assert json.loads(report.read_text())['ok'] is True
    with gzip.open(str(report)+'.gz','rb') as f:
        assert json.load(f)['repairAttemptedThisRun']==0
    assert json.loads((m.SEEDS/'g2b-award-fields-open.json').read_text())['count']==1
    state=m.iteration(1700000000,mock_runner)
    assert all(state[k]['status']=='ok' for k in ('actionable','rfp','awardFallback','rfpRepair','rfpOpenRepair','qualification'))
    another=m.iteration(1700000001,mock_runner)
    assert another['rfp']['attemptEpoch']==1700000000

    # A triggered scan MUST continue the next bounded batch without a timed wait.
    now=time.time()
    active=m.read_state()
    active.update(rfpUpgradeActive=True,rfpUpgrade={'status':'parser_versions_upgraded','attemptEpoch':0})
    m.publish_state(active)
    batches=[]
    def recording_runner(args,**kwargs):
        if kwargs['env'].get('WORKLINKS_RFP_UPGRADE_ONLY')=='1':
            batches.append('upgrade')
        return mock_runner(args,**kwargs)
    first=m.iteration(now,recording_runner)
    second=m.iteration(now+1,recording_runner)
    assert len(batches)==2, 'successful RFP batches must run back-to-back'
    assert second['rfpUpgrade']['status']=='ok'
    assert second['rfpUpgrade']['attemptEpoch']==now+1
    assert second['rfpUpgradeActive'] is True
    assert second['rfpUpgradeBatchesCompleted']==2

    # A real upstream quota error should pause, never spin or hammer G2B.
    def quota_runner(args,**kwargs):
        if kwargs['env'].get('WORKLINKS_RFP_UPGRADE_ONLY')=='1':
            batches.append('quota_attempt')
            return SimpleNamespace(returncode=1,stdout='',
                                   stderr='RFP_UPSTREAM_DAILY_QUOTA_PREFLIGHT')
        return mock_runner(args,**kwargs)
    failed=m.iteration(now+2,quota_runner)
    assert failed['rfpUpgrade']['status']=='failed'
    assert failed['rfpUpgrade']['retryAfterEpoch']>=time.time()+21500
    assert failed['rfpUpgradeActive'] is True
    held=m.iteration(now+3,quota_runner)
    assert batches.count('quota_attempt')==1
    assert held['rfpUpgrade']['status']=='failed'

    # No currently eligible RFP is not proof every notice is complete:
    # keep the triggered queue active and recheck after a cooldown.
    active=m.read_state()
    active['rfpUpgrade']={'status':'ok','attemptEpoch':now+1}
    m.publish_state(active)
    def empty_runner(args,**kwargs):
        if kwargs['env'].get('WORKLINKS_RFP_UPGRADE_ONLY')=='1':
            return SimpleNamespace(returncode=0,stdout='RFP_UPGRADE_SELECT_COUNT 0',
                                   stderr='')
        return mock_runner(args,**kwargs)
    empty=m.iteration(now+4,empty_runner)
    assert empty['rfpUpgrade']['status']=='no_eligible_now'
    assert empty['rfpUpgradeActive'] is True
    assert empty['rfpUpgrade']['retryAfterEpoch']>time.time()+250

    # OCR repair is limited to one verified-source pass per four completed
    # scan batches. It must neither starve behind an always-active scanner
    # nor take over each individual scan batch.
    keep=m.read_state()
    keep['rfpUpgradeActive']=True
    keep['rfpUpgrade']={'status':'failed','attemptEpoch':now+4,
                       'retryAfterEpoch':time.time()+3600}
    keep['rfpOpenRepair']={'status':'ok','attemptEpoch':now-50}
    keep['rfpUpgradeBatchesCompleted']=3
    keep['rfpOpenRepairUpgradeBatch']=0
    m.publish_state(keep)
    repair_calls=[]
    def count_repair(args,**kwargs):
        if 'repair_open_rfp_cached_attachments.py' in args[1]:
            repair_calls.append('ocr')
        return mock_runner(args,**kwargs)
    deferred=m.iteration(now+5,count_repair)
    assert not repair_calls, 'expensive no-progress OCR must yield to upgrade queue'
    assert deferred['rfpOpenRepair']['attemptEpoch']==now-50
    keep=m.read_state()
    keep['rfpUpgradeBatchesCompleted']=4
    m.publish_state(keep)
    fair=m.iteration(now+6,count_repair)
    assert repair_calls==['ocr'],repair_calls
    assert fair['rfpOpenRepairUpgradeBatch']==4
    again=m.iteration(now+7,count_repair)
    assert repair_calls==['ocr'],repair_calls
    # A continuously successful first-time scan MUST periodically give one
    # turn to local OCR repair, while legacy top500 repair remains excluded.
    keep=m.read_state()
    keep['rfpUpgradeActive']=True
    keep['rfpUpgrade']={'status':'ok','attemptEpoch':now+7}
    keep['rfpOpenRepair']={'status':'ok','attemptEpoch':0}
    keep['rfpRepair']={'status':'ok','attemptEpoch':0}
    keep['rfpUpgradeBatchesCompleted']=101
    m.publish_state(keep)
    repair_blockers=[]
    def nonblocking_runner(args,**kwargs):
        if any(v in args[1] for v in (
                'repair_open_rfp_cached_attachments.py',
                'repair_changcom_top500_rfp.py')):
            repair_blockers.append(args[1])
        return mock_runner(args,**kwargs)
    active_next=m.iteration(now+8,nonblocking_runner)
    assert active_next['rfpUpgrade']['status']=='ok'
    assert repair_blockers==[str(next(p for p in repair_blockers if p.endswith(
        'repair_open_rfp_cached_attachments.py')))],repair_blockers
    assert active_next['rfpOpenRepairUpgradeBatch']>=101
    repair_blockers.clear()
    m.iteration(now+9,nonblocking_runner)
    assert not repair_blockers, 'OCR must not block each following scan batch'
    print('WORKLINKS_CONTINUOUS_SCAN_FAIR_LOCAL_OCR_REPAIR=PASS')

    # The scanner may have processed every currently eligible original and
    # be waiting on 1-hour retry cooldown; OCR still needs to drain its
    # already-verified local backlog without a new scan batch.
    idle=m.read_state()
    idle['rfpUpgradeActive']=True
    idle['rfpUpgrade']={'status':'waiting_for_download','attemptEpoch':now+9,
                        'retryAfterEpoch':now+3600}
    idle['rfpOpenRepair']={'status':'ok','attemptEpoch':now-150}
    idle['rfpOpenRepairUpgradeBatch']=int(idle.get('rfpUpgradeBatchesCompleted') or 0)
    m.publish_state(idle)
    idle_calls=[]
    def idle_reader(args,**kwargs):
        if 'repair_open_rfp_cached_attachments.py' in args[1]:
            idle_calls.append('ocr')
        return mock_runner(args,**kwargs)
    drained=m.iteration(now+10,idle_reader)
    assert idle_calls==['ocr'],idle_calls
    assert drained['rfpOpenRepair']['status']=='ok'
    print('WORKLINKS_OCR_REPAIR_DRAINS_DURING_SCAN_RETRY_COOLDOWN=PASS')

    print('WORKLINKS_RFP_UPGRADE_4_BATCH_OCR_FAIRNESS=PASS')

    # After durable snapshot publication, the scanner parent acknowledges its
    # independent scan lane. A failed batch must not silently complete notice.
    (m.SCRIPTS/'rfp_dual_queue.py').write_text(
        (source.parents[1]/'scripts'/'rfp_dual_queue.py').read_text())
    sys.path.insert(0,str(m.SCRIPTS))
    from rfp_dual_queue import RfpDualQueue
    dual=RfpDualQueue(m.DATA/'rfp-dual-queue.sqlite3')
    dual.enqueue([('R26BK01808709','000','2099-12-31')],'test-reader-1')
    claim=dual.claim_download()
    assert claim
    dual.downloaded(claim[0],{
        'attachments':{'ok':True,'complete':True,
                       'items':[{'name':'rfp.pdf','url':'https://www.g2b.go.kr/UntyAtchFile/test.pdf'}]},
        'noticeDocuments':{'ok':True,'complete':True},
        'downloadVerifiedFiles':[{'name':'rfp.pdf',
            'url':'https://www.g2b.go.kr/UntyAtchFile/test.pdf','sha256':'a'*64}]
    },1,1)
    ready=dual.claim_ready(1)
    assert len(ready)==1
    def dual_runner(args,**kwargs):
        result=mock_runner(args,**kwargs)
        return SimpleNamespace(returncode=0,
            stdout='RFP_DUAL_SCAN_RESULT [{"key":"R26BK01808709:000","ok":true}]',
            stderr='')
    with patch.dict(os.environ,{'WORKLINKS_RFP_DUAL_QUEUE':'1'}):
        m.run_once('rfpUpgrade',dual_runner)
    assert dual.stats()['scan']['done']==1,dual.stats()
    print('WORKLINKS_DUAL_SCAN_COMMIT_AFTER_SNAPSHOT_PUBLISH=PASS')

    # Child scanner estimated 1 hour, but the durable queue has the actual
    # next attempt or an evidence-change hold. Live UI must not show the old
    # one-hour estimate, and success must clear stale file retry events.
    with dual.connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS rfp_live_events(
            lane TEXT,notice_key TEXT,file_key TEXT,phase TEXT,
            status TEXT,retry_epoch REAL,error_text TEXT,updated_epoch REAL)""")
        con.executemany("""INSERT INTO rfp_live_events
            VALUES('scan',?,?,?,'retry',?,'old hourly retry',0)""",[
              ('R26BK01808709:000','','판독 오류',time.time()+3600),
              ('R26BK01808709:000','file1','판독 오류',time.time()+3600)])
        con.execute("""UPDATE rfp_dual_notices
            SET scan_status='retry',scan_retry_epoch=2147483647,
                last_error='scan_staffing_incomplete:pdf_ocr_incomplete'
            WHERE notice_key='R26BK01808709:000'""")
    m.sync_scan_retry_activity(dual,'R26BK01808709:000')
    with dual.connect() as con:
        rows=con.execute("""SELECT file_key,phase,status,retry_epoch,error_text
             FROM rfp_live_events WHERE notice_key='R26BK01808709:000'""").fetchall()
        assert len(rows)==2 and all(r[3]==0 for r in rows),rows
        assert '변경 필요' in rows[0][1] and 'pdf_ocr_incomplete' in rows[0][4],rows
        con.execute("""UPDATE rfp_dual_notices SET scan_status='done',
            scan_retry_epoch=0,last_error=''
            WHERE notice_key='R26BK01808709:000'""")
    m.sync_scan_retry_activity(dual,'R26BK01808709:000')
    with dual.connect() as con:
        rows=con.execute("""SELECT file_key,status,retry_epoch,error_text
            FROM rfp_live_events WHERE notice_key='R26BK01808709:000'""").fetchall()
        assert rows==[('','done',0.0,'')],rows
    print('WORKLINKS_RFP_RETRY_UI_CLOCK_MATCHES_PERSISTED_QUEUE=PASS')

    historical={'ok':True,'byNotice':{'R26BK00000000:000':{},'R26BK01808709:000':{}}}
    (m.SEEDS/'rfp-coverage-index.json').write_text(json.dumps(historical))
    (m.DATA/'bad').mkdir()
    target=m.DATA/'bad'/'rfp-coverage-index.json'
    target.write_text(json.dumps(original))
    try:
        m.quality_guard('rfp',[target])
    except ValueError as error:
        assert 'regression' in str(error)
    else:
        raise AssertionError('RFP archive regression accepted')
    old=(m.SEEDS/'changcom-actionable.json').read_bytes()
    def fail_runner(*args,**kwargs):
        return SimpleNamespace(returncode=1,stdout='',stderr='mock failure')
    try:
        m.run_once('actionable',fail_runner)
    except RuntimeError:pass
    else:raise AssertionError('broken run considered success')
    assert (m.SEEDS/'changcom-actionable.json').read_bytes()==old
# Downloader supervision cannot be held hostage by long stage-3 scans.
import threading
watcher_calls=[]
watcher_stop=threading.Event()
def one_watch(current):
    watcher_calls.append(current.get('rfpUpgradeActive'))
    watcher_stop.set()
with (
    patch.object(m,'read_state',return_value={'rfpUpgradeActive':True}),
    patch.object(m,'ensure_independent_downloader',side_effect=one_watch),
):
    m.supervise_independent_downloader(watcher_stop)
assert watcher_calls==[True],watcher_calls

print('WORKLINKS_SERVER123_SCHEDULER_ATOMIC_NO_NETWORK=PASS')
