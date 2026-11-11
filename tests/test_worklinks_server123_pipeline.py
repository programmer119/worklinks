#!/usr/bin/env python3
"""No-network tests for server123 scheduler durability and publication."""
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

source=Path(__file__).resolve().parents[1]/'server'/'worklinks-server123-pipeline.py'
spec=importlib.util.spec_from_file_location('worklinks_pipeline',str(source))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    m.DATA=root
    m.SEEDS=root/'snapshots'
    m.SCRIPTS=root/'source'
    m.STATE=root/'scheduler.json'
    m.SEEDS.mkdir()
    m.SCRIPTS.mkdir()
    for script in ('refresh_worklinks_rfp.py','refresh_worklinks_actionable.py'):
        (m.SCRIPTS/script).write_text('# test fixture\n',encoding='utf-8')
    original={'ok':True,'generatedAt':'2026-11-01','byNotice':{
        'R26BK01808709:000':{'status':'text_extracted_requires_review'}}}
    for filename in ('rfp-clauses.json','rfp-coverage-index.json'):
        (m.SEEDS/filename).write_text(json.dumps(original),encoding='utf-8')
    (m.SEEDS/'changcom-actionable.json').write_text(json.dumps({
        'ok':True,'bizno':'1308185973',
        'counts':{'indexedSWTotal':6000},'bids':[]}),encoding='utf-8')
    def mock_runner(args,cwd,env,capture_output,text,timeout):
        assert env['WORKLINKS_G2B_API'].startswith('http://127.0.0.1:')
        assert 'serviceKey=' not in str(args)
        p=Path(cwd)/'startup-support'
        if 'refresh_worklinks_rfp.py' in args[1]:
            updated={'ok':True,'generatedAt':'2026-11-11','byNotice':{
               'R26BK01808709:000':{'status':'text_extracted_requires_review'},
               'R26BK01809647:000':{'status':'text_extracted_requires_review'}}}
            for filename in ('rfp-clauses.json','rfp-coverage-index.json'):
                (p/filename).write_text(json.dumps(updated),encoding='utf-8')
        else:
            updated={'ok':True,'bizno':'1308185973',
                     'counts':{'indexedSWTotal':6001},'bids':[]}
            (p/'changcom-actionable.json').write_text(json.dumps(updated),encoding='utf-8')
        return SimpleNamespace(returncode=0,stdout='mock=ok',stderr='')
    m.run_once('rfp',mock_runner)
    assert len(json.loads((m.SEEDS/'rfp-coverage-index.json').read_text())['byNotice'])==2
    with gzip.open(str(m.SEEDS/'rfp-coverage-index.json')+'.gz','rb') as f:
        assert len(json.load(f)['byNotice'])==2
    m.run_once('actionable',mock_runner)
    state=m.iteration(1700000000,mock_runner)
    assert state['actionable']['status']=='ok' and state['rfp']['status']=='ok'
    another=m.iteration(1700000001,mock_runner)
    assert another['rfp']['attemptEpoch']==1700000000
    historical={'ok':True,'byNotice':{'R26BK00000000:000':{},'R26BK01808709:000':{}}}
    (m.SEEDS/'rfp-coverage-index.json').write_text(json.dumps(historical))
    target=m.DATA/'test-regressed.json'
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
print('WORKLINKS_SERVER123_SCHEDULER_ATOMIC_NO_NETWORK=PASS')
