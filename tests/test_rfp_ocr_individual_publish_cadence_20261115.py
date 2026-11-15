#!/usr/bin/env python3
"""No-network scheduler regression for per-notice publishing and immediate local drain."""
import importlib.util
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ocr_independent_schedule',
                       ROOT/'server/worklinks-server123-pipeline.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

with tempfile.TemporaryDirectory() as temp:
    p=Path(temp)
    m.DATA=p;m.SEEDS=p/'snapshots';m.STATE=p/'scheduler-state.json'
    m.SEEDS.mkdir()
    now=time.time()
    state={
      'rfpUpgradeActive':True,
      'rfpUpgradeBatchesCompleted':13,
      'rfpOpenRepairUpgradeBatch':13,
      'rfpOpenRepairHasMore':True}
    for name in m.PUBLISHED:
        state[name]={'attemptEpoch':now,'status':'ok'}
    state['rfpUpgrade']={'attemptEpoch':now,'status':'waiting_for_download',
                        'retryAfterEpoch':now+500}
    state['rfpOpenRepair']={'attemptEpoch':now-16,'status':'ok'}
    m.publish_state(state)
    work=[]
    def job(name,runner=None,_single=False):
        work.append((name,_single))
        assert name=='rfpOpenRepair'
        assert _single is True
        return True
    with patch.object(m,'run_once',side_effect=job):
        first=m.iteration(now)
        assert work==[('rfpOpenRepair',True)],work
        assert first['rfpOpenRepairHasMore'] is True
        assert first['rfpOpenRepair']['status']=='ok'
        m.iteration(now+5)
        assert len(work)==1,'must not spin every scheduler tick'
        m.iteration(now+16)
        assert len(work)==2,'pending OCR must continue after a 15s pause'
    # No remaining verified file: honor the idle 120-second cooldown.
    def empty(name,runner=None,_single=False):
        assert name=='rfpOpenRepair'
        return False
    with patch.object(m,'run_once',side_effect=empty):
        drained=m.iteration(now+32)
        assert drained['rfpOpenRepairHasMore'] is False
    with patch.object(m,'run_once',side_effect=AssertionError('OCR work exhausted')):
        m.iteration(now+47)
    # OCR exceptions must not become a false 'has more' hot loop or crash
    ready=m.read_state()
    ready['rfpOpenRepair']={'attemptEpoch':now-200,'status':'ok'}
    ready['rfpOpenRepairHasMore']=False
    m.publish_state(ready)
    with patch.object(m,'run_once',side_effect=RuntimeError('ocr original unsupported')):
        failed=m.iteration(now+48)
        assert failed['rfpOpenRepairHasMore'] is False
        assert failed['rfpOpenRepair']['status']=='failed'
print('OCR_ONE_FILE_ONE_NOTICE_PUBLISH_CONTINUOUS_WORK_DRAIN=PASS')
