#!/usr/bin/env python3
"""No network: scheduling, snapshots, failure and freshness guard."""
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile

spec=importlib.util.spec_from_file_location(
    'wl_standalone',Path(__file__).resolve().parents[1]/
    'server/worklinks-standalone-jobs.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    m.DATA=root
    m.SRC=root/'source'
    m.SNAP=root/'snapshots'
    m.STATE=root/'standalone-jobs-state.json'
    m.LOCK=root/'standalone-jobs.lock'
    m.SNAP.mkdir()
    m.SRC.mkdir()
    m.validate('localBudget',{
        'opportunities':[],'stats':{},'sources':[{'status':'ok'}]})
    m.validate('investment',{
        'schemaVersion':1,'opportunities':[],'sources':[{'status':'partial'}]})
    m.validate('kimseDeep',{'summary':{'sources':10},'sources':[]})
    m.validate('healthLive',{'results':[],'coverage':{'listingDegraded':[]}})
    m.validate('smeCert',{'ok':True,'recordsByBizno':{'1308185973':None}})
    m.validate('directProduction',{
        'ok':True,'complete':True,'recordCount':20000,'recordsByBizno':{}})
    for job,data in (
        ('localBudget',{'opportunities':[],'stats':{},'sources':[{'status':'error'}]}),
        ('investment',{'schemaVersion':1,'opportunities':[],'sources':[{'status':'error'}]}),
        ('kimseDeep',{'summary':{'sources':9},'sources':[]}),
        ('healthLive',{'results':[],'coverage':{'listingDegraded':['NIA']}}),
        ('smeCert',{'ok':True,'recordsByBizno':{}}),
        ('directProduction',{'ok':True,'complete':False,'recordCount':10})):
        try:m.validate(job,data)
        except ValueError:pass
        else:raise AssertionError('bad source accepted: '+job)
    original={'ok':True,'checkedAt':'2026-11-11T00:00:00Z',
              'recordsByBizno':{'1308185973':None}}
    body=(json.dumps(original)+'\n').encode()
    m.publish('smeCert',body)
    assert (m.SNAP/'sme-cert-snapshot.json').read_bytes()==body
    with gzip.open(m.SNAP/'sme-cert-snapshot.json.gz','rb') as g:
        assert g.read()==body
    try:m.publish('smeCert',(json.dumps({**original,'checkedAt':'2026-11-01T00:00:00Z'})+'\n').encode())
    except ValueError:pass
    else:raise AssertionError('older SME data replaced verified newer snapshot')
    assert (m.SNAP/'sme-cert-snapshot.json').read_bytes()==body
    m.update_source=lambda:(True,'abcdef123')
    m.test_source=lambda root:(True,[{'ok':True}])
    m.test_diagnostics=lambda root,cmd:[{'ok':True}]
    m.source_head=lambda:'abcdef123'
    received=[]
    class FakeProcess:
        pid=123
        def poll(self):return 0
    m.start_job=lambda job:received.append(job) or FakeProcess()
    # Two concurrent source collectors: first run is nonblocking and launches
    # only the first two while the Git poll loop remains responsive.
    state=m.iterate(1700000000)
    assert len(received)==2,received
    assert len(m.RUNNING)==2
    assert state['checkedHead']=='abcdef123'
    for tick in range(1,4):
        state=m.iterate(1700000000+tick)
    assert len(received)==len(m.JOBS),(received,m.JOBS)
    assert all(state[k]['status']=='ok' for k in m.JOBS)
    assert not m.RUNNING
    m.iterate(1700000004)
    assert len(received)==len(m.JOBS),'repeat loop launched duplicate jobs'
    # Restart-interrupted job must retry in minutes, not after a full day.
    restart=m.state_load()
    restart['localBudget']['status']='started'
    m.state_save(restart)
    m.iterate(1700000800)
    assert received.count('localBudget')==2,'interrupted collector never restarted'
    m.iterate(1700000801)
    assert m.state_load()['localBudget']['status']=='ok'
    m.update_source=lambda:(True,'def456')
    m.source_head=lambda:'def456'
    m.test_source=lambda root:(False,[{'ok':False,'tail':'bad source test'}])
    st=m.iterate(1700001200)
    assert st['checkedHead']=='abcdef123'
    assert not st['lastQa']['ok']
    assert len(received)==len(m.JOBS)+1,'failed source QA ran new collectors'
print('WORKLINKS_STANDALONE_NO_NETWORK_CADENCE_AND_SAFETY=PASS')
